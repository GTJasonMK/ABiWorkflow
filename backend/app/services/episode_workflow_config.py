from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Episode, Project
from app.services.episode_workflow import (
    normalize_skipped_checks,
    validate_episode_provider_key,
    write_episode_provider_payload_defaults,
    write_episode_skipped_checks,
)
from app.services.project_workflow_defaults import (
    merge_provider_payload_defaults,
    read_project_workflow_defaults,
)

_PROVIDER_FIELDS: dict[str, str] = {
    "video_provider_key": "video",
    "tts_provider_key": "tts",
    "lipsync_provider_key": "lipsync",
}


def _normalize_explicit_provider_key(raw_value: Any, *, field_name: str) -> str | None:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if text:
        return text
    raise ValueError(f"{field_name} 不能为空；若要清空请传 null")


async def resolve_episode_create_workflow_config(
    db: AsyncSession,
    *,
    project: Project,
    raw_config: dict[str, Any] | None,
) -> dict[str, Any]:
    raw_data = dict(raw_config or {})
    project_defaults = read_project_workflow_defaults(project)
    resolved = {
        "provider_payload_defaults": merge_provider_payload_defaults(
            project_defaults["provider_payload_defaults"],
            raw_data.get("provider_payload_defaults") or {},
        ),
        "skipped_checks": normalize_skipped_checks(raw_data.get("skipped_checks") or []),
    }
    for field_name, provider_type in _PROVIDER_FIELDS.items():
        resolved[field_name] = await validate_episode_provider_key(
            db,
            provider_key=raw_data.get(field_name) or project_defaults[field_name],
            provider_type=provider_type,
        )
    return resolved


async def resolve_episode_update_workflow_config(
    db: AsyncSession,
    *,
    raw_updates: dict[str, Any],
) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for field_name, provider_type in _PROVIDER_FIELDS.items():
        if field_name not in raw_updates:
            continue
        resolved[field_name] = await validate_episode_provider_key(
            db,
            provider_key=_normalize_explicit_provider_key(raw_updates[field_name], field_name=field_name),
            provider_type=provider_type,
        )
    if "provider_payload_defaults" in raw_updates:
        resolved["provider_payload_defaults"] = merge_provider_payload_defaults(
            {},
            raw_updates.get("provider_payload_defaults") or {},
        )
    if "skipped_checks" in raw_updates:
        resolved["skipped_checks"] = normalize_skipped_checks(raw_updates.get("skipped_checks") or [])
    return resolved


def apply_episode_workflow_config(
    episode: Episode,
    workflow_config: dict[str, Any],
) -> None:
    for field_name in _PROVIDER_FIELDS:
        if field_name in workflow_config:
            setattr(episode, field_name, workflow_config[field_name])
    if "provider_payload_defaults" in workflow_config:
        episode.provider_payload_defaults_json = write_episode_provider_payload_defaults(
            workflow_config["provider_payload_defaults"]
        )
    if "skipped_checks" in workflow_config:
        episode.skipped_checks_json = write_episode_skipped_checks(workflow_config["skipped_checks"])
