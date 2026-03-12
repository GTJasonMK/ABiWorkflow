from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompositionTask, Episode, Panel, PanelEffectiveBinding, ScriptEntity, ScriptEntityAssetBinding
from app.services.json_codec import from_json_text, to_json_text
from app.services.provider_constraints import resolve_video_duration_constraints
from app.services.provider_gateway import get_provider_config_or_404

WORKFLOW_STEP_EPISODES = "script"
WORKFLOW_STEP_ASSETS = "assets"
WORKFLOW_STEP_SCENES = "storyboard"
WORKFLOW_STEP_GENERATE = "video"
WORKFLOW_STEP_COMPOSE = "preview"

WORKFLOW_CHECK_ASSET_BINDING = "asset_binding_ready"
WORKFLOW_CHECK_PANELS = "panels_ready"
WORKFLOW_CHECK_PROVIDERS = "providers_ready"
WORKFLOW_CHECK_SCRIPT = "script_ready"
WORKFLOW_CHECK_VIDEO = "video_ready"
WORKFLOW_CHECK_VOICE = "voice_ready"

PROVIDER_TASK_TYPE_TO_FIELD = {
    "video": "video_provider_key",
    "tts": "tts_provider_key",
    "lipsync": "lipsync_provider_key",
}

PROVIDER_TYPES = ("video", "tts", "lipsync")
DEFAULT_PROVIDER_PAYLOAD_DEFAULTS: dict[str, dict[str, Any]] = {
    "video": {},
    "tts": {},
    "lipsync": {},
}
ASSET_ENTITY_TYPES = ("character", "location")


def normalize_provider_payload_defaults(value: Any) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {
        key: {}
        for key in PROVIDER_TYPES
    }
    if not isinstance(value, dict):
        return normalized
    for key in PROVIDER_TYPES:
        item = value.get(key)
        if isinstance(item, dict):
            normalized[key] = dict(item)
    return normalized


def normalize_skipped_checks(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def read_episode_provider_payload_defaults(episode: Episode) -> dict[str, dict[str, Any]]:
    return normalize_provider_payload_defaults(
        from_json_text(getattr(episode, "provider_payload_defaults_json", None), {})
    )


def read_episode_skipped_checks(episode: Episode) -> list[str]:
    return normalize_skipped_checks(from_json_text(getattr(episode, "skipped_checks_json", None), []))


def write_episode_provider_payload_defaults(value: dict[str, dict[str, Any]]) -> str | None:
    return to_json_text(normalize_provider_payload_defaults(value))


def write_episode_skipped_checks(value: list[str]) -> str | None:
    normalized = normalize_skipped_checks(value)
    return to_json_text(normalized) if normalized else None


def get_episode_provider_key(episode: Episode, task_type: str) -> str | None:
    field_name = PROVIDER_TASK_TYPE_TO_FIELD[task_type]
    value = getattr(episode, field_name, None)
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


async def validate_episode_provider_key(
    db: AsyncSession,
    *,
    provider_key: str | None,
    provider_type: str,
) -> str | None:
    key = (provider_key or "").strip() or None
    if key is None:
        return None
    if provider_type == "video":
        await resolve_video_duration_constraints(db, provider_key=key)
        return key
    config = await get_provider_config_or_404(db, key)
    if config.provider_type != provider_type:
        raise ValueError(f"provider_key={key} 不是 {provider_type} Provider（provider_type={config.provider_type}）")
    return key


def merge_episode_provider_payload(
    episode: Episode,
    *,
    task_type: str,
    extra_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    defaults = read_episode_provider_payload_defaults(episode)
    merged = dict(defaults.get(task_type) or {})
    if isinstance(extra_payload, dict):
        merged.update(extra_payload)
    return merged


def _binding_scope_episode_id(binding: ScriptEntityAssetBinding) -> str | None:
    strategy = from_json_text(binding.strategy_json, {})
    if not isinstance(strategy, dict):
        return None
    raw = strategy.get("episode_id")
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


def _read_effective_voice_id(compiled_json: str | None) -> str | None:
    payload = from_json_text(compiled_json, {})
    if not isinstance(payload, dict):
        return None
    effective_voice = payload.get("effective_voice")
    if not isinstance(effective_voice, dict):
        return None
    raw = effective_voice.get("voice_id")
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


def _check_blocker(check_key: str, skipped_checks: set[str]) -> bool:
    return check_key not in skipped_checks


def _empty_entity_id_sets() -> dict[str, set[str]]:
    return {
        entity_type: set()
        for entity_type in ASSET_ENTITY_TYPES
    }


def _compose_bound_entity_ids(
    *,
    shared_entity_ids_by_type: dict[str, set[str]] | None,
    scoped_entity_ids_by_type: dict[str, set[str]] | None,
) -> dict[str, set[str]]:
    merged = _empty_entity_id_sets()
    for entity_type in ASSET_ENTITY_TYPES:
        if shared_entity_ids_by_type:
            merged[entity_type].update(shared_entity_ids_by_type.get(entity_type) or set())
        if scoped_entity_ids_by_type:
            merged[entity_type].update(scoped_entity_ids_by_type.get(entity_type) or set())
    return merged


def _build_episode_workflow_summary_from_context(
    *,
    episode: Episode,
    panels: list[Panel],
    effective_voice_map: dict[str, str | None],
    bound_entity_ids_by_type: dict[str, set[str]],
    required_entity_ids_by_type: dict[str, set[str]],
    composed: bool,
) -> dict[str, Any]:
    skipped_checks = set(read_episode_skipped_checks(episode))
    script_text = (episode.script_text or "").strip()
    script_ready = bool(script_text)
    providers_ready = bool(get_episode_provider_key(episode, "video"))

    panel_total = len(panels)
    panel_video_done = sum(1 for panel in panels if bool(panel.video_url or panel.lipsync_video_url))
    panel_tts_done = sum(1 for panel in panels if bool(panel.tts_audio_url))
    panel_lipsync_done = sum(1 for panel in panels if bool(panel.lipsync_video_url))

    bound_characters = len(bound_entity_ids_by_type["character"])
    bound_locations = len(bound_entity_ids_by_type["location"])
    required_characters = len(required_entity_ids_by_type["character"])
    required_locations = len(required_entity_ids_by_type["location"])

    if required_characters > 0:
        character_ready = bound_entity_ids_by_type["character"] >= required_entity_ids_by_type["character"]
    else:
        character_ready = bound_characters > 0
    if required_locations > 0:
        location_ready = bound_entity_ids_by_type["location"] >= required_entity_ids_by_type["location"]
    else:
        location_ready = bound_locations > 0
    asset_binding_ready = script_ready and character_ready and location_ready

    panels_ready = panel_total > 0
    tts_provider_key = get_episode_provider_key(episode, "tts")
    voice_ready = True
    if panels_ready and tts_provider_key:
        voice_ready = all(
            bool(panel.tts_audio_url or panel.voice_id or effective_voice_map.get(panel.id))
            for panel in panels
        )

    video_ready = panels_ready and all(bool(panel.video_url or panel.lipsync_video_url) for panel in panels)

    blockers: list[str] = []
    if not script_ready and _check_blocker(WORKFLOW_CHECK_SCRIPT, skipped_checks):
        blockers.append("当前分集正文为空")
    if not providers_ready and _check_blocker(WORKFLOW_CHECK_PROVIDERS, skipped_checks):
        blockers.append("当前分集未配置视频 Provider")
    if not asset_binding_ready and _check_blocker(WORKFLOW_CHECK_ASSET_BINDING, skipped_checks):
        if required_characters > 0 and bound_characters < required_characters:
            blockers.append(f"角色绑定未完成（{bound_characters}/{required_characters}）")
        elif bound_characters <= 0:
            blockers.append("缺少角色绑定")
        if required_locations > 0 and bound_locations < required_locations:
            blockers.append(f"地点绑定未完成（{bound_locations}/{required_locations}）")
        elif bound_locations <= 0:
            blockers.append("缺少地点绑定")
    if not panels_ready and _check_blocker(WORKFLOW_CHECK_PANELS, skipped_checks):
        blockers.append("当前分集尚未生成分镜")
    if not voice_ready and _check_blocker(WORKFLOW_CHECK_VOICE, skipped_checks):
        blockers.append("存在未绑定语音的分镜")
    if not video_ready and _check_blocker(WORKFLOW_CHECK_VIDEO, skipped_checks):
        blockers.append("存在尚未完成视频生成的分镜")

    if not script_ready or not providers_ready:
        current_step = WORKFLOW_STEP_EPISODES
        completion_percent = 10 if script_ready else 0
    elif not asset_binding_ready and WORKFLOW_CHECK_ASSET_BINDING not in skipped_checks:
        current_step = WORKFLOW_STEP_ASSETS
        completion_percent = 25
    elif (
        not panels_ready
        or (not voice_ready and WORKFLOW_CHECK_VOICE not in skipped_checks)
    ):
        current_step = WORKFLOW_STEP_SCENES
        completion_percent = 50 if panels_ready else 40
    elif not video_ready and WORKFLOW_CHECK_VIDEO not in skipped_checks:
        current_step = WORKFLOW_STEP_GENERATE
        completion_percent = 70
    else:
        current_step = WORKFLOW_STEP_COMPOSE
        completion_percent = 100 if composed else 85

    return {
        "current_step": current_step,
        "completion_percent": completion_percent,
        "checks": {
            WORKFLOW_CHECK_SCRIPT: script_ready,
            WORKFLOW_CHECK_PROVIDERS: providers_ready,
            WORKFLOW_CHECK_ASSET_BINDING: asset_binding_ready,
            WORKFLOW_CHECK_PANELS: panels_ready,
            WORKFLOW_CHECK_VOICE: voice_ready,
            WORKFLOW_CHECK_VIDEO: video_ready,
            "compose_ready": video_ready,
            "composed": composed,
        },
        "counts": {
            "required_characters": required_characters,
            "bound_characters": bound_characters,
            "required_locations": required_locations,
            "bound_locations": bound_locations,
            "panel_total": panel_total,
            "panel_video_done": panel_video_done,
            "panel_tts_done": panel_tts_done,
            "panel_lipsync_done": panel_lipsync_done,
        },
        "blockers": blockers,
        "skipped_checks": sorted(skipped_checks),
    }


async def build_episode_workflow_summaries(
    episodes: list[Episode],
    db: AsyncSession,
) -> dict[str, dict[str, Any]]:
    if not episodes:
        return {}

    episode_ids = [episode.id for episode in episodes]
    project_ids = sorted({episode.project_id for episode in episodes})
    episode_ids_by_project: dict[str, list[str]] = {}
    for episode in episodes:
        episode_ids_by_project.setdefault(episode.project_id, []).append(episode.id)

    panels = (await db.execute(
        select(Panel)
        .where(Panel.episode_id.in_(episode_ids))
        .order_by(Panel.episode_id, Panel.panel_order, Panel.created_at)
    )).scalars().all()
    panels_by_episode_id = {episode.id: [] for episode in episodes}
    for panel in panels:
        panels_by_episode_id.setdefault(panel.episode_id, []).append(panel)

    panel_ids = [panel.id for panel in panels]
    effective_rows = (await db.execute(
        select(PanelEffectiveBinding).where(PanelEffectiveBinding.panel_id.in_(panel_ids))
    )).scalars().all() if panel_ids else []
    effective_voice_map = {
        row.panel_id: _read_effective_voice_id(row.compiled_json)
        for row in effective_rows
    }

    entities = (await db.execute(
        select(ScriptEntity).where(
            ScriptEntity.project_id.in_(project_ids),
            ScriptEntity.entity_type.in_(ASSET_ENTITY_TYPES),
        )
    )).scalars().all()
    entity_type_map = {
        entity.id: entity.entity_type
        for entity in entities
    }
    required_entity_ids_by_episode_id = {
        episode.id: _empty_entity_id_sets()
        for episode in episodes
    }
    for entity in entities:
        meta = from_json_text(entity.meta_json, {})
        if not isinstance(meta, dict):
            continue
        meta_episode_id = meta.get("episode_id")
        is_required = bool(meta.get("required"))
        is_ignored = bool(meta.get("ignored"))
        if is_required and not is_ignored and isinstance(meta_episode_id, str):
            episode_entity_sets = required_entity_ids_by_episode_id.get(meta_episode_id)
            if episode_entity_sets is not None:
                episode_entity_sets[entity.entity_type].add(entity.id)

    bindings = (await db.execute(
        select(ScriptEntityAssetBinding).where(
            ScriptEntityAssetBinding.project_id.in_(project_ids),
            ScriptEntityAssetBinding.asset_type.in_(ASSET_ENTITY_TYPES),
        )
    )).scalars().all()
    shared_bound_entity_ids_by_project = {
        project_id: _empty_entity_id_sets()
        for project_id in project_ids
    }
    scoped_bound_entity_ids_by_episode_id = {
        episode.id: _empty_entity_id_sets()
        for episode in episodes
    }
    for binding in bindings:
        entity_type = entity_type_map.get(binding.entity_id)
        if not entity_type or binding.asset_type != entity_type:
            continue
        binding_episode_id = _binding_scope_episode_id(binding)
        if binding_episode_id is None:
            shared_bound_entity_ids_by_project[binding.project_id][entity_type].add(binding.entity_id)
            continue
        scoped_entity_sets = scoped_bound_entity_ids_by_episode_id.get(binding_episode_id)
        if scoped_entity_sets is not None:
            scoped_entity_sets[entity_type].add(binding.entity_id)

    composed_episode_ids: set[str] = set()
    composition_rows = (await db.execute(
        select(CompositionTask.episode_id)
        .where(
            CompositionTask.project_id.in_(project_ids),
            CompositionTask.episode_id.in_(episode_ids),
            CompositionTask.status == "completed",
        )
        .order_by(CompositionTask.episode_id, CompositionTask.created_at.desc())
    )).all()
    for episode_id, in composition_rows:
        if isinstance(episode_id, str):
            composed_episode_ids.add(episode_id)

    return {
        episode.id: _build_episode_workflow_summary_from_context(
            episode=episode,
            panels=panels_by_episode_id.get(episode.id, []),
            effective_voice_map=effective_voice_map,
            bound_entity_ids_by_type=_compose_bound_entity_ids(
                shared_entity_ids_by_type=shared_bound_entity_ids_by_project.get(episode.project_id),
                scoped_entity_ids_by_type=scoped_bound_entity_ids_by_episode_id.get(episode.id),
            ),
            required_entity_ids_by_type=required_entity_ids_by_episode_id.get(episode.id, _empty_entity_id_sets()),
            composed=episode.id in composed_episode_ids,
        )
        for episode in episodes
    }
