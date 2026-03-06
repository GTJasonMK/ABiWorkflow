from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Panel, Project, Scene, VideoClip
from app.panel_status import PANEL_STATUS_PENDING
from app.project_status import (
    PROJECT_RESET_TO_PARSED_ON_CONTENT_CHANGE,
    PROJECT_STATUS_PARSED,
)
from app.scene_status import SCENE_STATUS_PENDING
from app.services.composition_state import mark_completed_compositions_stale


async def downgrade_project_after_generation_input_change(
    db: AsyncSession,
    project: Project,
    *,
    episode_id: str | None = None,
) -> None:
    """生成输入变更后，将项目回退到 parsed，并标记受影响成片为 stale。"""
    if project.status in PROJECT_RESET_TO_PARSED_ON_CONTENT_CHANGE:
        project.status = PROJECT_STATUS_PARSED
    await mark_completed_compositions_stale(db, project.id, episode_id=episode_id)


async def invalidate_panel_generation_outputs(
    db: AsyncSession,
    *,
    project: Project,
    panel: Panel,
) -> None:
    """分镜生成输入变化后，清空当前分镜输出并触发项目级失效。"""
    panel.status = PANEL_STATUS_PENDING
    panel.error_message = None
    panel.video_url = None
    panel.lipsync_video_url = None
    await downgrade_project_after_generation_input_change(db, project, episode_id=panel.episode_id)


async def invalidate_scene_outputs_for_regeneration(
    db: AsyncSession,
    scene_ids: list[str],
) -> None:
    """删除旧场景视频并把关联场景打回 pending，供重新生成使用。"""
    if not scene_ids:
        return

    await db.execute(delete(VideoClip).where(VideoClip.scene_id.in_(scene_ids)))
    affected_scenes = (await db.execute(select(Scene).where(Scene.id.in_(scene_ids)))).scalars().all()
    for scene in affected_scenes:
        scene.status = SCENE_STATUS_PENDING
