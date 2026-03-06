from __future__ import annotations

import logging
import uuid
from typing import Any, Callable, Literal, TypeVar

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response_utils import isoformat_or_none
from app.config import resolve_runtime_path, settings
from app.database import get_db
from app.models import GlobalAssetFolder, GlobalCharacter, GlobalLocation, GlobalVoice, Project
from app.schemas.common import ApiResponse
from app.services.json_codec import from_json_text, to_json_text

router = APIRouter(prefix="/asset-hub", tags=["全局资产中心"])
logger = logging.getLogger(__name__)


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    folder_type: str = "generic"
    storage_path: str | None = None
    description: str | None = None


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    folder_type: str | None = None
    storage_path: str | None = None
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class VoiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = None
    provider: str = "edge-tts"
    voice_code: str = Field(min_length=1, max_length=200)
    folder_id: str | None = None
    language: str | None = None
    gender: str | None = None
    sample_audio_url: str | None = None
    style_prompt: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class VoiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    project_id: str | None = None
    provider: str | None = None
    voice_code: str | None = Field(default=None, min_length=1, max_length=200)
    folder_id: str | None = None
    language: str | None = None
    gender: str | None = None
    sample_audio_url: str | None = None
    style_prompt: str | None = None
    meta: dict[str, Any] | None = None
    is_active: bool | None = None


class GlobalCharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = None
    folder_id: str | None = None
    alias: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    reference_image_url: str | None = None
    default_voice_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class GlobalCharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    project_id: str | None = None
    folder_id: str | None = None
    alias: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    reference_image_url: str | None = None
    default_voice_id: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


class GlobalLocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    project_id: str | None = None
    folder_id: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    reference_image_url: str | None = None
    tags: list[str] = Field(default_factory=list)


class GlobalLocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    project_id: str | None = None
    folder_id: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    reference_image_url: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


class AssetDraftFromPanelRequest(BaseModel):
    asset_type: Literal["character", "location", "voice"]
    panel_title: str = Field(min_length=1, max_length=200)
    script_text: str | None = None
    visual_prompt: str | None = None
    tts_text: str | None = None
    reference_image_url: str | None = None
    source_voice_name: str | None = None
    source_voice_provider: str | None = None
    source_voice_code: str | None = None


class AssetDraftFromPanelResponse(BaseModel):
    name: str
    description: str | None = None
    prompt_template: str | None = None
    style_prompt: str | None = None
    generator: Literal["llm"]


class VoiceSampleGenerateRequest(BaseModel):
    sample_text: str | None = None


class _AssetDraftLlmResult(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    style_prompt: str | None = None


AssetRowT = TypeVar("AssetRowT", GlobalAssetFolder, GlobalCharacter, GlobalLocation, GlobalVoice)


def _clean_text(value: str | None) -> str:
    return (value or "").strip()


async def _generate_asset_draft_with_llm(body: AssetDraftFromPanelRequest) -> _AssetDraftLlmResult:
    from app.llm.base import Message
    from app.llm.factory import create_llm_adapter
    from app.services.llm_json import extract_json_object

    context_lines = [
        f"资产类型: {body.asset_type}",
        f"分镜标题: {_clean_text(body.panel_title)}",
        f"分镜文本(script_text): {_clean_text(body.script_text)}",
        f"视频提示词(visual_prompt): {_clean_text(body.visual_prompt)}",
        f"配音文本(tts_text): {_clean_text(body.tts_text)}",
        f"参考图URL: {_clean_text(body.reference_image_url)}",
        f"源语音名称: {_clean_text(body.source_voice_name)}",
        f"源语音Provider: {_clean_text(body.source_voice_provider)}",
        f"源语音编码: {_clean_text(body.source_voice_code)}",
    ]
    system_prompt = (
        "你是资产生产流水线中的“资产提示词设计器”。\n"
        "目标：基于分镜内容，为资产创建可复用草案。\n"
        "输出必须是 JSON 对象，仅允许包含字段：name, description, prompt_template, style_prompt。\n"
        "规则：\n"
        "1) character/location 必须输出非空 prompt_template（用于文生图）；\n"
        "   voice 必须输出非空 style_prompt（用于语音风格）。\n"
        "2) name 简洁明确，中文命名。\n"
        "3) description 使用中文，概括资产用途与关键特征。\n"
        "4) prompt_template 优先英文，结构化描述主体、环境、光线、构图、风格。\n"
        "5) style_prompt 使用中文，突出语速、语气、情绪、停顿建议。\n"
        "6) 不要输出 markdown，不要输出额外字段。"
    )
    user_prompt = "请根据以下上下文生成资产草案：\n" + "\n".join(context_lines)

    llm = create_llm_adapter()
    try:
        response = await llm.complete(
            messages=[
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_prompt),
            ],
            response_format=_AssetDraftLlmResult,
            temperature=0.4,
        )
        parsed = extract_json_object(response.content)
        return _AssetDraftLlmResult.model_validate(parsed)
    finally:
        await llm.close()


def _coerce_asset_draft(
    body: AssetDraftFromPanelRequest,
    llm_draft: _AssetDraftLlmResult,
) -> AssetDraftFromPanelResponse:
    title = _clean_text(body.panel_title) or "未命名分镜"
    default_name = (
        f"{title}-角色"
        if body.asset_type == "character"
        else f"{title}-地点"
        if body.asset_type == "location"
        else f"{title}-语音"
    )
    name = _clean_text(llm_draft.name) or default_name
    description = _clean_text(llm_draft.description) or None
    prompt_template = _clean_text(llm_draft.prompt_template) or None
    style_prompt = _clean_text(llm_draft.style_prompt) or None

    if body.asset_type in {"character", "location"}:
        if not prompt_template:
            raise ValueError("LLM 未返回可用的 prompt_template")
        return AssetDraftFromPanelResponse(
            name=name,
            description=description,
            prompt_template=prompt_template,
            style_prompt=None,
            generator="llm",
        )

    if not style_prompt:
        raise ValueError("LLM 未返回可用的 style_prompt")
    return AssetDraftFromPanelResponse(
        name=name,
        description=description,
        prompt_template=None,
        style_prompt=style_prompt,
        generator="llm",
    )


def _folder_payload(item: GlobalAssetFolder) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "folder_type": item.folder_type,
        "storage_path": item.storage_path,
        "description": item.description,
        "sort_order": item.sort_order,
        "is_active": item.is_active,
        "created_at": isoformat_or_none(item.created_at),
        "updated_at": isoformat_or_none(item.updated_at),
    }


def _voice_payload(item: GlobalVoice) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "project_id": item.project_id,
        "provider": item.provider,
        "voice_code": item.voice_code,
        "folder_id": item.folder_id,
        "language": item.language,
        "gender": item.gender,
        "sample_audio_url": item.sample_audio_url,
        "style_prompt": item.style_prompt,
        "meta": from_json_text(item.meta_json, {}),
        "is_active": item.is_active,
        "created_at": isoformat_or_none(item.created_at),
        "updated_at": isoformat_or_none(item.updated_at),
    }


def _character_payload(item: GlobalCharacter) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "project_id": item.project_id,
        "folder_id": item.folder_id,
        "alias": item.alias,
        "description": item.description,
        "prompt_template": item.prompt_template,
        "reference_image_url": item.reference_image_url,
        "default_voice_id": item.default_voice_id,
        "tags": from_json_text(item.tags_json, []),
        "is_active": item.is_active,
        "created_at": isoformat_or_none(item.created_at),
        "updated_at": isoformat_or_none(item.updated_at),
    }


def _location_payload(item: GlobalLocation) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "project_id": item.project_id,
        "folder_id": item.folder_id,
        "description": item.description,
        "prompt_template": item.prompt_template,
        "reference_image_url": item.reference_image_url,
        "tags": from_json_text(item.tags_json, []),
        "is_active": item.is_active,
        "created_at": isoformat_or_none(item.created_at),
        "updated_at": isoformat_or_none(item.updated_at),
    }


async def _get_row_or_404(
    db: AsyncSession,
    model: type[AssetRowT],
    row_id: str,
    detail: str,
) -> AssetRowT:
    row = (await db.execute(select(model).where(model.id == row_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=detail)
    return row


async def _render_reference_image(
    db: AsyncSession,
    *,
    item: GlobalCharacter | GlobalLocation,
    payload_builder: Callable[[GlobalCharacter | GlobalLocation], dict[str, Any]],
    missing_prompt_detail: str,
    output_subdir: str,
    failure_label: str,
) -> dict[str, Any]:
    prompt = _clean_text(item.prompt_template)
    if not prompt:
        raise HTTPException(status_code=400, detail=missing_prompt_detail)

    from app.services.portrait_generator import generate_image_from_prompt

    try:
        image_url = await generate_image_from_prompt(item.id, prompt, output_subdir=output_subdir)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一抛前端，避免静默失败
        logger.exception("%s失败: id=%s, error=%s", failure_label, item.id, exc)
        raise HTTPException(status_code=502, detail=f"{failure_label}失败: {exc}") from exc

    item.reference_image_url = image_url
    await db.commit()
    await db.refresh(item)
    return payload_builder(item)


async def _render_visual_asset_reference(
    db: AsyncSession,
    *,
    row_id: str,
    model: type[GlobalCharacter] | type[GlobalLocation],
    detail: str,
    serializer: Callable[[GlobalCharacter | GlobalLocation], dict[str, Any]],
    missing_prompt_detail: str,
    output_subdir: str,
    failure_label: str,
) -> dict[str, Any]:
    item = await _get_row_or_404(db, model, row_id, detail)
    return await _render_reference_image(
        db,
        item=item,
        payload_builder=serializer,
        missing_prompt_detail=missing_prompt_detail,
        output_subdir=output_subdir,
        failure_label=failure_label,
    )


async def _ensure_folder_id(folder_id: str | None, db: AsyncSession) -> str | None:
    normalized = (folder_id or "").strip() or None
    if normalized is None:
        return None
    exists = (await db.execute(
        select(GlobalAssetFolder.id).where(GlobalAssetFolder.id == normalized)
    )).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=400, detail="关联资产目录不存在")
    return normalized


async def _ensure_project_id(project_id: str | None, db: AsyncSession) -> str | None:
    normalized = (project_id or "").strip() or None
    if normalized is None:
        return None
    exists = (await db.execute(
        select(Project.id).where(Project.id == normalized)
    )).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=400, detail="关联项目不存在")
    return normalized


async def _resolve_scoped_refs(
    db: AsyncSession,
    *,
    project_id: str | None,
    folder_id: str | None,
) -> dict[str, Any]:
    return {
        "project_id": await _ensure_project_id(project_id, db),
        "folder_id": await _ensure_folder_id(folder_id, db),
    }


def _build_voice_create_values(body: VoiceCreate) -> dict[str, Any]:
    return {
        "name": body.name.strip(),
        "provider": _clean_text(body.provider) or "edge-tts",
        "voice_code": body.voice_code.strip(),
        "language": _clean_text(body.language) or None,
        "gender": _clean_text(body.gender) or None,
        "sample_audio_url": _clean_text(body.sample_audio_url) or None,
        "style_prompt": _clean_text(body.style_prompt) or None,
        "meta_json": to_json_text(body.meta),
    }


def _build_visual_asset_create_values(
    body: GlobalCharacterCreate | GlobalLocationCreate,
) -> dict[str, Any]:
    return {
        "name": body.name.strip(),
        "description": _clean_text(body.description) or None,
        "prompt_template": _clean_text(body.prompt_template) or None,
        "reference_image_url": _clean_text(body.reference_image_url) or None,
        "tags_json": to_json_text(body.tags),
    }


def _build_character_create_values(body: GlobalCharacterCreate) -> dict[str, Any]:
    return {
        **_build_visual_asset_create_values(body),
        "alias": _clean_text(body.alias) or None,
        "default_voice_id": body.default_voice_id,
    }


def _build_location_create_values(body: GlobalLocationCreate) -> dict[str, Any]:
    return _build_visual_asset_create_values(body)


async def _create_scoped_asset(
    db: AsyncSession,
    *,
    project_id: str | None,
    folder_id: str | None,
    model: type[AssetRowT],
    serializer: Callable[[AssetRowT], dict[str, Any]],
    create_values: dict[str, Any],
) -> dict[str, Any]:
    scoped_refs = await _resolve_scoped_refs(db, project_id=project_id, folder_id=folder_id)
    entity = model(**scoped_refs, **create_values)
    db.add(entity)
    return await _save_and_serialize(db, entity, serializer)


async def _update_scoped_asset(
    db: AsyncSession,
    *,
    row_id: str,
    model: type[AssetRowT],
    detail: str,
    serializer: Callable[[AssetRowT], dict[str, Any]],
    updates: dict[str, Any],
    json_field_map: dict[str, tuple[str, Any]] | None = None,
) -> tuple[AssetRowT, dict[str, Any]]:
    entity = await _get_row_or_404(db, model, row_id, detail)
    normalized_updates = await _normalize_scoped_updates(db, updates)
    _apply_updates(entity, normalized_updates, json_field_map=json_field_map)
    return entity, await _save_and_serialize(db, entity, serializer)


async def _create_visual_asset(
    db: AsyncSession,
    *,
    body: GlobalCharacterCreate | GlobalLocationCreate,
    model: type[GlobalCharacter] | type[GlobalLocation],
    serializer: Callable[[GlobalCharacter | GlobalLocation], dict[str, Any]],
    create_values: dict[str, Any],
) -> dict[str, Any]:
    return await _create_scoped_asset(
        db,
        project_id=body.project_id,
        folder_id=body.folder_id,
        model=model,
        serializer=serializer,
        create_values=create_values,
    )


async def _update_visual_asset(
    db: AsyncSession,
    *,
    row_id: str,
    body: GlobalCharacterUpdate | GlobalLocationUpdate,
    model: type[GlobalCharacter] | type[GlobalLocation],
    detail: str,
    serializer: Callable[[GlobalCharacter | GlobalLocation], dict[str, Any]],
    empty_name_detail: str,
) -> dict[str, Any]:
    entity, payload = await _update_scoped_asset(
        db,
        row_id=row_id,
        model=model,
        detail=detail,
        serializer=serializer,
        updates=body.model_dump(exclude_unset=True),
        json_field_map={"tags": ("tags_json", [])},
    )
    if not entity.name:
        raise HTTPException(status_code=400, detail=empty_name_detail)
    return payload


def _folder_order_stmt():
    return select(GlobalAssetFolder).order_by(GlobalAssetFolder.sort_order, GlobalAssetFolder.created_at)



def _build_folder_create_values(body: FolderCreate) -> dict[str, Any]:
    return {
        "name": body.name.strip(),
        "folder_type": _clean_text(body.folder_type) or "generic",
        "storage_path": _clean_text(body.storage_path) or None,
        "description": _clean_text(body.description) or None,
    }


async def _list_scoped_rows(
    db: AsyncSession,
    model: type[AssetRowT],
    *,
    scope: Literal["all", "global", "project"],
    project_id: str | None,
) -> list[AssetRowT]:
    normalized_project_id = await _ensure_project_id(project_id, db)
    stmt = select(model).order_by(model.created_at)
    scoped = _scope_condition(model.project_id, scope, normalized_project_id)
    if scoped is not None:
        stmt = stmt.where(scoped)
    return (await db.execute(stmt)).scalars().all()


async def _normalize_scoped_updates(db: AsyncSession, updates: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(updates)
    if "folder_id" in normalized:
        normalized["folder_id"] = await _ensure_folder_id(normalized["folder_id"], db)
    if "project_id" in normalized:
        normalized["project_id"] = await _ensure_project_id(normalized["project_id"], db)
    return normalized


def _apply_updates(
    entity: Any,
    updates: dict[str, Any],
    *,
    json_field_map: dict[str, tuple[str, Any]] | None = None,
) -> None:
    field_map = json_field_map or {}
    for key, value in updates.items():
        if key in field_map:
            target_field, default_value = field_map[key]
            setattr(entity, target_field, to_json_text(value if value is not None else default_value))
            continue
        if isinstance(value, str):
            setattr(entity, key, value.strip() or None)
            continue
        setattr(entity, key, value)


async def _save_and_serialize(
    db: AsyncSession,
    entity: AssetRowT,
    serializer: Callable[[AssetRowT], dict[str, Any]],
) -> dict[str, Any]:
    await db.commit()
    await db.refresh(entity)
    return serializer(entity)


async def _delete_row(
    db: AsyncSession,
    model: type[AssetRowT],
    row_id: str,
    detail: str,
) -> None:
    entity = await _get_row_or_404(db, model, row_id, detail)
    await db.delete(entity)
    await db.commit()


def _scope_condition(
    project_column,
    scope: Literal["all", "global", "project"],
    project_id: str | None,
):
    if scope == "global":
        return project_column.is_(None)
    if scope == "project":
        if not project_id:
            raise HTTPException(status_code=400, detail="scope=project 时必须提供 project_id")
        return project_column == project_id
    if scope == "all":
        if not project_id:
            return None
        return or_(project_column.is_(None), project_column == project_id)
    raise HTTPException(status_code=400, detail="scope 参数非法")


@router.get("/overview", response_model=ApiResponse[dict])
async def get_asset_hub_overview(
    project_id: str | None = None,
    scope: Literal["all", "global", "project"] = "all",
    db: AsyncSession = Depends(get_db),
):
    folders = (await db.execute(_folder_order_stmt())).scalars().all()
    characters = await _list_scoped_rows(db, GlobalCharacter, scope=scope, project_id=project_id)
    locations = await _list_scoped_rows(db, GlobalLocation, scope=scope, project_id=project_id)
    voices = await _list_scoped_rows(db, GlobalVoice, scope=scope, project_id=project_id)
    return ApiResponse(data={
        "folders": [_folder_payload(item) for item in folders],
        "characters": [_character_payload(item) for item in characters],
        "locations": [_location_payload(item) for item in locations],
        "voices": [_voice_payload(item) for item in voices],
    })


@router.post("/drafts/from-panel", response_model=ApiResponse[dict])
async def generate_asset_draft_from_panel(body: AssetDraftFromPanelRequest):
    if not settings.llm_api_key.strip():
        raise HTTPException(status_code=400, detail="未配置 LLM_API_KEY，无法生成资产提示词草案")
    try:
        draft_from_llm = await _generate_asset_draft_with_llm(body)
        draft = _coerce_asset_draft(body, draft_from_llm)
        return ApiResponse(data=draft.model_dump())
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一抛给前端，避免静默降级
        logger.exception("资产提示词草案 LLM 生成失败: %s", exc)
        raise HTTPException(status_code=502, detail=f"LLM 生成资产提示词草案失败: {exc}") from exc


@router.post("/characters/{character_id}/render-reference", response_model=ApiResponse[dict])
async def render_global_character_reference(character_id: str, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _render_visual_asset_reference(
        db,
        row_id=character_id,
        model=GlobalCharacter,
        detail="全局角色不存在",
        serializer=_character_payload,
        missing_prompt_detail="角色提示词为空，无法生成参考图",
        output_subdir="asset-hub/characters",
        failure_label="角色参考图生成",
    ))


@router.post("/locations/{location_id}/render-reference", response_model=ApiResponse[dict])
async def render_global_location_reference(location_id: str, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _render_visual_asset_reference(
        db,
        row_id=location_id,
        model=GlobalLocation,
        detail="全局地点不存在",
        serializer=_location_payload,
        missing_prompt_detail="地点提示词为空，无法生成参考图",
        output_subdir="asset-hub/locations",
        failure_label="地点参考图生成",
    ))

@router.post("/voices/{voice_id}/render-sample", response_model=ApiResponse[dict])
async def render_global_voice_sample(
    voice_id: str,
    body: VoiceSampleGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    voice = (await db.execute(select(GlobalVoice).where(GlobalVoice.id == voice_id))).scalar_one_or_none()
    if voice is None:
        raise HTTPException(status_code=404, detail="语音不存在")

    provider = (voice.provider or "").strip().lower()
    if provider not in {"edge-tts", "edge_tts", "edge"}:
        raise HTTPException(status_code=400, detail="当前仅支持 edge-tts 语音样音生成")
    if not _clean_text(voice.voice_code):
        raise HTTPException(status_code=400, detail="voice_code 为空，无法生成样音")

    sample_text = _clean_text(body.sample_text) or _clean_text(voice.style_prompt) or "你好，这是一段语音资产样音。"
    if not sample_text:
        raise HTTPException(status_code=400, detail="样音文本为空，无法生成")

    from app.services.tts_service import TTSService

    output_dir = resolve_runtime_path(settings.video_output_dir) / "_asset_voice_samples"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_name = f"{voice.id}_{uuid.uuid4().hex[:8]}.mp3"
    output_path = output_dir / output_name

    try:
        tts = TTSService(voice=voice.voice_code)
        await tts.generate_audio(sample_text, output_path)
    except Exception as exc:  # noqa: BLE001 - 统一抛前端，避免静默失败
        logger.exception("语音样音生成失败: id=%s, error=%s", voice.id, exc)
        raise HTTPException(status_code=502, detail=f"语音样音生成失败: {exc}") from exc

    voice.sample_audio_url = f"/media/videos/_asset_voice_samples/{output_name}"
    await db.commit()
    await db.refresh(voice)
    return ApiResponse(data=_voice_payload(voice))


@router.get("/folders", response_model=ApiResponse[list[dict]])
async def list_asset_folders(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(_folder_order_stmt())).scalars().all()
    return ApiResponse(data=[_folder_payload(item) for item in rows])


@router.post("/folders", response_model=ApiResponse[dict])
async def create_asset_folder(body: FolderCreate, db: AsyncSession = Depends(get_db)):
    entity = GlobalAssetFolder(**_build_folder_create_values(body))
    db.add(entity)
    return ApiResponse(data=await _save_and_serialize(db, entity, _folder_payload))


@router.put("/folders/{folder_id}", response_model=ApiResponse[dict])
async def update_asset_folder(folder_id: str, body: FolderUpdate, db: AsyncSession = Depends(get_db)):
    entity = await _get_row_or_404(db, GlobalAssetFolder, folder_id, "资产目录不存在")
    _apply_updates(entity, body.model_dump(exclude_unset=True))
    if not entity.name:
        raise HTTPException(status_code=400, detail="资产目录名称不能为空")
    if not entity.folder_type:
        entity.folder_type = "generic"
    return ApiResponse(data=await _save_and_serialize(db, entity, _folder_payload))


@router.delete("/folders/{folder_id}", response_model=ApiResponse[None])
async def delete_asset_folder(folder_id: str, db: AsyncSession = Depends(get_db)):
    await _get_row_or_404(db, GlobalAssetFolder, folder_id, "资产目录不存在")
    await db.execute(update(GlobalVoice).where(GlobalVoice.folder_id == folder_id).values(folder_id=None))
    await db.execute(update(GlobalCharacter).where(GlobalCharacter.folder_id == folder_id).values(folder_id=None))
    await db.execute(update(GlobalLocation).where(GlobalLocation.folder_id == folder_id).values(folder_id=None))
    await _delete_row(db, GlobalAssetFolder, folder_id, "资产目录不存在")
    return ApiResponse(data=None)


@router.get("/voices", response_model=ApiResponse[list[dict]])
async def list_global_voices(
    project_id: str | None = None,
    scope: Literal["all", "global", "project"] = "all",
    db: AsyncSession = Depends(get_db),
):
    rows = await _list_scoped_rows(db, GlobalVoice, scope=scope, project_id=project_id)
    return ApiResponse(data=[_voice_payload(item) for item in rows])


@router.post("/voices", response_model=ApiResponse[dict])
async def create_global_voice(body: VoiceCreate, db: AsyncSession = Depends(get_db)):
    scoped_refs = await _resolve_scoped_refs(db, project_id=body.project_id, folder_id=body.folder_id)
    voice = GlobalVoice(**scoped_refs, **_build_voice_create_values(body))
    db.add(voice)
    return ApiResponse(data=await _save_and_serialize(db, voice, _voice_payload))


@router.put("/voices/{voice_id}", response_model=ApiResponse[dict])
async def update_global_voice(voice_id: str, body: VoiceUpdate, db: AsyncSession = Depends(get_db)):
    voice = await _get_row_or_404(db, GlobalVoice, voice_id, "语音不存在")
    updates = await _normalize_scoped_updates(db, body.model_dump(exclude_unset=True))
    _apply_updates(voice, updates, json_field_map={"meta": ("meta_json", {})})
    if not voice.name:
        raise HTTPException(status_code=400, detail="语音名称不能为空")
    if not voice.voice_code:
        raise HTTPException(status_code=400, detail="voice_code 不能为空")
    return ApiResponse(data=await _save_and_serialize(db, voice, _voice_payload))


@router.delete("/voices/{voice_id}", response_model=ApiResponse[None])
async def delete_global_voice(voice_id: str, db: AsyncSession = Depends(get_db)):
    await _delete_row(db, GlobalVoice, voice_id, "语音不存在")
    return ApiResponse(data=None)


@router.get("/characters", response_model=ApiResponse[list[dict]])
async def list_global_characters(
    project_id: str | None = None,
    scope: Literal["all", "global", "project"] = "all",
    db: AsyncSession = Depends(get_db),
):
    rows = await _list_scoped_rows(db, GlobalCharacter, scope=scope, project_id=project_id)
    return ApiResponse(data=[_character_payload(item) for item in rows])


@router.post("/characters", response_model=ApiResponse[dict])
async def create_global_character(body: GlobalCharacterCreate, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _create_visual_asset(
        db,
        body=body,
        model=GlobalCharacter,
        serializer=_character_payload,
        create_values=_build_character_create_values(body),
    ))


@router.put("/characters/{character_id}", response_model=ApiResponse[dict])
async def update_global_character(character_id: str, body: GlobalCharacterUpdate, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _update_visual_asset(
        db,
        row_id=character_id,
        body=body,
        model=GlobalCharacter,
        detail="全局角色不存在",
        serializer=_character_payload,
        empty_name_detail="角色名称不能为空",
    ))


@router.delete("/characters/{character_id}", response_model=ApiResponse[None])
async def delete_global_character(character_id: str, db: AsyncSession = Depends(get_db)):
    await _delete_row(db, GlobalCharacter, character_id, "全局角色不存在")
    return ApiResponse(data=None)


@router.get("/locations", response_model=ApiResponse[list[dict]])
async def list_global_locations(
    project_id: str | None = None,
    scope: Literal["all", "global", "project"] = "all",
    db: AsyncSession = Depends(get_db),
):
    rows = await _list_scoped_rows(db, GlobalLocation, scope=scope, project_id=project_id)
    return ApiResponse(data=[_location_payload(item) for item in rows])


@router.post("/locations", response_model=ApiResponse[dict])
async def create_global_location(body: GlobalLocationCreate, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _create_visual_asset(
        db,
        body=body,
        model=GlobalLocation,
        serializer=_location_payload,
        create_values=_build_location_create_values(body),
    ))


@router.put("/locations/{location_id}", response_model=ApiResponse[dict])
async def update_global_location(location_id: str, body: GlobalLocationUpdate, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _update_visual_asset(
        db,
        row_id=location_id,
        body=body,
        model=GlobalLocation,
        detail="全局地点不存在",
        serializer=_location_payload,
        empty_name_detail="地点名称不能为空",
    ))


@router.delete("/locations/{location_id}", response_model=ApiResponse[None])
async def delete_global_location(location_id: str, db: AsyncSession = Depends(get_db)):
    await _delete_row(db, GlobalLocation, location_id, "全局地点不存在")
    return ApiResponse(data=None)
