from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clip_status import CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED
from app.config import resolve_runtime_path, settings
from app.models import Episode, Panel, VideoClip
from app.panel_status import (
    PANEL_READY_STATUSES,
    PANEL_REGENERATABLE_STATUSES,
    PANEL_STATUS_COMPLETED,
    PANEL_STATUS_DRAFT,
    PANEL_STATUS_FAILED,
    PANEL_STATUS_PENDING,
)


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def resolve_panel_generation_prompt(panel: Panel, effective_binding: dict[str, Any] | None) -> str | None:
    effective = _clean_text((effective_binding or {}).get("effective_visual_prompt"))
    if effective:
        if _clean_text(panel.visual_prompt) or _clean_text(panel.script_text):
            return effective
        if effective != _clean_text(panel.title):
            return effective
    return _clean_text(panel.visual_prompt) or _clean_text(panel.script_text) or None


def resolve_panel_generation_request(panel: Panel, effective_binding: dict[str, Any] | None) -> dict[str, str | None]:
    effective = effective_binding or {}
    prompt = resolve_panel_generation_prompt(panel, effective)
    negative_prompt = _clean_text(effective.get("effective_negative_prompt")) or _clean_text(panel.negative_prompt) or None
    reference_image_url = (
        _clean_text(effective.get("effective_reference_image_url"))
        or _clean_text(panel.reference_image_url)
        or None
    )
    return {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "reference_image_url": reference_image_url,
    }


async def list_project_panels_ordered(project_id: str, db: AsyncSession) -> list[Panel]:
    stmt = (
        select(Panel)
        .join(Episode, Panel.episode_id == Episode.id)
        .where(Panel.project_id == project_id)
        .order_by(Episode.episode_order, Panel.panel_order, Panel.created_at)
    )
    return (await db.execute(stmt)).scalars().all()


def clip_to_media_url(file_path: str | None) -> str | None:
    if not file_path:
        return None
    resolved = Path(file_path)
    if not resolved.is_absolute():
        resolved = resolve_runtime_path(resolved)
    root = resolve_runtime_path(settings.video_output_dir)
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError:
        return None
    return f"/media/videos/{relative}"


def reset_panel_generation_state(panel: Panel, *, clear_lipsync: bool) -> None:
    panel.status = PANEL_STATUS_PENDING
    panel.video_url = None
    panel.video_provider_task_id = None
    panel.error_message = None
    if clear_lipsync:
        panel.lipsync_video_url = None
        panel.lipsync_provider_task_id = None
        panel.lipsync_status = "idle"


def count_panel_generation_result(panels: list[Panel]) -> tuple[int, int]:
    completed = sum(1 for item in panels if item.status == PANEL_STATUS_COMPLETED)
    failed = sum(1 for item in panels if item.status == PANEL_STATUS_FAILED)
    return completed, failed


def _fallback_panel_status(panel: Panel) -> str:
    if _clean_text(panel.visual_prompt) or _clean_text(panel.script_text):
        return PANEL_STATUS_PENDING
    return PANEL_STATUS_DRAFT


async def sync_panel_outputs_from_clips(
    project_id: str,
    db: AsyncSession,
    *,
    panel_ids: set[str] | None = None,
) -> tuple[int, int]:
    panels = await list_project_panels_ordered(project_id, db)
    if panel_ids is not None:
        panels = [panel for panel in panels if panel.id in panel_ids]
    if not panels:
        return 0, 0

    clips = (await db.execute(
        select(VideoClip)
        .where(
            VideoClip.panel_id.in_([panel.id for panel in panels]),
            VideoClip.status.in_([CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED]),
        )
        .order_by(VideoClip.panel_id, VideoClip.clip_order, VideoClip.candidate_index)
    )).scalars().all()

    selected_completed: dict[str, VideoClip] = {}
    fallback_completed: dict[str, VideoClip] = {}
    failed_map: dict[str, VideoClip] = {}
    for clip in clips:
        if clip.status == CLIP_STATUS_COMPLETED:
            if clip.is_selected and clip.panel_id not in selected_completed:
                selected_completed[clip.panel_id] = clip
            fallback_completed.setdefault(clip.panel_id, clip)
            continue
        failed_map.setdefault(clip.panel_id, clip)

    preferred_map = dict(fallback_completed)
    preferred_map.update(selected_completed)

    completed = 0
    failed = 0
    for panel in panels:
        preferred_clip = preferred_map.get(panel.id)
        failed_clip = failed_map.get(panel.id)
        if preferred_clip is not None:
            panel.status = PANEL_STATUS_COMPLETED
            panel.video_url = clip_to_media_url(preferred_clip.file_path)
            panel.error_message = None
            completed += 1
            continue

        if failed_clip is not None:
            panel.status = PANEL_STATUS_FAILED
            panel.video_url = None
            panel.lipsync_video_url = None
            panel.error_message = failed_clip.error_message or "分镜生成失败"
            failed += 1
            continue

        panel.video_url = None
        panel.error_message = None
        panel.lipsync_video_url = None
        if panel.status in PANEL_READY_STATUSES | PANEL_REGENERATABLE_STATUSES:
            panel.status = _fallback_panel_status(panel)

    await db.flush()
    return completed, failed
