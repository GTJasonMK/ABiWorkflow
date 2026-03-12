from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response_utils import isoformat_or_empty
from app.models import Episode
from app.schemas.episode import EpisodeResponse
from app.services.episode_workflow import (
    build_episode_workflow_summaries,
    read_episode_provider_payload_defaults,
    read_episode_skipped_checks,
)


def build_episode_response(
    episode: Episode,
    *,
    panel_count: int,
    workflow_summary: dict,
) -> EpisodeResponse:
    return EpisodeResponse(
        id=episode.id,
        project_id=episode.project_id,
        episode_order=episode.episode_order,
        title=episode.title,
        summary=episode.summary,
        script_text=episode.script_text,
        video_provider_key=episode.video_provider_key,
        tts_provider_key=episode.tts_provider_key,
        lipsync_provider_key=episode.lipsync_provider_key,
        provider_payload_defaults=read_episode_provider_payload_defaults(episode),
        skipped_checks=read_episode_skipped_checks(episode),
        status=episode.status,
        panel_count=panel_count,
        workflow_summary=workflow_summary,
        created_at=isoformat_or_empty(episode.created_at),
        updated_at=isoformat_or_empty(episode.updated_at),
    )


async def build_episode_responses(
    episodes: list[Episode],
    *,
    db: AsyncSession,
    panel_count_map: dict[str, int] | None = None,
) -> list[EpisodeResponse]:
    if not episodes:
        return []
    counts = panel_count_map or {}
    workflow_summaries = await build_episode_workflow_summaries(episodes, db)
    return [
        build_episode_response(
            episode,
            panel_count=counts.get(episode.id, 0),
            workflow_summary=workflow_summaries.get(episode.id, {}),
        )
        for episode in episodes
    ]
