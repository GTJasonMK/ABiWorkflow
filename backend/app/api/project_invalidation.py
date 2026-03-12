from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Panel, Project, VideoClip
from app.panel_status import PANEL_STATUS_PENDING
from app.project_status import (
    PROJECT_RESET_TO_PARSED_ON_CONTENT_CHANGE,
    PROJECT_STATUS_PARSED,
)
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


def _clear_panel_runtime_state(
    panel: Panel,
    *,
    clear_video: bool = False,
    clear_tts: bool = False,
    clear_lipsync: bool = False,
) -> None:
    if clear_video:
        panel.video_url = None
        panel.video_provider_task_id = None
        panel.video_status = "idle"
    if clear_tts:
        panel.tts_audio_url = None
        panel.tts_provider_task_id = None
        panel.tts_status = "idle"
    if clear_lipsync:
        panel.lipsync_video_url = None
        panel.lipsync_provider_task_id = None
        panel.lipsync_status = "idle"


async def invalidate_panel_runtime_outputs(
    db: AsyncSession,
    *,
    project: Project,
    panel: Panel,
    clear_generation: bool = False,
    clear_voice: bool = False,
) -> None:
    """按影响范围清理分镜运行态输出，并触发一次项目级失效。"""
    if not clear_generation and not clear_voice:
        return

    if clear_generation:
        panel.status = PANEL_STATUS_PENDING
        panel.error_message = None
    _clear_panel_runtime_state(
        panel,
        clear_video=clear_generation,
        clear_tts=clear_voice,
        clear_lipsync=clear_generation or clear_voice,
    )
    await downgrade_project_after_generation_input_change(db, project, episode_id=panel.episode_id)


async def invalidate_panel_outputs_for_regeneration(
    db: AsyncSession,
    panel_ids: list[str],
) -> None:
    """删除旧分镜片段并把关联分镜打回 pending，供重新生成使用。"""
    if not panel_ids:
        return

    await db.execute(delete(VideoClip).where(VideoClip.panel_id.in_(panel_ids)))
    affected_panels = (await db.execute(select(Panel).where(Panel.id.in_(panel_ids)))).scalars().all()
    for panel in affected_panels:
        panel.status = PANEL_STATUS_PENDING
        panel.video_url = None
        panel.lipsync_video_url = None
        panel.video_provider_task_id = None
        panel.lipsync_provider_task_id = None
        panel.error_message = None


async def invalidate_project_generation_outputs(
    db: AsyncSession,
    *,
    project_id: str,
) -> list[str]:
    panel_ids = list((await db.execute(
        select(Panel.id).where(Panel.project_id == project_id)
    )).scalars().all())
    await invalidate_panel_outputs_for_regeneration(db, panel_ids)
    return panel_ids
