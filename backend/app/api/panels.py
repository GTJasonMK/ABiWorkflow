from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.project_common import get_episode_or_404, get_project_or_404
from app.api.project_invalidation import invalidate_panel_generation_outputs
from app.api.response_utils import isoformat_or_empty, json_dict_or_none
from app.database import get_db
from app.models import Episode, GlobalVoice, Panel, PanelAssetOverride, Project, ScriptEntity, ScriptEntityAssetBinding
from app.panel_status import (
    PANEL_STATUS_COMPLETED,
    PANEL_STATUS_FAILED,
    PANEL_STATUS_PROCESSING,
)
from app.project_status import PROJECT_BUSY_STATUSES
from app.schemas.common import ApiResponse
from app.services.costing import record_usage_cost
from app.services.provider_gateway import query_provider_task_status, submit_provider_task
from app.services.script_asset_compiler import compile_panel_effective_binding, get_panel_effective_binding
from app.services.task_records import (
    create_task_record,
    get_task_record_by_source_id,
    serialize_task_record,
    update_task_record,
)
from app.task_record_status import (
    TASK_RECORD_STATUS_COMPLETED,
    TASK_RECORD_STATUS_FAILED,
    TASK_RECORD_STATUS_RUNNING,
)

router = APIRouter(tags=["分镜管理"])


class PanelAssetOverrideResponse(BaseModel):
    id: str
    panel_id: str
    entity_id: str
    asset_type: Literal["character", "location", "voice"]
    asset_id: str
    asset_name: str | None
    role_tag: str | None
    priority: int
    is_primary: bool
    strategy: dict[str, Any] | None
    created_at: str
    updated_at: str


class PanelCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    script_text: str | None = None
    visual_prompt: str | None = None
    negative_prompt: str | None = None
    duration_seconds: float = 5.0


class PanelUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=200)
    script_text: str | None = None
    visual_prompt: str | None = None
    negative_prompt: str | None = None
    camera_hint: str | None = None
    duration_seconds: float | None = None
    style_preset: str | None = None
    reference_image_url: str | None = None
    voice_id: str | None = None
    tts_text: str | None = None
    tts_audio_url: str | None = None
    video_url: str | None = None
    lipsync_video_url: str | None = None
    status: str | None = None


class PanelReorderRequest(BaseModel):
    panel_ids: list[str]


class ProviderSubmitRequest(BaseModel):
    provider_key: str
    payload: dict[str, Any] = Field(default_factory=dict)
    unit_price: float = 0.0
    model_name: str | None = None


class ProviderApplyRequest(BaseModel):
    result_url: str


class VoiceDesignRequest(BaseModel):
    mood: str | None = None
    speed: float | None = None
    pitch: float | None = None


class VoiceBindingRequest(BaseModel):
    voice_id: str | None = None
    entity_id: str | None = None
    role_tag: str | None = None
    binding: dict[str, Any] = Field(default_factory=dict)


class PanelResponse(BaseModel):
    id: str
    project_id: str
    episode_id: str
    panel_order: int
    title: str
    script_text: str | None
    visual_prompt: str | None
    negative_prompt: str | None
    camera_hint: str | None
    duration_seconds: float
    style_preset: str | None
    reference_image_url: str | None
    voice_id: str | None
    asset_overrides: list[PanelAssetOverrideResponse]
    effective_binding: dict[str, Any] | None
    tts_text: str | None
    tts_audio_url: str | None
    video_url: str | None
    lipsync_video_url: str | None
    provider_task_id: str | None
    status: str
    error_message: str | None
    created_at: str
    updated_at: str



def _normalize_role_tag(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


def _sorted_voice_overrides(panel: Panel) -> list[PanelAssetOverride]:
    return sorted(
        [item for item in panel.asset_overrides if item.asset_type == "voice"],
        key=lambda item: (
            0 if item.is_primary else 1,
            int(item.priority or 0),
            isoformat_or_empty(item.created_at),
            item.id,
        ),
    )


async def _resolve_speaker_entity_id(
    panel: Panel,
    *,
    db: AsyncSession,
    voice_id: str,
    explicit_entity_id: str | None,
) -> str:
    entity_id = (explicit_entity_id or "").strip() or None
    if entity_id:
        row = (await db.execute(
            select(ScriptEntity).where(
                ScriptEntity.id == entity_id,
                ScriptEntity.project_id == panel.project_id,
                ScriptEntity.entity_type == "speaker",
            )
        )).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=400, detail="entity_id 非法或不属于当前项目说话人实体")
        return row.id

    existing_primary = _sorted_voice_overrides(panel)
    if existing_primary:
        return existing_primary[0].entity_id

    matched_binding_entity_id = (await db.execute(
        select(ScriptEntityAssetBinding.entity_id)
        .join(ScriptEntity, ScriptEntity.id == ScriptEntityAssetBinding.entity_id)
        .where(
            ScriptEntityAssetBinding.project_id == panel.project_id,
            ScriptEntityAssetBinding.asset_type == "voice",
            ScriptEntityAssetBinding.asset_id == voice_id,
            ScriptEntity.project_id == panel.project_id,
            ScriptEntity.entity_type == "speaker",
        )
        .order_by(
            ScriptEntityAssetBinding.is_primary.desc(),
            ScriptEntityAssetBinding.priority.asc(),
            ScriptEntityAssetBinding.created_at.asc(),
        )
    )).scalars().first()
    if matched_binding_entity_id:
        return matched_binding_entity_id

    auto_entity = ScriptEntity(
        project_id=panel.project_id,
        entity_type="speaker",
        name=f"自动说话人-{voice_id[:6]}-{str(uuid.uuid4())[:4]}",
        description="由分镜语音绑定自动创建",
        meta_json=None,
    )
    db.add(auto_entity)
    await db.flush()
    return auto_entity.id


async def _replace_panel_voice_override(
    panel: Panel,
    *,
    db: AsyncSession,
    voice_id: str | None,
    strategy: dict[str, Any] | None,
    entity_id: str | None,
    role_tag: str | None = None,
) -> None:
    from app.services.json_codec import to_json_text

    for item in list(panel.asset_overrides):
        if item.asset_type == "voice":
            await db.delete(item)

    normalized_voice_id = (voice_id or "").strip() or None
    if normalized_voice_id:
        target_entity_id = await _resolve_speaker_entity_id(
            panel,
            db=db,
            voice_id=normalized_voice_id,
            explicit_entity_id=entity_id,
        )
        voice_name = (await db.execute(
            select(GlobalVoice.name).where(GlobalVoice.id == normalized_voice_id)
        )).scalar_one_or_none()
        db.add(PanelAssetOverride(
            panel_id=panel.id,
            entity_id=target_entity_id,
            asset_type="voice",
            asset_id=normalized_voice_id,
            asset_name=voice_name,
            role_tag=_normalize_role_tag(role_tag),
            priority=0,
            is_primary=True,
            strategy_json=to_json_text(strategy) if strategy else None,
        ))
        panel.voice_id = normalized_voice_id
    else:
        panel.voice_id = None

    await db.flush()
    await db.refresh(panel, attribute_names=["asset_overrides"])


def _to_asset_override_response(link: PanelAssetOverride) -> PanelAssetOverrideResponse:
    return PanelAssetOverrideResponse(
        id=link.id,
        panel_id=link.panel_id,
        entity_id=link.entity_id,
        asset_type=link.asset_type,  # type: ignore[arg-type]
        asset_id=link.asset_id,
        asset_name=link.asset_name,
        role_tag=link.role_tag,
        priority=int(link.priority or 0),
        is_primary=bool(link.is_primary),
        strategy=json_dict_or_none(link.strategy_json),
        created_at=isoformat_or_empty(link.created_at),
        updated_at=isoformat_or_empty(link.updated_at),
    )


def _loaded_panel_overrides(panel: Panel) -> list[PanelAssetOverride]:
    panel_state = sa_inspect(panel)
    if "asset_overrides" in panel_state.unloaded:
        return []
    return list(panel.asset_overrides)


def _sorted_panel_override_responses(panel: Panel) -> list[PanelAssetOverrideResponse]:
    overrides = sorted(
        _loaded_panel_overrides(panel),
        key=lambda item: (
            item.entity_id,
            item.asset_type,
            0 if item.is_primary else 1,
            int(item.priority or 0),
            item.id,
        ),
    )
    return [_to_asset_override_response(item) for item in overrides]


def _panel_effective_binding(panel: Panel) -> dict[str, Any] | None:
    panel_state = sa_inspect(panel)
    if "effective_binding" in panel_state.unloaded or panel.effective_binding is None:
        return None
    return json_dict_or_none(panel.effective_binding.compiled_json)  # type: ignore[arg-type]


def _to_panel_response(panel: Panel) -> PanelResponse:
    return PanelResponse(
        id=panel.id,
        project_id=panel.project_id,
        episode_id=panel.episode_id,
        panel_order=panel.panel_order,
        title=panel.title,
        script_text=panel.script_text,
        visual_prompt=panel.visual_prompt,
        negative_prompt=panel.negative_prompt,
        camera_hint=panel.camera_hint,
        duration_seconds=float(panel.duration_seconds or 0.0),
        style_preset=panel.style_preset,
        reference_image_url=panel.reference_image_url,
        voice_id=panel.voice_id,
        asset_overrides=_sorted_panel_override_responses(panel),
        effective_binding=_panel_effective_binding(panel),
        tts_text=panel.tts_text,
        tts_audio_url=panel.tts_audio_url,
        video_url=panel.video_url,
        lipsync_video_url=panel.lipsync_video_url,
        provider_task_id=panel.provider_task_id,
        status=panel.status,
        error_message=panel.error_message,
        created_at=isoformat_or_empty(panel.created_at),
        updated_at=isoformat_or_empty(panel.updated_at),
    )


def _panel_detail_options() -> tuple[Any, Any]:
    return (
        selectinload(Panel.asset_overrides),
        selectinload(Panel.effective_binding),
    )


async def _list_panels_with_details(
    db: AsyncSession,
    *,
    project_id: str | None = None,
    episode_id: str | None = None,
) -> list[Panel]:
    stmt = select(Panel).options(*_panel_detail_options())
    if project_id is not None:
        stmt = (
            stmt.join(Episode, Panel.episode_id == Episode.id)
            .where(Panel.project_id == project_id)
            .order_by(Episode.episode_order, Panel.panel_order, Panel.created_at)
        )
    elif episode_id is not None:
        stmt = stmt.where(Panel.episode_id == episode_id).order_by(Panel.panel_order, Panel.created_at)
    return (await db.execute(stmt)).scalars().all()


async def _get_panel_with_details_or_404(panel_id: str, db: AsyncSession) -> Panel:
    panel = (await db.execute(
        select(Panel).options(*_panel_detail_options()).where(Panel.id == panel_id)
    )).scalar_one_or_none()
    if panel is None:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return panel


async def _ensure_project_editable(project_id: str, db: AsyncSession, action: str) -> Project:
    project = await get_project_or_404(project_id, db)
    if project.status in PROJECT_BUSY_STATUSES:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许{action}")
    return project


@router.get("/projects/{project_id}/panels", response_model=ApiResponse[list[PanelResponse]])
async def list_project_panels(project_id: str, db: AsyncSession = Depends(get_db)):
    panels = await _list_panels_with_details(db, project_id=project_id)
    return ApiResponse(data=[_to_panel_response(item) for item in panels])


@router.get("/episodes/{episode_id}/panels", response_model=ApiResponse[list[PanelResponse]])
async def list_panels(episode_id: str, db: AsyncSession = Depends(get_db)):
    await get_episode_or_404(episode_id, db)
    panels = await _list_panels_with_details(db, episode_id=episode_id)
    return ApiResponse(data=[_to_panel_response(item) for item in panels])


@router.post("/episodes/{episode_id}/panels", response_model=ApiResponse[PanelResponse])
async def create_panel(episode_id: str, body: PanelCreate, db: AsyncSession = Depends(get_db)):
    episode = await get_episode_or_404(episode_id, db)
    await _ensure_project_editable(episode.project_id, db, "创建分镜")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="分镜标题不能为空")

    max_order = (await db.execute(
        select(func.coalesce(func.max(Panel.panel_order), -1)).where(Panel.episode_id == episode_id)
    )).scalar_one()
    panel = Panel(
        project_id=episode.project_id,
        episode_id=episode_id,
        panel_order=int(max_order or -1) + 1,
        title=title,
        script_text=(body.script_text or "").strip() or None,
        visual_prompt=(body.visual_prompt or "").strip() or None,
        negative_prompt=(body.negative_prompt or "").strip() or None,
        duration_seconds=max(0.1, float(body.duration_seconds)),
    )
    db.add(panel)
    await db.commit()
    await db.refresh(panel)
    from app.services.script_asset_compiler import compile_panel_effective_binding

    await compile_panel_effective_binding(panel, db)
    await db.commit()
    panel = await _get_panel_with_details_or_404(panel.id, db)
    return ApiResponse(data=_to_panel_response(panel))


@router.put("/episodes/{episode_id}/panels/reorder", response_model=ApiResponse[None])
async def reorder_panels(episode_id: str, body: PanelReorderRequest, db: AsyncSession = Depends(get_db)):
    episode = await get_episode_or_404(episode_id, db)
    await _ensure_project_editable(episode.project_id, db, "排序分镜")
    panels = (await db.execute(
        select(Panel).where(Panel.episode_id == episode_id)
    )).scalars().all()
    existing_ids = [item.id for item in panels]
    if len(body.panel_ids) != len(existing_ids) or set(body.panel_ids) != set(existing_ids):
        raise HTTPException(status_code=400, detail="panel_ids 必须完整覆盖当前分集分镜")
    mapping = {item.id: item for item in panels}
    for idx, panel_id in enumerate(body.panel_ids):
        mapping[panel_id].panel_order = idx
    await db.commit()
    return ApiResponse(data=None)


@router.get("/panels/{panel_id}", response_model=ApiResponse[PanelResponse])
async def get_panel(panel_id: str, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_with_details_or_404(panel_id, db)
    return ApiResponse(data=_to_panel_response(panel))


@router.put("/panels/{panel_id}", response_model=ApiResponse[PanelResponse])
async def update_panel(panel_id: str, body: PanelUpdate, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_with_details_or_404(panel_id, db)
    project = await _ensure_project_editable(panel.project_id, db, "编辑分镜")
    updates = body.model_dump(exclude_unset=True)

    changed_fields: set[str] = set()

    for key, value in updates.items():
        if key == "title" and value is not None:
            normalized = str(value).strip()
            if not normalized:
                raise HTTPException(status_code=400, detail="分镜标题不能为空")
            if panel.title != normalized:
                changed_fields.add("title")
            panel.title = normalized
            continue
        if key in {
            "script_text",
            "visual_prompt",
            "negative_prompt",
            "camera_hint",
            "style_preset",
            "reference_image_url",
            "tts_text",
            "tts_audio_url",
            "video_url",
            "lipsync_video_url",
        }:
            normalized = (str(value).strip() if isinstance(value, str) else value) or None
            if getattr(panel, key) != normalized:
                changed_fields.add(key)
            setattr(panel, key, normalized)
            continue
        if key == "duration_seconds" and value is not None:
            normalized_duration = max(0.1, float(value))
            if float(panel.duration_seconds or 0.0) != normalized_duration:
                changed_fields.add("duration_seconds")
            panel.duration_seconds = normalized_duration
            continue
        if getattr(panel, key) != value:
            changed_fields.add(key)
        setattr(panel, key, value)

    generation_affecting_fields = {
        "script_text",
        "visual_prompt",
        "negative_prompt",
        "camera_hint",
        "duration_seconds",
        "style_preset",
        "reference_image_url",
        "title",
    }
    if changed_fields & generation_affecting_fields:
        await invalidate_panel_generation_outputs(db, project=project, panel=panel)

    if "status" in changed_fields and updates.get("status") == PANEL_STATUS_COMPLETED:
        # 手动回写完成态时，不保留历史错误信息。
        panel.error_message = None

    if changed_fields:
        from app.services.script_asset_compiler import compile_panel_effective_binding

        await compile_panel_effective_binding(panel, db)

    await db.commit()
    await db.refresh(panel)
    panel = await _get_panel_with_details_or_404(panel.id, db)
    return ApiResponse(data=_to_panel_response(panel))


@router.delete("/panels/{panel_id}", response_model=ApiResponse[None])
async def delete_panel(panel_id: str, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_with_details_or_404(panel_id, db)
    await _ensure_project_editable(panel.project_id, db, "删除分镜")
    episode_id = panel.episode_id
    await db.delete(panel)
    await db.flush()

    remaining = (await db.execute(
        select(Panel).where(Panel.episode_id == episode_id).order_by(Panel.panel_order, Panel.created_at)
    )).scalars().all()
    for idx, item in enumerate(remaining):
        item.panel_order = idx
    await db.commit()
    return ApiResponse(data=None)


async def _submit_panel_provider_task(
    db: AsyncSession,
    *,
    panel: Panel,
    task_type: str,
    usage_type: str,
    body: ProviderSubmitRequest,
    payload: dict[str, Any],
) -> dict[str, Any]:
    submitted = await submit_provider_task(db, provider_key=body.provider_key, payload=payload)
    provider_task_id = submitted["task_id"]
    panel.provider_task_id = provider_task_id
    panel.status = PANEL_STATUS_PROCESSING
    panel.error_message = None

    record = await create_task_record(
        db,
        task_type=task_type,
        target_type="panel",
        target_id=panel.id,
        project_id=panel.project_id,
        episode_id=panel.episode_id,
        panel_id=panel.id,
        source_task_id=provider_task_id,
        status=TASK_RECORD_STATUS_RUNNING,
        progress_percent=0.0,
        message=f"{task_type} 已提交到 {body.provider_key}",
        payload={"provider_key": body.provider_key, "request": payload},
    )
    await record_usage_cost(
        db,
        provider_type=task_type,
        provider_name=body.provider_key,
        model_name=body.model_name,
        usage_type=usage_type,
        quantity=1.0,
        unit="request",
        unit_price=max(0.0, float(body.unit_price)),
        project_id=panel.project_id,
        episode_id=panel.episode_id,
        panel_id=panel.id,
        task_id=record.id,
    )
    await db.commit()
    await db.refresh(panel)
    return {
        "panel": _to_panel_response(panel).model_dump(),
        "task": serialize_task_record(record),
        "provider": submitted,
    }


def _map_provider_status_to_task_status(provider_status: str) -> str:
    return {
        "pending": TASK_RECORD_STATUS_RUNNING,
        "running": TASK_RECORD_STATUS_RUNNING,
        "completed": TASK_RECORD_STATUS_COMPLETED,
        "failed": TASK_RECORD_STATUS_FAILED,
        "cancelled": TASK_RECORD_STATUS_FAILED,
    }.get(provider_status, TASK_RECORD_STATUS_RUNNING)


async def _query_and_sync_panel_provider_status(
    db: AsyncSession,
    *,
    panel: Panel,
    provider_key: str,
    missing_task_detail: str,
) -> dict[str, Any]:
    if not panel.provider_task_id:
        raise HTTPException(status_code=400, detail=missing_task_detail)

    status_data = await query_provider_task_status(
        db,
        provider_key=provider_key,
        task_id=panel.provider_task_id,
    )
    task = await get_task_record_by_source_id(db, panel.provider_task_id)
    if task:
        await update_task_record(
            db,
            task=task,
            status=_map_provider_status_to_task_status(status_data["status"]),
            progress_percent=float(status_data.get("progress_percent") or 0.0),
            message=status_data.get("error_message") or f"provider={provider_key}",
            result={"provider_status": status_data},
            event_type="provider_status",
        )
    return status_data


def _apply_video_provider_status(panel: Panel, status_data: dict[str, Any]) -> None:
    if status_data["status"] == "completed":
        panel.status = PANEL_STATUS_COMPLETED
        return
    if status_data["status"] in {"failed", "cancelled"}:
        panel.status = PANEL_STATUS_FAILED
        panel.error_message = status_data.get("error_message")
        return
    panel.status = PANEL_STATUS_PROCESSING


async def _apply_panel_result_url(
    db: AsyncSession,
    *,
    panel: Panel,
    target_field: str,
    result_url: str,
) -> Panel:
    setattr(panel, target_field, result_url.strip())
    panel.status = PANEL_STATUS_COMPLETED
    panel.error_message = None
    await db.commit()
    await db.refresh(panel)
    return await _get_panel_with_details_or_404(panel.id, db)


async def _load_effective_panel_binding(
    panel: Panel,
    db: AsyncSession,
) -> dict[str, Any]:
    effective = await get_panel_effective_binding(panel.id, db, auto_compile=True) or {}
    return effective if isinstance(effective, dict) else {}



def _effective_voice_context(effective: dict[str, Any]) -> dict[str, Any]:
    voice = effective.get("effective_voice")
    return voice if isinstance(voice, dict) else {}



def _effective_voice_text(panel: Panel, effective: dict[str, Any]) -> str:
    text = effective.get("effective_tts_text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return (panel.tts_text or panel.script_text or panel.title or "").strip()



def _effective_voice_strategy(effective_voice: dict[str, Any]) -> dict[str, Any]:
    strategy = effective_voice.get("strategy")
    return dict(strategy) if isinstance(strategy, dict) else {}



def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _normalize_voice_binding_input(body: VoiceBindingRequest) -> tuple[str | None, str | None, dict[str, Any]]:
    strategy = dict(body.binding or {})
    entity_id = _optional_text(body.entity_id)
    role_tag = _optional_text(body.role_tag)
    if entity_id is None:
        entity_id = _optional_text(strategy.get("entity_id"))
    if role_tag is None:
        role_tag = _optional_text(strategy.get("role_tag"))
    strategy.pop("entity_id", None)
    strategy.pop("role_tag", None)
    return entity_id, role_tag, strategy


async def _compile_panel_binding_state(
    panel: Panel,
    db: AsyncSession,
    *,
    reload: bool = False,
) -> Panel:
    await compile_panel_effective_binding(panel, db)
    await db.commit()
    if not reload:
        return panel
    return await _get_panel_with_details_or_404(panel.id, db)


async def _ensure_panel_voice_override(
    panel: Panel,
    db: AsyncSession,
) -> PanelAssetOverride:
    voice_overrides = _sorted_voice_overrides(panel)
    if voice_overrides:
        return voice_overrides[0]

    effective = await _load_effective_panel_binding(panel, db)
    effective_voice = _effective_voice_context(effective)
    voice_id = _optional_text(effective_voice.get("voice_id"))
    if voice_id is None:
        raise HTTPException(status_code=400, detail="当前分镜未绑定语音，无法设计语音参数")

    await _replace_panel_voice_override(
        panel,
        db=db,
        voice_id=voice_id,
        strategy=_effective_voice_strategy(effective_voice),
        entity_id=_optional_text(effective_voice.get("entity_id")),
        role_tag=_optional_text(effective_voice.get("role_tag")),
    )
    panel = await _get_panel_with_details_or_404(panel.id, db)
    voice_overrides = _sorted_voice_overrides(panel)
    if not voice_overrides:
        raise HTTPException(status_code=500, detail="创建语音覆盖失败")
    return voice_overrides[0]



def _build_panel_tts_payload(
    panel: Panel,
    effective: dict[str, Any],
    extra_payload: dict[str, Any],
) -> dict[str, Any]:
    effective_voice = _effective_voice_context(effective)
    payload = {
        "text": _effective_voice_text(panel, effective),
        "voice_id": _optional_text(effective_voice.get("voice_id")) or panel.voice_id,
        "binding": _effective_voice_strategy(effective_voice),
        "voice_provider": _optional_text(effective_voice.get("provider")),
        "voice_code": _optional_text(effective_voice.get("voice_code")),
        **extra_payload,
    }
    return payload


def _effective_visual_prompt(panel: Panel, effective: dict[str, Any]) -> str:
    prompt = effective.get("effective_visual_prompt")
    if isinstance(prompt, str) and prompt.strip():
        return prompt.strip()
    return (panel.visual_prompt or panel.script_text or panel.title or "").strip()



def _effective_reference_image(panel: Panel, effective: dict[str, Any]) -> str | None:
    return _optional_text(effective.get("effective_reference_image_url")) or panel.reference_image_url



def _build_panel_video_payload(
    panel: Panel,
    effective: dict[str, Any],
    extra_payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "prompt": _effective_visual_prompt(panel, effective),
        "negative_prompt": panel.negative_prompt,
        "duration_seconds": panel.duration_seconds,
        "reference_image_url": _effective_reference_image(panel, effective),
        **extra_payload,
    }



def _build_panel_lipsync_payload(panel: Panel, extra_payload: dict[str, Any]) -> dict[str, Any]:
    if not panel.video_url:
        raise HTTPException(status_code=400, detail="请先提供原始视频（panel.video_url）")
    if not panel.tts_audio_url:
        raise HTTPException(status_code=400, detail="请先提供语音音频（panel.tts_audio_url）")
    return {
        "video_url": panel.video_url,
        "audio_url": panel.tts_audio_url,
        "panel_id": panel.id,
        **extra_payload,
    }


def _build_panel_lipsync_submit_payload(
    panel: Panel,
    _effective: dict[str, Any],
    extra_payload: dict[str, Any],
) -> dict[str, Any]:
    return _build_panel_lipsync_payload(panel, extra_payload)


async def _submit_panel_provider_request(
    db: AsyncSession,
    *,
    panel_id: str,
    body: ProviderSubmitRequest,
    task_type: str,
    usage_type: str,
    payload_builder: Callable[[Panel, dict[str, Any], dict[str, Any]], dict[str, Any]],
    load_effective_binding: bool = False,
) -> dict[str, Any]:
    panel = await _get_panel_with_details_or_404(panel_id, db)
    effective = await _load_effective_panel_binding(panel, db) if load_effective_binding else {}
    payload = payload_builder(panel, effective, body.payload)
    return await _submit_panel_provider_task(
        db,
        panel=panel,
        task_type=task_type,
        usage_type=usage_type,
        body=body,
        payload=payload,
    )


async def _get_panel_provider_status_response(
    db: AsyncSession,
    *,
    panel_id: str,
    provider_key: str,
    missing_task_detail: str,
    sync_panel_status: bool = False,
) -> dict[str, Any]:
    panel = await _get_panel_with_details_or_404(panel_id, db)
    status_data = await _query_and_sync_panel_provider_status(
        db,
        panel=panel,
        provider_key=provider_key,
        missing_task_detail=missing_task_detail,
    )
    if sync_panel_status:
        _apply_video_provider_status(panel, status_data)
        await db.commit()
        panel = await _get_panel_with_details_or_404(panel.id, db)
        return {
            "panel": _to_panel_response(panel).model_dump(),
            "provider_status": status_data,
        }
    await db.commit()
    return status_data


async def _apply_panel_provider_result_response(
    db: AsyncSession,
    *,
    panel_id: str,
    target_field: str,
    result_url: str,
) -> PanelResponse:
    panel = await _get_panel_with_details_or_404(panel_id, db)
    panel = await _apply_panel_result_url(db, panel=panel, target_field=target_field, result_url=result_url)
    return _to_panel_response(panel)


@router.post("/panels/{panel_id}/video/submit", response_model=ApiResponse[dict])
async def submit_panel_video(panel_id: str, body: ProviderSubmitRequest, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _submit_panel_provider_request(
        db,
        panel_id=panel_id,
        body=body,
        task_type="video",
        usage_type="panel_video_generate",
        payload_builder=_build_panel_video_payload,
        load_effective_binding=True,
    ))


@router.get("/panels/{panel_id}/video/status", response_model=ApiResponse[dict])
async def get_panel_video_status(panel_id: str, provider_key: str, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _get_panel_provider_status_response(
        db,
        panel_id=panel_id,
        provider_key=provider_key,
        missing_task_detail="该分镜尚未提交视频任务",
        sync_panel_status=True,
    ))


@router.post("/panels/{panel_id}/video/apply", response_model=ApiResponse[PanelResponse])
async def apply_panel_video(panel_id: str, body: ProviderApplyRequest, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _apply_panel_provider_result_response(
        db,
        panel_id=panel_id,
        target_field="video_url",
        result_url=body.result_url,
    ))


@router.post("/panels/{panel_id}/voice/analyze", response_model=ApiResponse[dict])
async def analyze_panel_voice(panel_id: str, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_with_details_or_404(panel_id, db)
    source_text = (panel.tts_text or panel.script_text or "").strip()
    length = len(source_text)
    sentence_count = max(1, source_text.count("。") + source_text.count("！") + source_text.count("？"))
    avg_chars = max(1, length // sentence_count)
    speaking_rate_cps = 4.5
    estimated_seconds = round(length / speaking_rate_cps, 2) if length else 0.0
    return ApiResponse(data={
        "panel_id": panel.id,
        "has_text": bool(source_text),
        "text_length": length,
        "sentence_count": sentence_count,
        "avg_chars_per_sentence": avg_chars,
        "estimated_seconds": estimated_seconds,
    })


@router.post("/panels/{panel_id}/voice/design", response_model=ApiResponse[dict])
async def design_panel_voice(panel_id: str, body: VoiceDesignRequest, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_with_details_or_404(panel_id, db)
    from app.services.json_codec import to_json_text

    target_override = await _ensure_panel_voice_override(panel, db)
    binding = json_dict_or_none(target_override.strategy_json) or {}
    if body.mood is not None:
        binding["mood"] = body.mood.strip()
    if body.speed is not None:
        binding["speed"] = float(body.speed)
    if body.pitch is not None:
        binding["pitch"] = float(body.pitch)
    binding["designed_at"] = datetime.now(timezone.utc).isoformat()
    target_override.strategy_json = to_json_text(binding) if binding else None

    await _compile_panel_binding_state(panel, db)
    return ApiResponse(data={
        "panel_id": panel.id,
        "voice_id": target_override.asset_id,
        "entity_id": target_override.entity_id,
        "binding": binding,
    })


@router.post("/panels/{panel_id}/voice/generate-lines", response_model=ApiResponse[dict])
async def generate_panel_voice_lines(panel_id: str, body: ProviderSubmitRequest, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _submit_panel_provider_request(
        db,
        panel_id=panel_id,
        body=body,
        task_type="tts",
        usage_type="panel_tts_generate",
        payload_builder=_build_panel_tts_payload,
        load_effective_binding=True,
    ))


@router.put("/panels/{panel_id}/voice/binding", response_model=ApiResponse[PanelResponse])
async def bind_panel_voice(panel_id: str, body: VoiceBindingRequest, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_with_details_or_404(panel_id, db)
    entity_id, role_tag, strategy = _normalize_voice_binding_input(body)

    await _replace_panel_voice_override(
        panel,
        db=db,
        voice_id=body.voice_id,
        strategy=strategy,
        entity_id=entity_id,
        role_tag=role_tag,
    )
    panel = await _compile_panel_binding_state(panel, db, reload=True)
    return ApiResponse(data=_to_panel_response(panel))


@router.post("/panels/{panel_id}/lipsync/submit", response_model=ApiResponse[dict])
async def submit_panel_lipsync(panel_id: str, body: ProviderSubmitRequest, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _submit_panel_provider_request(
        db,
        panel_id=panel_id,
        body=body,
        task_type="lipsync",
        usage_type="panel_lipsync_generate",
        payload_builder=_build_panel_lipsync_submit_payload,
    ))


@router.get("/panels/{panel_id}/lipsync/status", response_model=ApiResponse[dict])
async def get_panel_lipsync_status(panel_id: str, provider_key: str, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _get_panel_provider_status_response(
        db,
        panel_id=panel_id,
        provider_key=provider_key,
        missing_task_detail="该分镜尚未提交口型同步任务",
    ))


@router.post("/panels/{panel_id}/lipsync/apply", response_model=ApiResponse[PanelResponse])
async def apply_panel_lipsync(panel_id: str, body: ProviderApplyRequest, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _apply_panel_provider_result_response(
        db,
        panel_id=panel_id,
        target_field="lipsync_video_url",
        result_url=body.result_url,
    ))
