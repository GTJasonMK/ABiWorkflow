from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Episode, Panel
from app.services.episode_workflow import normalize_provider_payload_defaults, write_episode_provider_payload_defaults


def build_episode(
    project_id: str,
    *,
    order: int = 0,
    title: str = "第1集",
    video_provider_key: str | None = None,
    tts_provider_key: str | None = None,
    lipsync_provider_key: str | None = None,
    provider_payload_defaults: dict[str, dict[str, Any]] | None = None,
) -> Episode:
    return Episode(
        project_id=project_id,
        episode_order=order,
        title=title,
        video_provider_key=video_provider_key,
        tts_provider_key=tts_provider_key,
        lipsync_provider_key=lipsync_provider_key,
        provider_payload_defaults_json=write_episode_provider_payload_defaults(
            normalize_provider_payload_defaults(provider_payload_defaults or {})
        ),
    )


def build_panel(
    project_id: str,
    episode_id: str,
    *,
    order: int = 0,
    title: str = "分镜一",
    visual_prompt: str | None = "prompt",
    duration_seconds: float = 5.0,
    status: str = "pending",
    video_url: str | None = None,
) -> Panel:
    return Panel(
        project_id=project_id,
        episode_id=episode_id,
        panel_order=order,
        title=title,
        visual_prompt=visual_prompt,
        duration_seconds=duration_seconds,
        status=status,
        video_url=video_url,
    )


async def seed_single_panel(
    db_session: AsyncSession,
    project_id: str,
    *,
    title: str,
    visual_prompt: str | None,
    duration_seconds: float,
    status: str,
    video_url: str | None = None,
) -> Episode:
    episode = build_episode(project_id)
    db_session.add(episode)
    await db_session.flush()
    db_session.add(build_panel(
        project_id,
        episode.id,
        title=title,
        visual_prompt=visual_prompt,
        duration_seconds=duration_seconds,
        status=status,
        video_url=video_url,
    ))
    await db_session.flush()
    return episode
