from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class EpisodeResponse(BaseModel):
    id: str
    project_id: str
    episode_order: int
    title: str
    summary: str | None
    script_text: str | None
    video_provider_key: str | None
    tts_provider_key: str | None
    lipsync_provider_key: str | None
    provider_payload_defaults: dict[str, dict[str, Any]]
    skipped_checks: list[str]
    status: str
    panel_count: int = 0
    workflow_summary: dict[str, Any]
    created_at: str
    updated_at: str
