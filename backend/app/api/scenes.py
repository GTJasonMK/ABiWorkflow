from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import resolve_runtime_path, settings
from app.database import get_db
from app.models import Project, Scene, SceneCharacter, VideoClip
from app.schemas.common import ApiResponse
from app.schemas.scene import (
    CandidateClipResponse,
    ClipBrief,
    ClipSummary,
    SceneCharacterResponse,
    SceneReorderRequest,
    SceneResponse,
    SceneUpdate,
)
from app.services.composition_state import mark_completed_compositions_stale

router = APIRouter(prefix="/scenes", tags=["场景管理"])
GENERATION_AFFECTING_FIELDS = {
    "video_prompt",
    "negative_prompt",
    "duration_seconds",
}
IMMUTABLE_PROJECT_STATUSES = {"parsing", "generating", "composing"}
ALLOWED_TRANSITION_HINTS = {"none", "cut", "crossfade", "fade_black"}
NULLABLE_TEXT_FIELDS = {
    "description",
    "video_prompt",
    "negative_prompt",
    "camera_movement",
    "setting",
    "style_keywords",
    "dialogue",
}


@router.get("/project/{project_id}", response_model=ApiResponse[list[SceneResponse]])
async def list_scenes(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目的所有场景"""
    stmt = (
        select(Scene)
        .where(Scene.project_id == project_id)
        .options(
            selectinload(Scene.characters).selectinload(SceneCharacter.character),
            selectinload(Scene.video_clips),
        )
        .order_by(Scene.sequence_order)
    )
    result = await db.execute(stmt)
    scenes = result.scalars().all()
    return ApiResponse(data=[_to_response(s) for s in scenes])


@router.get("/{scene_id}", response_model=ApiResponse[SceneResponse])
async def get_scene(scene_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个场景详情"""
    scene = await _get_scene_or_404(scene_id, db)
    return ApiResponse(data=_to_response(scene))


@router.put("/{scene_id}", response_model=ApiResponse[SceneResponse])
async def update_scene(scene_id: str, body: SceneUpdate, db: AsyncSession = Depends(get_db)):
    """更新场景信息"""
    scene = await _get_scene_or_404(scene_id, db)
    project = (await db.execute(select(Project).where(Project.id == scene.project_id))).scalar_one()
    if project.status in IMMUTABLE_PROJECT_STATUSES:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许编辑场景")

    update_data = body.model_dump(exclude_unset=True)
    for field in NULLABLE_TEXT_FIELDS:
        if field in update_data and isinstance(update_data[field], str):
            normalized_text = update_data[field].strip()
            update_data[field] = normalized_text or None

    if "title" in update_data and update_data["title"] is not None:
        normalized_title = update_data["title"].strip()
        if not normalized_title:
            raise HTTPException(status_code=400, detail="场景标题不能为空")
        update_data["title"] = normalized_title

    if "transition_hint" in update_data and update_data["transition_hint"] is not None:
        normalized_transition = update_data["transition_hint"].strip().lower()
        if not normalized_transition:
            update_data["transition_hint"] = None
        elif normalized_transition not in ALLOWED_TRANSITION_HINTS:
            allowed = " / ".join(sorted(ALLOWED_TRANSITION_HINTS))
            raise HTTPException(status_code=400, detail=f"transition_hint 仅支持: {allowed}")
        else:
            update_data["transition_hint"] = normalized_transition

    changed_fields: set[str] = set()
    for key, value in update_data.items():
        if getattr(scene, key) != value:
            changed_fields.add(key)
        setattr(scene, key, value)

    # 当修改会影响视频生成结果的字段时，清理旧片段并回退到待生成状态，避免“编辑后仍沿用旧视频”。
    if changed_fields & GENERATION_AFFECTING_FIELDS:
        await db.execute(delete(VideoClip).where(VideoClip.scene_id == scene.id))
        scene.status = "pending"
        if project.status in {"completed", "failed"}:
            project.status = "parsed"
    elif changed_fields and project.status == "completed":
        # 即使只改字幕/转场等，也会影响最终成片，回退项目状态便于用户重新合成。
        project.status = "parsed"

    if changed_fields:
        await mark_completed_compositions_stale(db, project.id)

    await db.commit()
    await db.refresh(scene)
    # 重新加载关联
    scene = await _get_scene_or_404(scene_id, db)
    return ApiResponse(data=_to_response(scene))


@router.delete("/{scene_id}", response_model=ApiResponse[None])
async def delete_scene(scene_id: str, db: AsyncSession = Depends(get_db)):
    """删除场景"""
    scene = await _get_scene_or_404(scene_id, db)
    project = (await db.execute(select(Project).where(Project.id == scene.project_id))).scalar_one()
    if project.status in IMMUTABLE_PROJECT_STATUSES:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许删除场景")

    await db.delete(scene)
    # 删除后压缩顺序，避免 sequence_order 出现断层导致前端编号跳号。
    remaining_scenes = (await db.execute(
        select(Scene).where(Scene.project_id == project.id).order_by(Scene.sequence_order)
    )).scalars().all()
    for idx, item in enumerate(remaining_scenes):
        item.sequence_order = idx

    if project.status in {"completed", "failed"}:
        # 删除场景会影响成片与进度判断，回退到 parsed 让用户重新执行后续流程。
        project.status = "parsed"
    await mark_completed_compositions_stale(db, project.id)
    await db.commit()
    return ApiResponse(data=None)


@router.put("/project/{project_id}/reorder", response_model=ApiResponse[None])
async def reorder_scenes(project_id: str, body: SceneReorderRequest, db: AsyncSession = Depends(get_db)):
    """重新排序场景"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.status in IMMUTABLE_PROJECT_STATUSES:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许排序场景")

    project_scenes = (await db.execute(
        select(Scene).where(Scene.project_id == project_id)
    )).scalars().all()
    existing_ids = [scene.id for scene in project_scenes]
    if len(body.scene_ids) != len(existing_ids) or set(body.scene_ids) != set(existing_ids):
        raise HTTPException(status_code=400, detail="scene_ids 必须完整覆盖项目场景且不能重复")

    scene_map = {scene.id: scene for scene in project_scenes}
    order_changed = False
    for idx, scene_id in enumerate(body.scene_ids):
        if scene_map[scene_id].sequence_order != idx:
            order_changed = True
        scene_map[scene_id].sequence_order = idx

    if order_changed:
        if project.status == "completed":
            # 调整顺序会影响最终成片结果。
            project.status = "parsed"
        await mark_completed_compositions_stale(db, project.id)

    await db.commit()
    return ApiResponse(data=None)


async def _get_scene_or_404(scene_id: str, db: AsyncSession) -> Scene:
    """按 ID 查询场景，不存在时抛出 404"""
    stmt = (
        select(Scene)
        .where(Scene.id == scene_id)
        .options(
            selectinload(Scene.characters).selectinload(SceneCharacter.character),
            selectinload(Scene.video_clips),
        )
    )
    result = await db.execute(stmt)
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="场景不存在")
    return scene


def _to_response(scene: Scene) -> SceneResponse:
    """将 ORM 模型转为响应"""
    characters = []
    for sc in scene.characters:
        characters.append(SceneCharacterResponse(
            character_id=sc.character_id,
            character_name=sc.character.name if sc.character else "",
            action=sc.action,
            emotion=sc.emotion,
        ))

    # 构建视频片段摘要和详情列表
    video_clips = sorted(
        (getattr(scene, "video_clips", None) or []),
        key=lambda c: c.clip_order,
    )
    completed_count = sum(1 for c in video_clips if c.status == "completed")
    failed_count = sum(1 for c in video_clips if c.status == "failed")
    clip_summary = ClipSummary(
        total=len(video_clips),
        completed=completed_count,
        failed=failed_count,
    )
    clips = [
        ClipBrief(
            id=c.id,
            clip_order=c.clip_order,
            candidate_index=c.candidate_index,
            is_selected=c.is_selected,
            status=c.status,
            duration_seconds=c.duration_seconds,
            error_message=c.error_message,
        )
        for c in video_clips
    ]

    return SceneResponse(
        id=scene.id,
        project_id=scene.project_id,
        sequence_order=scene.sequence_order,
        title=scene.title,
        description=scene.description,
        video_prompt=scene.video_prompt,
        negative_prompt=scene.negative_prompt,
        camera_movement=scene.camera_movement,
        setting=scene.setting,
        style_keywords=scene.style_keywords,
        dialogue=scene.dialogue,
        duration_seconds=scene.duration_seconds,
        transition_hint=scene.transition_hint,
        status=scene.status,
        characters=characters,
        clip_summary=clip_summary,
        clips=clips,
        created_at=scene.created_at,
        updated_at=scene.updated_at,
    )


def _clip_to_media_url(file_path: str | None) -> str | None:
    """将 VideoClip 的 file_path 转为可访问的静态资源 URL。"""
    from pathlib import Path

    if not file_path:
        return None
    resolved = Path(file_path)
    if not resolved.is_absolute():
        resolved = resolve_runtime_path(resolved)
    root = resolve_runtime_path(settings.video_output_dir)
    try:
        relative = resolved.relative_to(root).as_posix()
        return f"/media/videos/{relative}"
    except ValueError:
        return None


@router.get("/{scene_id}/candidates", response_model=ApiResponse[list[CandidateClipResponse]])
async def list_candidates(scene_id: str, db: AsyncSession = Depends(get_db)):
    """获取场景的所有候选视频片段（含媒体地址）"""
    scene = (await db.execute(select(Scene).where(Scene.id == scene_id))).scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="场景不存在")

    clips = (await db.execute(
        select(VideoClip)
        .where(VideoClip.scene_id == scene_id)
        .order_by(VideoClip.clip_order, VideoClip.candidate_index)
    )).scalars().all()

    result = [
        CandidateClipResponse(
            id=c.id,
            clip_order=c.clip_order,
            candidate_index=c.candidate_index,
            is_selected=c.is_selected,
            status=c.status,
            duration_seconds=c.duration_seconds,
            error_message=c.error_message,
            media_url=_clip_to_media_url(c.file_path) if c.status == "completed" else None,
        )
        for c in clips
    ]
    return ApiResponse(data=result)


@router.put("/{scene_id}/clips/{clip_id}/select", response_model=ApiResponse[SceneResponse])
async def select_candidate(scene_id: str, clip_id: str, db: AsyncSession = Depends(get_db)):
    """选择候选片段用于合成"""
    clip = (await db.execute(
        select(VideoClip).where(VideoClip.id == clip_id, VideoClip.scene_id == scene_id)
    )).scalar_one_or_none()
    if clip is None:
        raise HTTPException(status_code=404, detail="片段不存在")
    if clip.status != "completed":
        raise HTTPException(status_code=400, detail="只能选择已完成的片段")

    # 将同组候选全部取消选中
    siblings = (await db.execute(
        select(VideoClip).where(
            VideoClip.scene_id == scene_id,
            VideoClip.clip_order == clip.clip_order,
        )
    )).scalars().all()
    for sibling in siblings:
        sibling.is_selected = False
    clip.is_selected = True

    # 查询场景所属项目，标记旧合成过期
    scene = (await db.execute(select(Scene).where(Scene.id == scene_id))).scalar_one()
    await mark_completed_compositions_stale(db, scene.project_id)
    await db.commit()

    scene = await _get_scene_or_404(scene_id, db)
    return ApiResponse(data=_to_response(scene))
