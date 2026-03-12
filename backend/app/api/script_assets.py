from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import get_episode_or_404, get_panel_or_404, get_project_or_404
from app.api.response_utils import isoformat_or_empty, json_dict_or_empty
from app.database import get_db
from app.models import (
    EpisodeAssetOverride,
    GlobalCharacter,
    GlobalLocation,
    GlobalVoice,
    Panel,
    PanelAssetOverride,
    ScriptEntity,
    ScriptEntityAssetBinding,
)
from app.schemas.common import ApiResponse
from app.services.json_codec import to_json_text
from app.services.script_asset_compiler import (
    compile_panel_effective_binding_by_id,
    compile_project_effective_bindings,
    get_panel_effective_binding,
)

router = APIRouter(tags=["剧本资产绑定"])

SUPPORTED_ENTITY_TYPES = {"character", "location", "speaker"}
SUPPORTED_ASSET_TYPES = {"character", "location", "voice"}
ASSET_MODEL_BY_TYPE = {
    "character": GlobalCharacter,
    "location": GlobalLocation,
    "voice": GlobalVoice,
}
ASSET_LABEL_BY_TYPE = {
    "character": "角色",
    "location": "地点",
    "voice": "语音",
}


class AssetBindingPayload(BaseModel):
    asset_type: Literal["character", "location", "voice"]
    asset_id: str = Field(min_length=1, max_length=36)
    asset_name: str | None = Field(default=None, max_length=200)
    role_tag: str | None = Field(default=None, max_length=100)
    priority: int = 0
    is_primary: bool = False
    strategy: dict[str, Any] | None = None


class ScriptEntityCreate(BaseModel):
    entity_type: Literal["character", "location", "speaker"]
    name: str = Field(min_length=1, max_length=120)
    alias: str | None = Field(default=None, max_length=120)
    description: str | None = None
    meta: dict[str, Any] | None = None
    bindings: list[AssetBindingPayload] = Field(default_factory=list)


class ScriptEntityUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    alias: str | None = Field(default=None, max_length=120)
    description: str | None = None
    meta: dict[str, Any] | None = None


class ScriptEntityBindingReplace(BaseModel):
    bindings: list[AssetBindingPayload] = Field(default_factory=list)


class ScopedAssetOverridePayload(BaseModel):
    entity_id: str = Field(min_length=1, max_length=36)
    asset_type: Literal["character", "location", "voice"]
    asset_id: str = Field(min_length=1, max_length=36)
    asset_name: str | None = Field(default=None, max_length=200)
    role_tag: str | None = Field(default=None, max_length=100)
    priority: int = 0
    is_primary: bool = False
    strategy: dict[str, Any] | None = None


class EpisodeOverrideReplace(BaseModel):
    overrides: list[ScopedAssetOverridePayload] = Field(default_factory=list)


class PanelOverrideReplace(BaseModel):
    overrides: list[ScopedAssetOverridePayload] = Field(default_factory=list)


def _normalize_role(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _normalize_bindings(items: list[AssetBindingPayload]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for idx, item in enumerate(items):
        asset_type = str(item.asset_type).strip().lower()
        if asset_type not in SUPPORTED_ASSET_TYPES:
            raise HTTPException(status_code=400, detail=f"不支持的资产类型: {item.asset_type}")
        asset_id = str(item.asset_id).strip()
        if not asset_id:
            raise HTTPException(status_code=400, detail="asset_id 不能为空")
        role_tag = _normalize_role(item.role_tag)
        key = (asset_type, asset_id, role_tag or "")
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "asset_type": asset_type,
            "asset_id": asset_id,
            "asset_name": (item.asset_name or "").strip() or None,
            "role_tag": role_tag,
            "priority": int(item.priority if item.priority is not None else idx),
            "is_primary": bool(item.is_primary),
            "strategy_json": to_json_text(item.strategy) if item.strategy else None,
        })
    _ensure_primary(rows)
    return rows


def _normalize_overrides(items: list[ScopedAssetOverridePayload]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for idx, item in enumerate(items):
        entity_id = str(item.entity_id).strip()
        if not entity_id:
            raise HTTPException(status_code=400, detail="entity_id 不能为空")
        asset_type = str(item.asset_type).strip().lower()
        if asset_type not in SUPPORTED_ASSET_TYPES:
            raise HTTPException(status_code=400, detail=f"不支持的资产类型: {item.asset_type}")
        asset_id = str(item.asset_id).strip()
        if not asset_id:
            raise HTTPException(status_code=400, detail="asset_id 不能为空")
        role_tag = _normalize_role(item.role_tag)
        key = (entity_id, asset_type, asset_id, role_tag or "")
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "entity_id": entity_id,
            "asset_type": asset_type,
            "asset_id": asset_id,
            "asset_name": (item.asset_name or "").strip() or None,
            "role_tag": role_tag,
            "priority": int(item.priority if item.priority is not None else idx),
            "is_primary": bool(item.is_primary),
            "strategy_json": to_json_text(item.strategy) if item.strategy else None,
        })
    _ensure_primary(rows, scope_key="entity_id")
    return rows


def _ensure_primary(rows: list[dict[str, Any]], *, scope_key: str | None = None) -> None:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        scope = str(row.get(scope_key) or "") if scope_key else ""
        grouped.setdefault((scope, str(row["asset_type"])), []).append(row)
    for (_, _), group in grouped.items():
        group.sort(key=lambda item: (0 if bool(item["is_primary"]) else 1, int(item["priority"] or 0)))
        primary = next((item for item in group if bool(item["is_primary"])), None) or group[0]
        for item in group:
            item["is_primary"] = item is primary


async def _validate_asset_rows_for_project(
    db: AsyncSession,
    *,
    project_id: str,
    rows: list[dict[str, Any]],
) -> None:
    grouped_ids: dict[str, set[str]] = {}
    for row in rows:
        asset_type = str(row.get("asset_type") or "").strip().lower()
        asset_id = str(row.get("asset_id") or "").strip()
        if asset_type and asset_id:
            grouped_ids.setdefault(asset_type, set()).add(asset_id)

    for asset_type, asset_ids in grouped_ids.items():
        model = ASSET_MODEL_BY_TYPE[asset_type]
        label = ASSET_LABEL_BY_TYPE[asset_type]
        matches = (await db.execute(
            select(model.id, model.project_id).where(model.id.in_(list(asset_ids)))
        )).all()
        found_ids = {asset_id for asset_id, _project_id in matches}
        missing_ids = sorted(asset_ids - found_ids)
        if missing_ids:
            raise HTTPException(status_code=400, detail=f"包含不存在的{label}资产ID: {', '.join(missing_ids)}")

        foreign_ids = sorted(
            asset_id
            for asset_id, asset_project_id in matches
            if asset_project_id and asset_project_id != project_id
        )
        if foreign_ids:
            raise HTTPException(status_code=400, detail=f"包含不属于当前项目的{label}资产ID: {', '.join(foreign_ids)}")


def _binding_dict(item: ScriptEntityAssetBinding) -> dict[str, Any]:
    return {
        "id": item.id,
        "entity_id": item.entity_id,
        "asset_type": item.asset_type,
        "asset_id": item.asset_id,
        "asset_name": item.asset_name,
        "role_tag": item.role_tag,
        "priority": int(item.priority or 0),
        "is_primary": bool(item.is_primary),
        "strategy": json_dict_or_empty(item.strategy_json),
        "created_at": isoformat_or_empty(item.created_at),
        "updated_at": isoformat_or_empty(item.updated_at),
    }


def _entity_dict(item: ScriptEntity, bindings: list[ScriptEntityAssetBinding]) -> dict[str, Any]:
    return {
        "id": item.id,
        "project_id": item.project_id,
        "entity_type": item.entity_type,
        "name": item.name,
        "alias": item.alias,
        "description": item.description,
        "meta": json_dict_or_empty(item.meta_json),
        "bindings": [_binding_dict(row) for row in sorted(bindings, key=lambda x: (x.asset_type, x.priority, x.id))],
        "created_at": isoformat_or_empty(item.created_at),
        "updated_at": isoformat_or_empty(item.updated_at),
    }


def _override_dict(item: EpisodeAssetOverride | PanelAssetOverride) -> dict[str, Any]:
    return {
        "id": item.id,
        "entity_id": item.entity_id,
        "asset_type": item.asset_type,
        "asset_id": item.asset_id,
        "asset_name": item.asset_name,
        "role_tag": item.role_tag,
        "priority": int(item.priority or 0),
        "is_primary": bool(item.is_primary),
        "strategy": json_dict_or_empty(item.strategy_json),
        "created_at": isoformat_or_empty(item.created_at),
        "updated_at": isoformat_or_empty(item.updated_at),
    }


async def _get_entity_or_404(entity_id: str, db: AsyncSession) -> ScriptEntity:
    row = (await db.execute(select(ScriptEntity).where(ScriptEntity.id == entity_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="剧本实体不存在")
    return row


@router.get("/projects/{project_id}/script-assets/entities", response_model=ApiResponse[dict])
async def list_script_entities(project_id: str, db: AsyncSession = Depends(get_db)):
    await get_project_or_404(project_id, db)
    entities = (await db.execute(
        select(ScriptEntity)
        .where(ScriptEntity.project_id == project_id)
        .order_by(ScriptEntity.entity_type, ScriptEntity.name, ScriptEntity.created_at)
    )).scalars().all()
    if not entities:
        return ApiResponse(data={"items": []})
    entity_ids = [item.id for item in entities]
    bindings = (await db.execute(
        select(ScriptEntityAssetBinding)
        .where(ScriptEntityAssetBinding.entity_id.in_(entity_ids))
        .order_by(
            ScriptEntityAssetBinding.asset_type,
            ScriptEntityAssetBinding.priority,
            ScriptEntityAssetBinding.created_at,
        )
    )).scalars().all()
    binding_map: dict[str, list[ScriptEntityAssetBinding]] = {}
    for row in bindings:
        binding_map.setdefault(row.entity_id, []).append(row)
    return ApiResponse(data={"items": [_entity_dict(item, binding_map.get(item.id, [])) for item in entities]})


@router.post("/projects/{project_id}/script-assets/entities", response_model=ApiResponse[dict])
async def create_script_entity(project_id: str, body: ScriptEntityCreate, db: AsyncSession = Depends(get_db)):
    await get_project_or_404(project_id, db)
    entity_type = str(body.entity_type).strip().lower()
    if entity_type not in SUPPORTED_ENTITY_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的实体类型: {body.entity_type}")
    entity = ScriptEntity(
        project_id=project_id,
        entity_type=entity_type,
        name=body.name.strip(),
        alias=(body.alias or "").strip() or None,
        description=(body.description or "").strip() or None,
        meta_json=to_json_text(body.meta) if body.meta else None,
    )
    db.add(entity)
    await db.flush()

    rows = _normalize_bindings(body.bindings)
    await _validate_asset_rows_for_project(db, project_id=project_id, rows=rows)
    for item in rows:
        db.add(ScriptEntityAssetBinding(
            project_id=project_id,
            entity_id=entity.id,
            asset_type=item["asset_type"],
            asset_id=item["asset_id"],
            asset_name=item["asset_name"],
            role_tag=item["role_tag"],
            priority=item["priority"],
            is_primary=item["is_primary"],
            strategy_json=item["strategy_json"],
        ))

    await compile_project_effective_bindings(project_id, db)
    await db.commit()
    await db.refresh(entity)
    bindings = (await db.execute(
        select(ScriptEntityAssetBinding).where(ScriptEntityAssetBinding.entity_id == entity.id)
    )).scalars().all()
    return ApiResponse(data=_entity_dict(entity, bindings))


@router.put("/script-assets/entities/{entity_id}", response_model=ApiResponse[dict])
async def update_script_entity(entity_id: str, body: ScriptEntityUpdate, db: AsyncSession = Depends(get_db)):
    entity = await _get_entity_or_404(entity_id, db)
    updates = body.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        name = str(updates["name"]).strip()
        if not name:
            raise HTTPException(status_code=400, detail="实体名称不能为空")
        entity.name = name
    if "alias" in updates:
        entity.alias = (str(updates["alias"]).strip() if updates["alias"] is not None else "") or None
    if "description" in updates:
        entity.description = (str(updates["description"]).strip() if updates["description"] is not None else "") or None
    if "meta" in updates:
        entity.meta_json = to_json_text(updates["meta"]) if updates["meta"] else None
    entity.updated_at = datetime.now(timezone.utc)
    await compile_project_effective_bindings(entity.project_id, db)
    await db.commit()
    await db.refresh(entity)
    bindings = (await db.execute(
        select(ScriptEntityAssetBinding).where(ScriptEntityAssetBinding.entity_id == entity.id)
    )).scalars().all()
    return ApiResponse(data=_entity_dict(entity, bindings))


@router.delete("/script-assets/entities/{entity_id}", response_model=ApiResponse[None])
async def delete_script_entity(entity_id: str, db: AsyncSession = Depends(get_db)):
    entity = await _get_entity_or_404(entity_id, db)
    project_id = entity.project_id
    await db.delete(entity)
    await compile_project_effective_bindings(project_id, db)
    await db.commit()
    return ApiResponse(data=None)


@router.get("/script-assets/entities/{entity_id}/bindings", response_model=ApiResponse[dict])
async def get_script_entity_bindings(entity_id: str, db: AsyncSession = Depends(get_db)):
    entity = await _get_entity_or_404(entity_id, db)
    rows = (await db.execute(
        select(ScriptEntityAssetBinding)
        .where(ScriptEntityAssetBinding.entity_id == entity.id)
        .order_by(
            ScriptEntityAssetBinding.asset_type,
            ScriptEntityAssetBinding.priority,
            ScriptEntityAssetBinding.created_at,
        )
    )).scalars().all()
    return ApiResponse(data={"entity_id": entity.id, "bindings": [_binding_dict(item) for item in rows]})


@router.put("/script-assets/entities/{entity_id}/bindings", response_model=ApiResponse[dict])
async def replace_script_entity_bindings(
    entity_id: str,
    body: ScriptEntityBindingReplace,
    db: AsyncSession = Depends(get_db),
):
    entity = await _get_entity_or_404(entity_id, db)
    rows = _normalize_bindings(body.bindings)
    await _validate_asset_rows_for_project(db, project_id=entity.project_id, rows=rows)
    await db.execute(delete(ScriptEntityAssetBinding).where(ScriptEntityAssetBinding.entity_id == entity.id))
    for item in rows:
        db.add(ScriptEntityAssetBinding(
            project_id=entity.project_id,
            entity_id=entity.id,
            asset_type=item["asset_type"],
            asset_id=item["asset_id"],
            asset_name=item["asset_name"],
            role_tag=item["role_tag"],
            priority=item["priority"],
            is_primary=item["is_primary"],
            strategy_json=item["strategy_json"],
        ))
    await compile_project_effective_bindings(entity.project_id, db)
    await db.commit()
    return await get_script_entity_bindings(entity.id, db)


@router.get("/episodes/{episode_id}/asset-overrides", response_model=ApiResponse[dict])
async def get_episode_asset_overrides(episode_id: str, db: AsyncSession = Depends(get_db)):
    episode = await get_episode_or_404(episode_id, db)
    rows = (await db.execute(
        select(EpisodeAssetOverride)
        .where(EpisodeAssetOverride.episode_id == episode.id)
        .order_by(EpisodeAssetOverride.entity_id, EpisodeAssetOverride.asset_type, EpisodeAssetOverride.priority)
    )).scalars().all()
    return ApiResponse(data={"episode_id": episode.id, "overrides": [_override_dict(item) for item in rows]})


@router.put("/episodes/{episode_id}/asset-overrides", response_model=ApiResponse[dict])
async def replace_episode_asset_overrides(
    episode_id: str,
    body: EpisodeOverrideReplace,
    db: AsyncSession = Depends(get_db),
):
    episode = await get_episode_or_404(episode_id, db)
    rows = _normalize_overrides(body.overrides)

    entity_ids = {item["entity_id"] for item in rows}
    if entity_ids:
        entities = (await db.execute(
            select(ScriptEntity.id).where(
                ScriptEntity.id.in_(list(entity_ids)),
                ScriptEntity.project_id == episode.project_id,
            )
        )).scalars().all()
        missing = entity_ids - set(entities)
        if missing:
            raise HTTPException(status_code=400, detail=f"包含非法实体ID: {', '.join(sorted(missing))}")

    await _validate_asset_rows_for_project(db, project_id=episode.project_id, rows=rows)
    await db.execute(delete(EpisodeAssetOverride).where(EpisodeAssetOverride.episode_id == episode.id))
    for item in rows:
        db.add(EpisodeAssetOverride(
            episode_id=episode.id,
            entity_id=item["entity_id"],
            asset_type=item["asset_type"],
            asset_id=item["asset_id"],
            asset_name=item["asset_name"],
            role_tag=item["role_tag"],
            priority=item["priority"],
            is_primary=item["is_primary"],
            strategy_json=item["strategy_json"],
        ))
    panel_ids = (await db.execute(
        select(Panel.id).where(Panel.episode_id == episode.id)
    )).scalars().all()
    for panel_id in panel_ids:
        await compile_panel_effective_binding_by_id(panel_id, db)
    await db.commit()
    return await get_episode_asset_overrides(episode.id, db)


@router.get("/panels/{panel_id}/asset-overrides", response_model=ApiResponse[dict])
async def get_panel_asset_overrides(panel_id: str, db: AsyncSession = Depends(get_db)):
    panel = await get_panel_or_404(panel_id, db)
    rows = (await db.execute(
        select(PanelAssetOverride)
        .where(PanelAssetOverride.panel_id == panel.id)
        .order_by(PanelAssetOverride.entity_id, PanelAssetOverride.asset_type, PanelAssetOverride.priority)
    )).scalars().all()
    return ApiResponse(data={"panel_id": panel.id, "overrides": [_override_dict(item) for item in rows]})


@router.put("/panels/{panel_id}/asset-overrides", response_model=ApiResponse[dict])
async def replace_panel_asset_overrides(panel_id: str, body: PanelOverrideReplace, db: AsyncSession = Depends(get_db)):
    panel = await get_panel_or_404(panel_id, db)
    rows = _normalize_overrides(body.overrides)

    entity_ids = {item["entity_id"] for item in rows}
    if entity_ids:
        entities = (await db.execute(
            select(ScriptEntity.id).where(
                ScriptEntity.id.in_(list(entity_ids)),
                ScriptEntity.project_id == panel.project_id,
            )
        )).scalars().all()
        missing = entity_ids - set(entities)
        if missing:
            raise HTTPException(status_code=400, detail=f"包含非法实体ID: {', '.join(sorted(missing))}")

    await _validate_asset_rows_for_project(db, project_id=panel.project_id, rows=rows)
    await db.execute(delete(PanelAssetOverride).where(PanelAssetOverride.panel_id == panel.id))
    for item in rows:
        db.add(PanelAssetOverride(
            panel_id=panel.id,
            entity_id=item["entity_id"],
            asset_type=item["asset_type"],
            asset_id=item["asset_id"],
            asset_name=item["asset_name"],
            role_tag=item["role_tag"],
            priority=item["priority"],
            is_primary=item["is_primary"],
            strategy_json=item["strategy_json"],
        ))
    await compile_panel_effective_binding_by_id(panel.id, db)
    await db.commit()
    return await get_panel_asset_overrides(panel.id, db)


@router.post("/panels/{panel_id}/compile-bindings", response_model=ApiResponse[dict])
async def compile_panel_bindings(panel_id: str, db: AsyncSession = Depends(get_db)):
    await get_panel_or_404(panel_id, db)
    data = await compile_panel_effective_binding_by_id(panel_id, db)
    await db.commit()
    return ApiResponse(data=data)


@router.get("/panels/{panel_id}/effective-bindings", response_model=ApiResponse[dict])
async def read_panel_effective_bindings(panel_id: str, db: AsyncSession = Depends(get_db)):
    await get_panel_or_404(panel_id, db)
    data = await get_panel_effective_binding(panel_id, db, auto_compile=True)
    if data is None:
        raise HTTPException(status_code=404, detail="未找到分镜生效绑定")
    await db.commit()
    return ApiResponse(data=data)


@router.post("/projects/{project_id}/compile-bindings", response_model=ApiResponse[dict])
async def compile_project_bindings(project_id: str, db: AsyncSession = Depends(get_db)):
    await get_project_or_404(project_id, db)
    result = await compile_project_effective_bindings(project_id, db)
    await db.commit()
    return ApiResponse(data=result)
