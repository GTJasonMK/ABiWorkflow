from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clip_status import CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED
from app.composition_status import COMPOSITION_STATUS_COMPLETED
from app.config import resolve_runtime_path, settings
from app.database import get_db
from app.models import CompositionTask, Episode, Panel, Project, Scene
from app.schemas.common import ApiResponse

router = APIRouter(tags=["媒体资产"])


def _resolve_path(path_value: str | None) -> Path | None:
    """将绝对/相对路径统一解析为绝对路径，兼容历史 cwd 差异。"""
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path.resolve()

    runtime_based = resolve_runtime_path(path)
    cwd_based = (Path.cwd() / path).resolve()
    if runtime_based.exists():
        return runtime_based
    if cwd_based.exists():
        return cwd_based
    return runtime_based


def _to_media_url(file_path: str | None, root_dir: str, mount_prefix: str) -> str | None:
    """把磁盘路径转换为可访问的静态资源 URL。"""
    resolved_file = _resolve_path(file_path)
    if resolved_file is None:
        return None

    resolved_root = _resolve_path(root_dir)
    if resolved_root is None:
        return None

    try:
        relative = resolved_file.relative_to(resolved_root).as_posix()
        return f"{mount_prefix}/{relative}"
    except ValueError:
        return None


@router.get("/projects/{project_id}/assets", response_model=ApiResponse[dict])
async def get_project_assets(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目媒体资产概览（分镜片段 + 成片合成）。"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    panels = (await db.execute(
        select(Panel)
        .join(Episode, Panel.episode_id == Episode.id)
        .where(Panel.project_id == project_id)
        .order_by(Episode.episode_order, Panel.panel_order, Panel.created_at)
    )).scalars().all()

    scenes = (await db.execute(
        select(Scene)
        .where(Scene.project_id == project_id)
        .options(selectinload(Scene.video_clips))
        .order_by(Scene.sequence_order, Scene.created_at)
    )).scalars().all()

    panel_payload: list[dict] = []
    total_clips = 0
    failed_clips = 0
    ready_clips = 0

    scene_map: dict[int, Scene] = {}
    if len(scenes) == len(panels):
        candidate_map: dict[int, Scene] = {}
        duplicate_found = False
        for scene in scenes:
            sequence_order = int(scene.sequence_order)
            if sequence_order in candidate_map:
                duplicate_found = True
                break
            candidate_map[sequence_order] = scene
        if not duplicate_found and set(candidate_map) == set(range(len(panels))):
            scene_map = candidate_map

    for index, panel in enumerate(panels):
        mapped_scene = scene_map.get(index)
        clips = sorted((mapped_scene.video_clips if mapped_scene else []), key=lambda item: item.clip_order)
        clip_payload: list[dict] = []
        for clip in clips:
            total_clips += 1
            if clip.status == CLIP_STATUS_FAILED:
                failed_clips += 1
            if clip.status == CLIP_STATUS_COMPLETED:
                ready_clips += 1

            clip_payload.append({
                "id": clip.id,
                "clip_order": clip.clip_order,
                "candidate_index": clip.candidate_index,
                "is_selected": clip.is_selected,
                "status": clip.status,
                "duration_seconds": clip.duration_seconds,
                "provider_task_id": clip.provider_task_id,
                "file_path": clip.file_path,
                "media_url": _to_media_url(clip.file_path, settings.video_output_dir, "/media/videos"),
                "error_message": clip.error_message,
                "updated_at": clip.updated_at.isoformat() if clip.updated_at else None,
            })

        panel_payload.append({
            "panel_id": panel.id,
            "episode_id": panel.episode_id,
            "panel_order": panel.panel_order,
            "title": panel.title,
            "status": panel.status,
            "duration_seconds": panel.duration_seconds,
            "clips": clip_payload,
        })

    compositions = (await db.execute(
        select(CompositionTask)
        .where(CompositionTask.project_id == project_id)
        .order_by(CompositionTask.created_at.desc())
    )).scalars().all()

    composition_payload = [{
        "id": item.id,
        "status": item.status,
        "duration_seconds": item.duration_seconds,
        "transition_type": item.transition_type,
        "include_subtitles": item.include_subtitles,
        "include_tts": item.include_tts,
        "file_path": item.output_path,
        "media_url": _to_media_url(item.output_path, settings.composition_output_dir, "/media/compositions"),
        "download_url": f"/api/compositions/{item.id}/download",
        "error_message": item.error_message,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    } for item in compositions]
    available_composition_count = sum(1 for item in compositions if item.status == COMPOSITION_STATUS_COMPLETED)

    return ApiResponse(data={
        "project_id": project.id,
        "project_name": project.name,
        "summary": {
            "panel_count": len(panels),
            "clip_count": total_clips,
            "ready_clip_count": ready_clips,
            "failed_clip_count": failed_clips,
            "composition_count": available_composition_count,
        },
        "panels": panel_payload,
        "compositions": composition_payload,
    })
