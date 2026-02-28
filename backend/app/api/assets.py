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
from app.models import CompositionTask, Project, Scene, VideoClip
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
    """获取项目媒体资产概览（场景片段 + 成片合成）。"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    scenes = (await db.execute(
        select(Scene)
        .where(Scene.project_id == project_id)
        .options(selectinload(Scene.video_clips))
        .order_by(Scene.sequence_order)
    )).scalars().all()

    scene_payload: list[dict] = []
    total_clips = 0
    failed_clips = 0
    ready_clips = 0

    for scene in scenes:
        clips = sorted(scene.video_clips, key=lambda item: item.clip_order)
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

        scene_payload.append({
            "scene_id": scene.id,
            "sequence_order": scene.sequence_order,
            "title": scene.title,
            "status": scene.status,
            "duration_seconds": scene.duration_seconds,
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
            "scene_count": len(scene_payload),
            "clip_count": total_clips,
            "ready_clip_count": ready_clips,
            "failed_clip_count": failed_clips,
            "composition_count": available_composition_count,
        },
        "scenes": scene_payload,
        "compositions": composition_payload,
    })
