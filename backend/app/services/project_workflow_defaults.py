from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.services.episode_workflow import (
    DEFAULT_PROVIDER_PAYLOAD_DEFAULTS,
    normalize_provider_payload_defaults,
    validate_episode_provider_key,
)
from app.services.json_codec import from_json_text, to_json_text


def normalize_provider_key(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def empty_project_workflow_defaults() -> dict[str, Any]:
    return {
        "video_provider_key": None,
        "tts_provider_key": None,
        "lipsync_provider_key": None,
        "provider_payload_defaults": normalize_provider_payload_defaults({}),
    }


def read_project_provider_payload_defaults(project: Project) -> dict[str, dict[str, Any]]:
    return normalize_provider_payload_defaults(
        from_json_text(
            getattr(project, "default_provider_payload_defaults_json", None),
            DEFAULT_PROVIDER_PAYLOAD_DEFAULTS,
        )
    )


def write_project_provider_payload_defaults(value: dict[str, dict[str, Any]]) -> str | None:
    normalized = normalize_provider_payload_defaults(value)
    return to_json_text(normalized)


def read_project_workflow_defaults(project: Project) -> dict[str, Any]:
    return {
        "video_provider_key": normalize_provider_key(getattr(project, "default_video_provider_key", None)),
        "tts_provider_key": normalize_provider_key(getattr(project, "default_tts_provider_key", None)),
        "lipsync_provider_key": normalize_provider_key(getattr(project, "default_lipsync_provider_key", None)),
        "provider_payload_defaults": read_project_provider_payload_defaults(project),
    }


def merge_provider_payload_defaults(
    base: dict[str, dict[str, Any]] | None,
    overrides: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    merged = normalize_provider_payload_defaults(base or {})
    normalized_overrides = normalize_provider_payload_defaults(overrides or {})
    for key, value in normalized_overrides.items():
        if value:
            merged[key] = dict(value)
    return merged


async def resolve_project_workflow_defaults(
    db: AsyncSession,
    raw_defaults: dict[str, Any] | None,
    *,
    base_defaults: dict[str, Any] | None = None,
    clear_when_none: bool = False,
) -> dict[str, Any]:
    resolved = {
        **empty_project_workflow_defaults(),
        **(base_defaults or {}),
    }
    resolved["provider_payload_defaults"] = normalize_provider_payload_defaults(
        resolved.get("provider_payload_defaults") or {}
    )

    if raw_defaults is None:
        return empty_project_workflow_defaults() if clear_when_none else resolved

    raw_data = dict(raw_defaults)
    if "video_provider_key" in raw_data:
        resolved["video_provider_key"] = await validate_episode_provider_key(
            db,
            provider_key=raw_data.get("video_provider_key"),
            provider_type="video",
        )
    if "tts_provider_key" in raw_data:
        resolved["tts_provider_key"] = await validate_episode_provider_key(
            db,
            provider_key=raw_data.get("tts_provider_key"),
            provider_type="tts",
        )
    if "lipsync_provider_key" in raw_data:
        resolved["lipsync_provider_key"] = await validate_episode_provider_key(
            db,
            provider_key=raw_data.get("lipsync_provider_key"),
            provider_type="lipsync",
        )
    if "provider_payload_defaults" in raw_data:
        resolved["provider_payload_defaults"] = merge_provider_payload_defaults(
            resolved["provider_payload_defaults"],
            raw_data.get("provider_payload_defaults") or {},
        )
    return resolved


def apply_project_workflow_defaults(project: Project, workflow_defaults: dict[str, Any]) -> None:
    project.default_video_provider_key = workflow_defaults["video_provider_key"]
    project.default_tts_provider_key = workflow_defaults["tts_provider_key"]
    project.default_lipsync_provider_key = workflow_defaults["lipsync_provider_key"]
    project.default_provider_payload_defaults_json = write_project_provider_payload_defaults(
        workflow_defaults["provider_payload_defaults"]
    )
