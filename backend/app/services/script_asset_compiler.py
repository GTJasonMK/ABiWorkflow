from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    EpisodeAssetOverride,
    GlobalCharacter,
    GlobalLocation,
    GlobalVoice,
    Panel,
    PanelAssetOverride,
    PanelEffectiveBinding,
    ScriptEntity,
    ScriptEntityAssetBinding,
)
from app.services.json_codec import from_json_text, to_json_text

SUPPORTED_ASSET_TYPES = {"character", "location", "voice"}
SUPPORTED_ENTITY_TYPES = {"character", "location", "speaker"}
COMPILER_VERSION = "v2"


def _safe_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    value = from_json_text(raw, {})
    return value if isinstance(value, dict) else {}


def _clean_text(value: str | None) -> str:
    return (value or "").strip()


def _binding_scope_episode_id(item: ScriptEntityAssetBinding) -> str | None:
    strategy = _safe_json(item.strategy_json)
    raw = strategy.get("episode_id") if isinstance(strategy, dict) else None
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(row.get("asset_type") or "").strip(),
        str(row.get("asset_id") or "").strip(),
        str(row.get("role_tag") or "").strip(),
    )


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        rows,
        key=lambda item: (
            str(item.get("asset_type") or ""),
            str(item.get("entity_name") or ""),
            0 if bool(item.get("is_primary")) else 1,
            int(item.get("priority") or 0),
            str(item.get("asset_name") or ""),
            str(item.get("asset_id") or ""),
        ),
    )


def _ensure_primary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in rows:
        grouped.setdefault((str(item.get("entity_id")), str(item.get("asset_type"))), []).append(item)

    for (_, _), group in grouped.items():
        group.sort(key=lambda item: (0 if bool(item.get("is_primary")) else 1, int(item.get("priority") or 0)))
        primary = next((item for item in group if bool(item.get("is_primary"))), None) or group[0]
        for item in group:
            item["is_primary"] = item is primary
    return rows


def _merge_override(base_rows: list[dict[str, Any]], override_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not override_rows:
        return base_rows
    replace_keys = {(str(item.get("entity_id")), str(item.get("asset_type"))) for item in override_rows}
    kept = [
        item
        for item in base_rows
        if (str(item.get("entity_id")), str(item.get("asset_type"))) not in replace_keys
    ]
    merged = kept + override_rows
    dedup: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in merged:
        dedup[(str(item.get("entity_id")),) + _row_key(item)] = item
    return list(dedup.values())


def _entity_hits_panel(entity: ScriptEntity, panel_text: str) -> bool:
    if not panel_text:
        return False
    name = _clean_text(entity.name).lower()
    alias = _clean_text(entity.alias).lower()
    text = panel_text.lower()
    if name and name in text:
        return True
    if alias and alias in text:
        return True
    return False


def _payload_from_default_binding(item: ScriptEntityAssetBinding, entity: ScriptEntity) -> dict[str, Any]:
    return {
        "entity_id": item.entity_id,
        "entity_name": entity.name,
        "entity_type": entity.entity_type,
        "asset_type": item.asset_type,
        "asset_id": item.asset_id,
        "asset_name": item.asset_name,
        "role_tag": item.role_tag,
        "priority": int(item.priority or 0),
        "is_primary": bool(item.is_primary),
        "strategy": _safe_json(item.strategy_json),
        "source_layer": "script",
    }


def _payload_from_episode_override(item: EpisodeAssetOverride, entity: ScriptEntity) -> dict[str, Any]:
    return {
        "entity_id": item.entity_id,
        "entity_name": entity.name,
        "entity_type": entity.entity_type,
        "asset_type": item.asset_type,
        "asset_id": item.asset_id,
        "asset_name": item.asset_name,
        "role_tag": item.role_tag,
        "priority": int(item.priority or 0),
        "is_primary": bool(item.is_primary),
        "strategy": _safe_json(item.strategy_json),
        "source_layer": "episode",
    }


def _payload_from_panel_override(item: PanelAssetOverride, entity: ScriptEntity) -> dict[str, Any]:
    return {
        "entity_id": item.entity_id,
        "entity_name": entity.name,
        "entity_type": entity.entity_type,
        "asset_type": item.asset_type,
        "asset_id": item.asset_id,
        "asset_name": item.asset_name,
        "role_tag": item.role_tag,
        "priority": int(item.priority or 0),
        "is_primary": bool(item.is_primary),
        "strategy": _safe_json(item.strategy_json),
        "source_layer": "panel",
    }


async def _build_effective_rows(panel: Panel, db: AsyncSession) -> list[dict[str, Any]]:
    entities = (await db.execute(
        select(ScriptEntity).where(
            ScriptEntity.project_id == panel.project_id,
            ScriptEntity.entity_type.in_(list(SUPPORTED_ENTITY_TYPES)),
        )
    )).scalars().all()
    entity_map = {item.id: item for item in entities}

    panel_text = " ".join(
        [
            _clean_text(panel.title),
            _clean_text(panel.script_text),
            _clean_text(panel.visual_prompt),
            _clean_text(panel.tts_text),
        ]
    ).strip()
    matched_entity_ids = {item.id for item in entities if _entity_hits_panel(item, panel_text)}

    all_default_rows = (await db.execute(
        select(ScriptEntityAssetBinding).where(
            ScriptEntityAssetBinding.project_id == panel.project_id,
            ScriptEntityAssetBinding.asset_type.in_(list(SUPPORTED_ASSET_TYPES)),
        )
    )).scalars().all()
    default_rows = [item for item in all_default_rows if _binding_scope_episode_id(item) is None]
    scoped_default_rows = [
        item for item in all_default_rows
        if _binding_scope_episode_id(item) == panel.episode_id
    ]

    episode_rows = (await db.execute(
        select(EpisodeAssetOverride).where(
            EpisodeAssetOverride.episode_id == panel.episode_id,
            EpisodeAssetOverride.asset_type.in_(list(SUPPORTED_ASSET_TYPES)),
        )
    )).scalars().all()
    panel_rows = (await db.execute(
        select(PanelAssetOverride).where(
            PanelAssetOverride.panel_id == panel.id,
            PanelAssetOverride.asset_type.in_(list(SUPPORTED_ASSET_TYPES)),
        )
    )).scalars().all()

    forced_entity_ids = (
        {item.entity_id for item in scoped_default_rows}
        | {item.entity_id for item in episode_rows}
        | {item.entity_id for item in panel_rows}
    )
    effective_entity_ids = matched_entity_ids | forced_entity_ids

    default_payload = [
        _payload_from_default_binding(item, entity_map[item.entity_id])
        for item in default_rows
        if item.entity_id in effective_entity_ids and item.entity_id in entity_map
    ]
    scoped_default_payload = [
        {
            **_payload_from_default_binding(item, entity_map[item.entity_id]),
            "source_layer": "script_episode",
        }
        for item in scoped_default_rows
        if item.entity_id in effective_entity_ids and item.entity_id in entity_map
    ]
    episode_payload = [
        _payload_from_episode_override(item, entity_map[item.entity_id])
        for item in episode_rows
        if item.entity_id in effective_entity_ids and item.entity_id in entity_map
    ]
    panel_payload = [
        _payload_from_panel_override(item, entity_map[item.entity_id])
        for item in panel_rows
        if item.entity_id in effective_entity_ids and item.entity_id in entity_map
    ]

    merged = _merge_override(default_payload, scoped_default_payload)
    merged = _merge_override(merged, episode_payload)
    merged = _merge_override(merged, panel_payload)

    merged = _ensure_primary(merged)
    return _sort_rows(merged)


def _pick_primary(rows: list[dict[str, Any]], *, asset_type: str) -> dict[str, Any] | None:
    typed = [item for item in rows if item.get("asset_type") == asset_type]
    if not typed:
        return None
    typed.sort(key=lambda item: (0 if bool(item.get("is_primary")) else 1, int(item.get("priority") or 0)))
    return typed[0]


def _effective_voice_payload_from_binding(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "voice_id": row.get("asset_id"),
        "voice_name": row.get("asset_name"),
        "provider": row.get("provider"),
        "voice_code": row.get("voice_code"),
        "style_prompt": row.get("style_prompt"),
        "language": row.get("language"),
        "gender": row.get("gender"),
        "strategy": row.get("strategy") or {},
        "source_layer": row.get("source_layer"),
        "entity_id": row.get("entity_id"),
        "entity_name": row.get("entity_name"),
    }


def _effective_voice_payload_from_character_default(
    primary_character: dict[str, Any] | None,
    voice_map: dict[str, GlobalVoice],
    warnings: list[str],
) -> dict[str, Any] | None:
    if primary_character is None:
        return None

    voice_id = _clean_text(primary_character.get("default_voice_id"))
    if not voice_id:
        return None

    voice = voice_map.get(voice_id)
    if voice is None:
        warnings.append(f"角色默认语音不存在: {voice_id}")
        return None

    return {
        "voice_id": voice.id,
        "voice_name": voice.name,
        "provider": voice.provider,
        "voice_code": voice.voice_code,
        "style_prompt": voice.style_prompt,
        "language": voice.language,
        "gender": voice.gender,
        "strategy": {},
        "source_layer": "character_default",
        "entity_id": None,
        "entity_name": primary_character.get("entity_name"),
        "role_tag": primary_character.get("role_tag"),
    }


async def compile_panel_effective_binding(panel: Panel, db: AsyncSession) -> dict[str, Any]:
    rows = await _build_effective_rows(panel, db)

    character_ids = [str(item["asset_id"]) for item in rows if item.get("asset_type") == "character"]
    location_ids = [str(item["asset_id"]) for item in rows if item.get("asset_type") == "location"]
    voice_ids = [str(item["asset_id"]) for item in rows if item.get("asset_type") == "voice"]

    characters = (await db.execute(
        select(GlobalCharacter).where(GlobalCharacter.id.in_(character_ids))
    )).scalars().all() if character_ids else []
    locations = (await db.execute(
        select(GlobalLocation).where(GlobalLocation.id.in_(location_ids))
    )).scalars().all() if location_ids else []
    fallback_voice_ids = [
        str(item.default_voice_id)
        for item in characters
        if item.default_voice_id
    ]
    all_voice_ids = list(dict.fromkeys([*voice_ids, *fallback_voice_ids]))
    voices = (await db.execute(
        select(GlobalVoice).where(GlobalVoice.id.in_(all_voice_ids))
    )).scalars().all() if all_voice_ids else []

    character_map = {item.id: item for item in characters}
    location_map = {item.id: item for item in locations}
    voice_map = {item.id: item for item in voices}

    character_items: list[dict[str, Any]] = []
    location_items: list[dict[str, Any]] = []
    voice_items: list[dict[str, Any]] = []
    warnings: list[str] = []

    for row in rows:
        asset_type = str(row.get("asset_type") or "")
        asset_id = str(row.get("asset_id") or "")
        if asset_type == "character":
            record = character_map.get(asset_id)
            if record is None:
                warnings.append(f"角色资产不存在: {asset_id}")
                continue
            character_items.append({
                **row,
                "prompt_template": record.prompt_template,
                "description": record.description,
                "reference_image_url": record.reference_image_url,
                "default_voice_id": record.default_voice_id,
            })
            continue
        if asset_type == "location":
            record = location_map.get(asset_id)
            if record is None:
                warnings.append(f"地点资产不存在: {asset_id}")
                continue
            location_items.append({
                **row,
                "prompt_template": record.prompt_template,
                "description": record.description,
                "reference_image_url": record.reference_image_url,
            })
            continue
        if asset_type == "voice":
            record = voice_map.get(asset_id)
            if record is None:
                warnings.append(f"语音资产不存在: {asset_id}")
                continue
            voice_items.append({
                **row,
                "provider": record.provider,
                "voice_code": record.voice_code,
                "language": record.language,
                "gender": record.gender,
                "style_prompt": record.style_prompt,
                "sample_audio_url": record.sample_audio_url,
            })

    def _line(prefix: str, value: str | None) -> str | None:
        text = _clean_text(value)
        return f"{prefix}{text}" if text else None

    base_prompt = _clean_text(panel.visual_prompt) or _clean_text(panel.script_text) or _clean_text(panel.title)
    extra_lines: list[str] = []
    for item in character_items:
        line = _line(f"Character[{item['entity_name']}]: ", item.get("prompt_template") or item.get("description"))
        if line:
            extra_lines.append(line)
    for item in location_items:
        line = _line(f"Location[{item['entity_name']}]: ", item.get("prompt_template") or item.get("description"))
        if line:
            extra_lines.append(line)
    prompt_parts = [part for part in [base_prompt, *extra_lines] if _clean_text(part)]
    effective_visual_prompt = "\n".join(prompt_parts).strip() or None

    primary_character = _pick_primary(character_items, asset_type="character")
    primary_location = _pick_primary(location_items, asset_type="location")
    primary_voice = _pick_primary(voice_items, asset_type="voice")

    effective_reference_image_url = (
        _clean_text(panel.reference_image_url)
        or _clean_text((primary_character or {}).get("reference_image_url"))
        or _clean_text((primary_location or {}).get("reference_image_url"))
        or None
    )
    effective_voice = (
        _effective_voice_payload_from_binding(primary_voice)
        if primary_voice
        else _effective_voice_payload_from_character_default(primary_character, voice_map, warnings)
    )

    compiled = {
        "panel_id": panel.id,
        "project_id": panel.project_id,
        "episode_id": panel.episode_id,
        "characters": character_items,
        "locations": location_items,
        "voices": voice_items,
        "effective_voice": effective_voice,
        "effective_reference_image_url": effective_reference_image_url,
        "effective_visual_prompt": effective_visual_prompt,
        "effective_negative_prompt": panel.negative_prompt,
        "effective_tts_text": (
            _clean_text(panel.tts_text)
            or _clean_text(panel.script_text)
            or _clean_text(panel.title)
            or None
        ),
        "trace": {
            "warnings": warnings,
            "compiled_at": datetime.now(timezone.utc).isoformat(),
            "compiler_version": COMPILER_VERSION,
        },
    }

    encoded = json.dumps(compiled, ensure_ascii=False, sort_keys=True)
    compiled_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    row = (await db.execute(
        select(PanelEffectiveBinding).where(PanelEffectiveBinding.panel_id == panel.id)
    )).scalar_one_or_none()
    if row is None:
        row = PanelEffectiveBinding(
            panel_id=panel.id,
            compiled_json=to_json_text(compiled),
            compiled_hash=compiled_hash,
            compiler_version=COMPILER_VERSION,
            compiled_at=datetime.now(timezone.utc),
        )
        db.add(row)
    else:
        row.compiled_json = to_json_text(compiled)
        row.compiled_hash = compiled_hash
        row.compiler_version = COMPILER_VERSION
        row.compiled_at = datetime.now(timezone.utc)

    await db.flush()
    return compiled


async def compile_panel_effective_binding_by_id(panel_id: str, db: AsyncSession) -> dict[str, Any]:
    panel = (await db.execute(select(Panel).where(Panel.id == panel_id))).scalar_one_or_none()
    if panel is None:
        raise ValueError("panel not found")
    return await compile_panel_effective_binding(panel, db)


async def compile_project_effective_bindings(project_id: str, db: AsyncSession) -> dict[str, int]:
    panels = (await db.execute(
        select(Panel).where(Panel.project_id == project_id).order_by(Panel.created_at, Panel.panel_order)
    )).scalars().all()
    compiled_count = 0
    for panel in panels:
        await compile_panel_effective_binding(panel, db)
        compiled_count += 1
    return {"panel_count": len(panels), "compiled_count": compiled_count}


async def get_panel_effective_binding(
    panel_id: str,
    db: AsyncSession,
    *,
    auto_compile: bool = True,
) -> dict[str, Any] | None:
    row = (await db.execute(
        select(PanelEffectiveBinding).where(PanelEffectiveBinding.panel_id == panel_id)
    )).scalar_one_or_none()
    should_compile = row is None or row.compiler_version != COMPILER_VERSION
    if should_compile and auto_compile:
        try:
            return await compile_panel_effective_binding_by_id(panel_id, db)
        except ValueError:
            return None
    if row is None:
        return None
    value = from_json_text(row.compiled_json, {})
    return value if isinstance(value, dict) else None
