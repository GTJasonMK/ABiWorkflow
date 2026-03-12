from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.project_common import get_episode_or_404, get_project_or_404
from app.api.project_invalidation import invalidate_panel_runtime_outputs
from app.api.response_utils import isoformat_or_empty, json_dict_or_none
from app.database import get_db
from app.models import Episode, GlobalVoice, Panel, PanelAssetOverride, Project, ScriptEntity, ScriptEntityAssetBinding
from app.panel_status import (
    PANEL_STATUS_COMPLETED,
    PANEL_STATUS_FAILED,
    PANEL_STATUS_PENDING,
    PANEL_STATUS_PROCESSING,
)
from app.project_status import PROJECT_BUSY_STATUSES
from app.schemas.common import ApiResponse
from app.services.costing import record_usage_cost
from app.services.episode_workflow import get_episode_provider_key, merge_episode_provider_payload
from app.services.provider_gateway import query_provider_task_status, submit_provider_task
from app.services.script_asset_compiler import (
    COMPILER_VERSION,
    compile_panel_effective_binding,
    get_panel_effective_binding,
)
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
    duration_seconds: float | None = None


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


class EpisodePanelsGenerateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overwrite: bool = Field(default=True, description="是否覆盖当前分集已有分镜")


class ProviderSubmitRequest(BaseModel):
    provider_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    unit_price: float = 0.0
    model_name: str | None = None


class ProviderBatchSubmitRequest(ProviderSubmitRequest):
    force: bool = Field(default=False, description="是否强制覆盖已生成的结果")
    panel_ids: list[str] | None = Field(default=None, description="可选：仅提交指定 panel_ids")


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
    video_provider_task_id: str | None
    tts_provider_task_id: str | None
    lipsync_provider_task_id: str | None
    video_status: str
    tts_status: str
    lipsync_status: str
    status: str
    error_message: str | None
    created_at: str
    updated_at: str



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
    entity_id = _optional_text(explicit_entity_id)
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

    normalized_voice_id = _optional_text(voice_id)
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
            role_tag=_optional_text(role_tag),
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
        video_provider_task_id=panel.video_provider_task_id,
        tts_provider_task_id=panel.tts_provider_task_id,
        lipsync_provider_task_id=panel.lipsync_provider_task_id,
        video_status=panel.video_status,
        tts_status=panel.tts_status,
        lipsync_status=panel.lipsync_status,
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


def _panel_effective_binding_is_stale(panel: Panel) -> bool:
    panel_state = sa_inspect(panel)
    if "effective_binding" in panel_state.unloaded:
        return True
    row = panel.effective_binding
    return row is None or row.compiler_version != COMPILER_VERSION


async def _refresh_panel_effective_binding_if_needed(panel: Panel, db: AsyncSession) -> Panel:
    if not _panel_effective_binding_is_stale(panel):
        return panel
    await compile_panel_effective_binding(panel, db)
    await db.commit()
    return await _get_panel_with_details_or_404(panel.id, db)


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


async def _refresh_panel_list_effective_bindings_if_needed(
    panels: list[Panel],
    db: AsyncSession,
    *,
    project_id: str | None = None,
    episode_id: str | None = None,
) -> list[Panel]:
    stale_ids = {panel.id for panel in panels if _panel_effective_binding_is_stale(panel)}
    if not stale_ids:
        return panels

    for panel in panels:
        if panel.id in stale_ids:
            await compile_panel_effective_binding(panel, db)
    await db.commit()
    return await _list_panels_with_details(db, project_id=project_id, episode_id=episode_id)


async def _ensure_project_editable(project_id: str, db: AsyncSession, action: str) -> Project:
    project = await get_project_or_404(project_id, db)
    if project.status in PROJECT_BUSY_STATUSES:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许{action}")
    return project


@router.get("/projects/{project_id}/panels", response_model=ApiResponse[list[PanelResponse]])
async def list_project_panels(project_id: str, db: AsyncSession = Depends(get_db)):
    panels = await _list_panels_with_details(db, project_id=project_id)
    panels = await _refresh_panel_list_effective_bindings_if_needed(panels, db, project_id=project_id)
    return ApiResponse(data=[_to_panel_response(item) for item in panels])


@router.get("/episodes/{episode_id}/panels", response_model=ApiResponse[list[PanelResponse]])
async def list_panels(episode_id: str, db: AsyncSession = Depends(get_db)):
    await get_episode_or_404(episode_id, db)
    panels = await _list_panels_with_details(db, episode_id=episode_id)
    panels = await _refresh_panel_list_effective_bindings_if_needed(panels, db, episode_id=episode_id)
    return ApiResponse(data=[_to_panel_response(item) for item in panels])


@router.post("/episodes/{episode_id}/panels/video/submit-batch", response_model=ApiResponse[dict])
async def submit_episode_panels_video_batch(
    episode_id: str,
    body: ProviderBatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    """批量提交分集分镜的视频生成任务（Provider 模式）。"""
    return ApiResponse(data=await _submit_episode_panels_provider_batch(
        db,
        episode_id=episode_id,
        body=body,
        task_type="video",
        usage_type="panel_video_generate",
        payload_builder=_build_panel_video_payload,
    ))


@router.post("/episodes/{episode_id}/panels", response_model=ApiResponse[PanelResponse])
async def create_panel(episode_id: str, body: PanelCreate, db: AsyncSession = Depends(get_db)):
    episode = await get_episode_or_404(episode_id, db)
    await _ensure_project_editable(episode.project_id, db, "创建分镜")
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="分镜标题不能为空")

    duration_seconds: float
    provider_key = _optional_text(getattr(episode, "video_provider_key", None))
    if provider_key:
        try:
            from app.services.provider_constraints import resolve_video_duration_constraints

            constraints = await resolve_video_duration_constraints(db, provider_key=provider_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        raw_duration = body.duration_seconds
        if raw_duration is None:
            duration_seconds = float(constraints.allowed_seconds[0])
        else:
            requested = int(round(float(raw_duration)))
            if requested not in constraints.allowed_seconds:
                raise HTTPException(
                    status_code=400,
                    detail=f"分镜时长必须为 {constraints.allowed_seconds_text()} 秒之一",
                )
            duration_seconds = float(requested)
    else:
        raw_duration = float(body.duration_seconds if body.duration_seconds is not None else 5.0)
        duration_seconds = max(0.1, raw_duration)

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
        duration_seconds=duration_seconds,
    )
    db.add(panel)
    await db.commit()
    await db.refresh(panel)

    await compile_panel_effective_binding(panel, db)
    await db.commit()
    panel = await _get_panel_with_details_or_404(panel.id, db)
    return ApiResponse(data=_to_panel_response(panel))


@router.post("/episodes/{episode_id}/panels/generate", response_model=ApiResponse[list[PanelResponse]])
async def generate_episode_panels(
    episode_id: str,
    body: EpisodePanelsGenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    """将分集剧本文案解析为分镜列表（LLM 生成）。"""
    episode = await get_episode_or_404(episode_id, db)
    await _ensure_project_editable(episode.project_id, db, "生成分镜")

    script_text = (episode.script_text or "").strip()
    if not script_text:
        raise HTTPException(status_code=400, detail="当前分集剧本为空，无法生成分镜")

    provider_key = _optional_text(getattr(episode, "video_provider_key", None))
    if not provider_key:
        raise HTTPException(
            status_code=400,
            detail="当前分集未配置视频 Provider，请先在剧本编辑页“编辑本集”中设置 video_provider_key",
        )

    existing_count = int((await db.execute(
        select(func.count(Panel.id)).where(Panel.episode_id == episode_id)
    )).scalar() or 0)
    if existing_count > 0 and not body.overwrite:
        raise HTTPException(status_code=409, detail="当前分集已存在分镜，请使用 overwrite 覆盖生成")

    llm = None
    try:
        from app.llm.factory import create_llm_adapter
        from app.services.provider_constraints import resolve_video_duration_constraints
        from app.services.script_asset_compiler import compile_panel_effective_binding
        from app.services.script_parser import ScriptParserService, normalize_panel_duration

        llm = create_llm_adapter()
        try:
            constraints = await resolve_video_duration_constraints(db, provider_key=provider_key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        parser = ScriptParserService(llm)
        analysis = await parser.analyze_narrative(
            script_text,
            max_scene_seconds=constraints.max_scene_seconds,
            allowed_scene_seconds=constraints.allowed_seconds,
        )
        prompts = await parser.generate_panel_prompts(
            analysis,
            max_scene_seconds=constraints.max_scene_seconds,
            allowed_scene_seconds=constraints.allowed_seconds,
        )
        if not prompts:
            raise RuntimeError("未生成任何分镜提示词，请检查剧本内容")
        if len(prompts) != len(analysis.scenes):
            raise RuntimeError(f"生成提示词数量({len(prompts)})与叙事片段数({len(analysis.scenes)})不一致")

        if existing_count > 0 and body.overwrite:
            old_panels = (await db.execute(
                select(Panel).where(Panel.episode_id == episode_id)
            )).scalars().all()
            for panel in old_panels:
                await db.delete(panel)
            await db.flush()

        max_duration = float(constraints.max_scene_seconds)
        new_panels: list[Panel] = []

        for index, prompt in enumerate(prompts):
            narrative = analysis.scenes[index] if index < len(analysis.scenes) else None
            title = (prompt.title or "").strip()
            if not title and narrative is not None:
                title = (narrative.title or "").strip()
            if not title:
                title = f"分镜 {index + 1}"

            visual_prompt = (prompt.video_prompt or "").strip()
            if not visual_prompt:
                raise RuntimeError(f"第 {index + 1} 个分镜缺少有效视频提示词")

            duration_seconds = normalize_panel_duration(
                float(prompt.duration_seconds or constraints.allowed_seconds[0]),
                max_duration=max_duration,
                allowed_seconds=constraints.allowed_seconds,
            )
            camera_hint = (prompt.camera_movement or "").strip() or None
            if camera_hint:
                camera_hint = camera_hint[:200]
            style_preset = (prompt.style_keywords or "").strip() or None
            if style_preset:
                style_preset = style_preset[:100]
            negative_prompt = (prompt.negative_prompt or "").strip() or None
            script_segment = (getattr(narrative, "narrative", "") if narrative else "") or ""
            tts_text = (getattr(narrative, "dialogue", "") if narrative else "") or ""

            panel = Panel(
                project_id=episode.project_id,
                episode_id=episode_id,
                panel_order=index,
                title=title,
                script_text=script_segment.strip() or None,
                visual_prompt=visual_prompt,
                negative_prompt=negative_prompt,
                camera_hint=camera_hint,
                duration_seconds=duration_seconds,
                style_preset=style_preset,
                tts_text=tts_text.strip() or None,
                status=PANEL_STATUS_PENDING,
            )
            db.add(panel)
            new_panels.append(panel)

        await db.flush()
        for panel in new_panels:
            await compile_panel_effective_binding(panel, db)

        await db.commit()

        panels = await _list_panels_with_details(db, episode_id=episode_id)
        return ApiResponse(data=[_to_panel_response(item) for item in panels])
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一包装为 API 错误，便于前端展示
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"生成分镜失败: {exc}") from exc
    finally:
        if llm is not None:
            await llm.close()


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
    panel = await _refresh_panel_effective_binding_if_needed(panel, db)
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
            episode = await get_episode_or_404(panel.episode_id, db)
            provider_key = _optional_text(getattr(episode, "video_provider_key", None))
            if provider_key:
                try:
                    from app.services.provider_constraints import resolve_video_duration_constraints

                    constraints = await resolve_video_duration_constraints(db, provider_key=provider_key)
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc

                requested = int(round(normalized_duration))
                if requested not in constraints.allowed_seconds:
                    raise HTTPException(
                        status_code=400,
                        detail=f"分镜时长必须为 {constraints.allowed_seconds_text()} 秒之一",
                    )
                normalized_duration = float(requested)

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
    voice_output_affecting_fields = {
        "tts_text",
        "voice_id",
        "script_text",
        "title",
    }
    clear_generation_outputs = bool(changed_fields & generation_affecting_fields)
    clear_voice_outputs = bool(changed_fields & voice_output_affecting_fields)
    if clear_generation_outputs or clear_voice_outputs:
        await invalidate_panel_runtime_outputs(
            db,
            project=project,
            panel=panel,
            clear_generation=clear_generation_outputs,
            clear_voice=clear_voice_outputs,
        )

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


def _provider_phase_from_status(raw_status: str | None) -> str:
    value = str(raw_status or "").strip().lower()
    if value in {"completed", "success", "succeeded"}:
        return "succeeded"
    if value in {"failed", "cancelled", "error"}:
        return "failed"
    if value in {"pending", "submitted", "queued"}:
        return "queued"
    if value in {"running", "processing", "in_progress"}:
        return "running"
    return "idle"


def _set_panel_task_phase(panel: Panel, task_type: str, phase: str) -> None:
    if task_type == "video":
        panel.video_status = phase
        return
    if task_type == "tts":
        panel.tts_status = phase
        return
    if task_type == "lipsync":
        panel.lipsync_status = phase
        return
    raise ValueError(f"未知 task_type: {task_type}")


def _refresh_panel_rollup_status(panel: Panel) -> None:
    if panel.video_status in {"failed", "running", "queued"}:
        panel.status = PANEL_STATUS_FAILED if panel.video_status == "failed" else PANEL_STATUS_PROCESSING
        return
    if panel.lipsync_status in {"failed", "running", "queued"}:
        panel.status = PANEL_STATUS_FAILED if panel.lipsync_status == "failed" else PANEL_STATUS_PROCESSING
        return
    if panel.video_url or panel.lipsync_video_url or panel.video_status == "succeeded":
        panel.status = PANEL_STATUS_COMPLETED
        return
    panel.status = PANEL_STATUS_PENDING


def _provider_label(task_type: str) -> str:
    return {
        "video": "视频",
        "tts": "语音",
        "lipsync": "口型同步",
    }.get(task_type, task_type)


async def _resolve_provider_submit_request(
    db: AsyncSession,
    *,
    episode: Episode,
    task_type: str,
    body: ProviderSubmitRequest,
) -> ProviderSubmitRequest:
    provider_key = (body.provider_key or "").strip() or get_episode_provider_key(episode, task_type)
    if not provider_key:
        raise HTTPException(status_code=400, detail=f"当前分集未配置{_provider_label(task_type)} Provider")
    return ProviderSubmitRequest(
        provider_key=provider_key,
        payload=merge_episode_provider_payload(episode, task_type=task_type, extra_payload=body.payload),
        unit_price=float(body.unit_price or 0.0),
        model_name=body.model_name,
    )


async def _resolve_provider_status_key(
    db: AsyncSession,
    *,
    panel: Panel,
    task_type: str,
    provider_key: str | None,
) -> str:
    episode = await get_episode_or_404(panel.episode_id, db)
    resolved_provider_key = (provider_key or "").strip() or get_episode_provider_key(episode, task_type)
    if not resolved_provider_key:
        raise HTTPException(status_code=400, detail=f"当前分集未配置{_provider_label(task_type)} Provider")
    return resolved_provider_key


def _reset_panel_outputs_for_provider_submit(panel: Panel, task_type: str) -> None:
    if task_type == "video":
        panel.video_url = None
        panel.lipsync_video_url = None
        panel.lipsync_provider_task_id = None
        panel.video_status = "running"
        panel.lipsync_status = "idle"
        panel.error_message = None
        _refresh_panel_rollup_status(panel)
        return
    if task_type == "tts":
        panel.tts_audio_url = None
        panel.lipsync_video_url = None
        panel.lipsync_provider_task_id = None
        panel.tts_status = "running"
        panel.lipsync_status = "idle"
        _refresh_panel_rollup_status(panel)
        return
    if task_type == "lipsync":
        panel.lipsync_video_url = None
        panel.lipsync_status = "running"
        _refresh_panel_rollup_status(panel)


async def _submit_panel_provider_task(
    db: AsyncSession,
    *,
    panel: Panel,
    task_type: str,
    usage_type: str,
    body: ProviderSubmitRequest,
    payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        submitted = await submit_provider_task(db, provider_key=body.provider_key or "", payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        snippet = ""
        try:
            snippet = (exc.response.text or "")[:800].replace("\n", " ").strip()
        except Exception:  # noqa: BLE001
            snippet = ""
        detail = f"提交 Provider 任务失败: 上游返回 {exc.response.status_code}"
        if snippet:
            detail = f"{detail} - {snippet}"
        raise HTTPException(status_code=502, detail=detail) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"提交 Provider 任务失败: {exc}") from exc
    provider_task_id = submitted["task_id"]
    unit_price = max(0.0, float(body.unit_price))
    task_payload = {
        "provider_key": body.provider_key,
        "request": dict(payload),
        "usage_type": usage_type,
        "model_name": body.model_name,
        "unit_price": unit_price,
    }

    _reset_panel_outputs_for_provider_submit(panel, task_type)
    _set_panel_provider_task_id(panel, task_type, provider_task_id)
    _set_panel_task_phase(panel, task_type, _provider_phase_from_status(submitted.get("status")))
    if (
        task_type in {"video", "lipsync"}
        and panel.error_message
        and getattr(panel, f"{task_type}_status", "") != "failed"
    ):
        panel.error_message = None
    _refresh_panel_rollup_status(panel)

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
        payload=task_payload,
    )
    await record_usage_cost(
        db,
        provider_type=task_type,
        provider_name=body.provider_key,
        model_name=body.model_name,
        usage_type=usage_type,
        quantity=1.0,
        unit="request",
        unit_price=unit_price,
        project_id=panel.project_id,
        episode_id=panel.episode_id,
        panel_id=panel.id,
        task_id=record.id,
    )

    immediate_status = str(submitted.get("status") or "").strip().lower()
    immediate_result_url = str(submitted.get("result_url") or "").strip() or None
    if immediate_status == "completed" and immediate_result_url:
        target_field = {
            "video": "video_url",
            "tts": "tts_audio_url",
            "lipsync": "lipsync_video_url",
        }.get(task_type)
        if not target_field:
            raise HTTPException(status_code=500, detail=f"未知 task_type: {task_type}")

        setattr(panel, target_field, immediate_result_url)
        _set_panel_task_phase(panel, task_type, "succeeded")
        panel.error_message = None
        _refresh_panel_rollup_status(panel)

        await update_task_record(
            db,
            task=record,
            status=TASK_RECORD_STATUS_COMPLETED,
            progress_percent=100.0,
            message=f"{task_type} 已完成（同步返回结果）",
            result={
                "result_url": immediate_result_url,
                "provider_submit": submitted,
            },
            event_type="provider_submitted",
        )
    await db.commit()
    await db.refresh(panel)
    await db.refresh(record)
    return {
        "panel": _to_panel_response(panel).model_dump(),
        "task": serialize_task_record(record),
        "provider": submitted,
    }


def _map_provider_status_to_task_status(provider_status: str) -> str:
    return {
        "pending": TASK_RECORD_STATUS_RUNNING,
        "queued": TASK_RECORD_STATUS_RUNNING,
        "submitted": TASK_RECORD_STATUS_RUNNING,
        "running": TASK_RECORD_STATUS_RUNNING,
        "completed": TASK_RECORD_STATUS_COMPLETED,
        "success": TASK_RECORD_STATUS_COMPLETED,
        "succeeded": TASK_RECORD_STATUS_COMPLETED,
        "failed": TASK_RECORD_STATUS_FAILED,
        "cancelled": TASK_RECORD_STATUS_FAILED,
    }.get(provider_status, TASK_RECORD_STATUS_RUNNING)


def _panel_provider_task_field(task_type: str) -> str:
    return {
        "video": "video_provider_task_id",
        "tts": "tts_provider_task_id",
        "lipsync": "lipsync_provider_task_id",
    }[task_type]


def _panel_provider_task_id(panel: Panel, task_type: str) -> str | None:
    return getattr(panel, _panel_provider_task_field(task_type))


def _set_panel_provider_task_id(panel: Panel, task_type: str, task_id: str) -> None:
    setattr(panel, _panel_provider_task_field(task_type), task_id)


def _panel_provider_output_url(panel: Panel, task_type: str) -> str | None:
    if task_type == "video":
        return panel.video_url
    if task_type == "tts":
        return panel.tts_audio_url
    if task_type == "lipsync":
        return panel.lipsync_video_url
    raise ValueError(f"未知 task_type: {task_type}")


async def _query_and_sync_panel_provider_status(
    db: AsyncSession,
    *,
    panel: Panel,
    task_type: str,
    provider_key: str,
    missing_task_detail: str,
) -> dict[str, Any]:
    provider_task_id = _panel_provider_task_id(panel, task_type)
    if not provider_task_id:
        raise HTTPException(status_code=400, detail=missing_task_detail)

    existing_output = _panel_provider_output_url(panel, task_type)
    if existing_output:
        return {
            "provider_key": provider_key,
            "task_id": str(provider_task_id),
            "status": "completed",
            "progress_percent": 100.0,
            "result_url": existing_output,
            "error_message": None,
            "raw": {"source": "panel"},
        }

    try:
        status_data = await query_provider_task_status(
            db,
            provider_key=provider_key,
            task_id=provider_task_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"查询 Provider 状态失败: {exc}") from exc
    task = await get_task_record_by_source_id(db, provider_task_id)
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
    _set_panel_task_phase(panel, task_type, _provider_phase_from_status(status_data.get("status")))
    if status_data["status"] in {"failed", "cancelled"}:
        panel.error_message = status_data.get("error_message")
    elif task_type in {"video", "lipsync"} and status_data["status"] == "completed":
        panel.error_message = None
    _refresh_panel_rollup_status(panel)
    return status_data


def _apply_video_provider_status(panel: Panel, status_data: dict[str, Any]) -> None:
    _set_panel_task_phase(panel, "video", _provider_phase_from_status(status_data.get("status")))
    if status_data["status"] in {"failed", "cancelled"}:
        panel.error_message = status_data.get("error_message")
    elif status_data["status"] == "completed":
        panel.error_message = None
    _refresh_panel_rollup_status(panel)


async def _sync_panel_provider_apply_task_record(
    db: AsyncSession,
    *,
    panel: Panel,
    task_type: str,
    result_url: str,
) -> None:
    provider_task_id = _panel_provider_task_id(panel, task_type)
    if not provider_task_id:
        return

    task = await get_task_record_by_source_id(db, provider_task_id)
    if task is None:
        return

    task.error_message = None
    await update_task_record(
        db,
        task=task,
        status=TASK_RECORD_STATUS_COMPLETED,
        progress_percent=100.0,
        message=f"{task_type} 结果已应用",
        result={"result_url": result_url},
        event_type="provider_applied",
    )


async def _apply_panel_result_url(
    db: AsyncSession,
    *,
    panel: Panel,
    task_type: str,
    target_field: str,
    result_url: str,
    mark_panel_completed: bool,
) -> Panel:
    normalized_result_url = result_url.strip()
    if not normalized_result_url:
        raise HTTPException(status_code=400, detail="result_url 不能为空")
    setattr(panel, target_field, normalized_result_url)
    _set_panel_task_phase(panel, task_type, "succeeded")
    if mark_panel_completed or task_type in {"tts", "lipsync"}:
        panel.error_message = None
    _refresh_panel_rollup_status(panel)
    await _sync_panel_provider_apply_task_record(
        db,
        panel=panel,
        task_type=task_type,
        result_url=normalized_result_url,
    )
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



def _resolved_effective_voice(panel: Panel, effective: dict[str, Any]) -> dict[str, Any]:
    effective_voice = _effective_voice_context(effective)
    return {
        "text": _effective_voice_text(panel, effective),
        "voice_id": _optional_text(effective_voice.get("voice_id")) or panel.voice_id,
        "entity_id": _optional_text(effective_voice.get("entity_id")),
        "role_tag": _optional_text(effective_voice.get("role_tag")),
        "provider": _optional_text(effective_voice.get("provider")),
        "voice_code": _optional_text(effective_voice.get("voice_code")),
        "strategy": _effective_voice_strategy(effective_voice),
    }



def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _panel_voice_source_text(panel: Panel) -> str:
    return (panel.tts_text or panel.script_text or "").strip()


def _analyze_voice_text(source_text: str) -> dict[str, Any]:
    length = len(source_text)
    sentence_count = max(1, source_text.count("。") + source_text.count("！") + source_text.count("？"))
    avg_chars = max(1, length // sentence_count)
    speaking_rate_cps = 4.5
    estimated_seconds = round(length / speaking_rate_cps, 2) if length else 0.0
    return {
        "has_text": bool(source_text),
        "text_length": length,
        "sentence_count": sentence_count,
        "avg_chars_per_sentence": avg_chars,
        "estimated_seconds": estimated_seconds,
    }


def _apply_voice_design_request(binding: dict[str, Any], body: VoiceDesignRequest) -> dict[str, Any]:
    updated = dict(binding)
    if body.mood is not None:
        updated["mood"] = body.mood.strip()
    if body.speed is not None:
        updated["speed"] = float(body.speed)
    if body.pitch is not None:
        updated["pitch"] = float(body.pitch)
    updated["designed_at"] = datetime.now(timezone.utc).isoformat()
    return updated


def _build_voice_design_response(
    panel: Panel,
    target_override: PanelAssetOverride,
    binding: dict[str, Any],
) -> dict[str, Any]:
    return {
        "panel_id": panel.id,
        "voice_id": target_override.asset_id,
        "entity_id": target_override.entity_id,
        "binding": binding,
    }


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
    resolved_voice = _resolved_effective_voice(panel, effective)
    voice_id = resolved_voice["voice_id"]
    if voice_id is None:
        raise HTTPException(status_code=400, detail="当前分镜未绑定语音，无法设计语音参数")

    await _replace_panel_voice_override(
        panel,
        db=db,
        voice_id=voice_id,
        strategy=resolved_voice["strategy"],
        entity_id=resolved_voice["entity_id"],
        role_tag=resolved_voice["role_tag"],
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
    resolved_voice = _resolved_effective_voice(panel, effective)
    payload = dict(extra_payload)
    payload["text"] = resolved_voice["text"]
    payload["voice_id"] = resolved_voice["voice_id"]
    payload["binding"] = resolved_voice["strategy"]
    payload["voice_provider"] = resolved_voice["provider"]
    payload["voice_code"] = resolved_voice["voice_code"]
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
    seconds = int(round(float(panel.duration_seconds or 0.0)))
    payload = dict(extra_payload)
    payload["prompt"] = _effective_visual_prompt(panel, effective)
    payload["negative_prompt"] = panel.negative_prompt
    payload["seconds"] = max(1, seconds)
    payload["reference_image_url"] = _effective_reference_image(panel, effective)
    return payload



def _build_panel_lipsync_payload(panel: Panel, extra_payload: dict[str, Any]) -> dict[str, Any]:
    if not panel.video_url:
        raise HTTPException(status_code=400, detail="请先提供原始视频（panel.video_url）")
    if not panel.tts_audio_url:
        raise HTTPException(status_code=400, detail="请先提供语音音频（panel.tts_audio_url）")
    payload = dict(extra_payload)
    payload["video_url"] = panel.video_url
    payload["audio_url"] = panel.tts_audio_url
    payload["panel_id"] = panel.id
    return payload


def _build_panel_lipsync_payload_with_effective(
    panel: Panel,
    _: dict[str, Any],
    extra_payload: dict[str, Any],
) -> dict[str, Any]:
    return _build_panel_lipsync_payload(panel, extra_payload)


async def _submit_panel_provider_payload(
    db: AsyncSession,
    *,
    panel: Panel,
    body: ProviderSubmitRequest,
    task_type: str,
    usage_type: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return await _submit_panel_provider_task(
        db,
        panel=panel,
        task_type=task_type,
        usage_type=usage_type,
        body=body,
        payload=payload,
    )


async def _submit_effective_panel_provider_request(
    db: AsyncSession,
    *,
    panel_id: str,
    body: ProviderSubmitRequest,
    task_type: str,
    usage_type: str,
    payload_builder: Callable[[Panel, dict[str, Any], dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    panel = await _get_panel_with_details_or_404(panel_id, db)
    episode = await get_episode_or_404(panel.episode_id, db)
    resolved_body = await _resolve_provider_submit_request(
        db,
        episode=episode,
        task_type=task_type,
        body=body,
    )
    effective = await _load_effective_panel_binding(panel, db)
    payload = payload_builder(panel, effective, resolved_body.payload)
    return await _submit_panel_provider_payload(
        db,
        panel=panel,
        body=resolved_body,
        task_type=task_type,
        usage_type=usage_type,
        payload=payload,
    )


def _panel_has_provider_output(panel: Panel, task_type: str) -> bool:
    if task_type == "video":
        return bool(panel.video_url or panel.lipsync_video_url)
    return bool(_panel_provider_output_url(panel, task_type))


async def _submit_episode_panels_provider_batch(
    db: AsyncSession,
    *,
    episode_id: str,
    body: ProviderBatchSubmitRequest,
    task_type: str,
    usage_type: str,
    payload_builder: Callable[[Panel, dict[str, Any], dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    episode = await get_episode_or_404(episode_id, db)
    resolved_body = await _resolve_provider_submit_request(
        db,
        episode=episode,
        task_type=task_type,
        body=body,
    )
    panels = await _list_panels_with_details(db, episode_id=episode_id)
    allowed_ids = set(body.panel_ids) if body.panel_ids else None

    total = 0
    submitted = 0
    skipped = 0
    errors: list[dict[str, Any]] = []

    for panel in panels:
        if allowed_ids is not None and panel.id not in allowed_ids:
            continue

        total += 1
        if not body.force and _panel_has_provider_output(panel, task_type):
            skipped += 1
            continue

        try:
            effective = await _load_effective_panel_binding(panel, db)
            payload = payload_builder(panel, effective, resolved_body.payload)
            if task_type == "video" and not str(payload.get("prompt") or "").strip():
                raise HTTPException(status_code=400, detail="缺少有效 prompt，无法提交视频生成")
            if task_type == "tts" and not str(payload.get("text") or "").strip():
                raise HTTPException(status_code=400, detail="缺少有效 text，无法提交语音生成")

            await _submit_panel_provider_payload(
                db,
                panel=panel,
                body=resolved_body,
                task_type=task_type,
                usage_type=usage_type,
                payload=payload,
            )
            submitted += 1
        except HTTPException as exc:
            errors.append({
                "panel_id": panel.id,
                "title": panel.title,
                "detail": exc.detail,
            })
        except Exception as exc:  # noqa: BLE001
            errors.append({
                "panel_id": panel.id,
                "title": panel.title,
                "detail": str(exc),
            })

    return {
        "episode_id": episode.id,
        "provider_key": resolved_body.provider_key,
        "task_type": task_type,
        "total": total,
        "submitted": submitted,
        "skipped": skipped,
        "failed": len(errors),
        "errors": errors,
    }


async def _build_panel_provider_status_response(
    db: AsyncSession,
    *,
    panel_id: str,
    task_type: str,
    provider_key: str | None,
    missing_task_detail: str,
    panel_status_applier: Callable[[Panel, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    panel = await _get_panel_with_details_or_404(panel_id, db)
    resolved_provider_key = await _resolve_provider_status_key(
        db,
        panel=panel,
        task_type=task_type,
        provider_key=provider_key,
    )
    status_data = await _query_and_sync_panel_provider_status(
        db,
        panel=panel,
        task_type=task_type,
        provider_key=resolved_provider_key,
        missing_task_detail=missing_task_detail,
    )
    response_status = {
        **status_data,
        "provider_key": resolved_provider_key,
    }
    if panel_status_applier is None:
        await db.commit()
        return response_status

    panel_status_applier(panel, status_data)
    await db.commit()
    panel = await _get_panel_with_details_or_404(panel.id, db)
    return {
        "panel": _to_panel_response(panel).model_dump(),
        "provider_status": response_status,
    }


async def _apply_panel_provider_result_response(
    db: AsyncSession,
    *,
    panel_id: str,
    task_type: str,
    target_field: str,
    result_url: str,
    mark_panel_completed: bool,
) -> PanelResponse:
    panel = await _get_panel_with_details_or_404(panel_id, db)
    panel = await _apply_panel_result_url(
        db,
        panel=panel,
        task_type=task_type,
        target_field=target_field,
        result_url=result_url,
        mark_panel_completed=mark_panel_completed,
    )
    return _to_panel_response(panel)


@router.post("/panels/{panel_id}/video/submit", response_model=ApiResponse[dict])
async def submit_panel_video(panel_id: str, body: ProviderSubmitRequest, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _submit_effective_panel_provider_request(
        db,
        panel_id=panel_id,
        body=body,
        task_type="video",
        usage_type="panel_video_generate",
        payload_builder=_build_panel_video_payload,
    ))


@router.get("/panels/{panel_id}/video/status", response_model=ApiResponse[dict])
async def get_panel_video_status(panel_id: str, provider_key: str | None = None, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _build_panel_provider_status_response(
        db,
        panel_id=panel_id,
        task_type="video",
        provider_key=provider_key,
        missing_task_detail="该分镜尚未提交视频任务",
        panel_status_applier=_apply_video_provider_status,
    ))


@router.post("/panels/{panel_id}/video/apply", response_model=ApiResponse[PanelResponse])
async def apply_panel_video(panel_id: str, body: ProviderApplyRequest, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _apply_panel_provider_result_response(
        db,
        panel_id=panel_id,
        task_type="video",
        target_field="video_url",
        result_url=body.result_url,
        mark_panel_completed=True,
    ))


@router.post("/panels/{panel_id}/voice/analyze", response_model=ApiResponse[dict])
async def analyze_panel_voice(panel_id: str, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_with_details_or_404(panel_id, db)
    return ApiResponse(data={
        "panel_id": panel.id,
        **_analyze_voice_text(_panel_voice_source_text(panel)),
    })


@router.post("/panels/{panel_id}/voice/design", response_model=ApiResponse[dict])
async def design_panel_voice(panel_id: str, body: VoiceDesignRequest, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_with_details_or_404(panel_id, db)
    from app.services.json_codec import to_json_text

    target_override = await _ensure_panel_voice_override(panel, db)
    binding = _apply_voice_design_request(json_dict_or_none(target_override.strategy_json) or {}, body)
    target_override.strategy_json = to_json_text(binding) if binding else None

    await _compile_panel_binding_state(panel, db)
    return ApiResponse(data=_build_voice_design_response(panel, target_override, binding))


@router.post("/panels/{panel_id}/voice/generate-lines", response_model=ApiResponse[dict])
async def generate_panel_voice_lines(panel_id: str, body: ProviderSubmitRequest, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _submit_effective_panel_provider_request(
        db,
        panel_id=panel_id,
        body=body,
        task_type="tts",
        usage_type="panel_tts_generate",
        payload_builder=_build_panel_tts_payload,
    ))


@router.post("/episodes/{episode_id}/panels/voice/submit-batch", response_model=ApiResponse[dict])
async def submit_episode_panels_voice_batch(
    episode_id: str,
    body: ProviderBatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    return ApiResponse(data=await _submit_episode_panels_provider_batch(
        db,
        episode_id=episode_id,
        body=body,
        task_type="tts",
        usage_type="panel_tts_generate",
        payload_builder=_build_panel_tts_payload,
    ))


@router.get("/panels/{panel_id}/voice/status", response_model=ApiResponse[dict])
async def get_panel_voice_status(panel_id: str, provider_key: str | None = None, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _build_panel_provider_status_response(
        db,
        panel_id=panel_id,
        task_type="tts",
        provider_key=provider_key,
        missing_task_detail="该分镜尚未提交语音任务",
    ))


@router.post("/panels/{panel_id}/voice/apply", response_model=ApiResponse[PanelResponse])
async def apply_panel_voice(panel_id: str, body: ProviderApplyRequest, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _apply_panel_provider_result_response(
        db,
        panel_id=panel_id,
        task_type="tts",
        target_field="tts_audio_url",
        result_url=body.result_url,
        mark_panel_completed=False,
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
    panel = await _get_panel_with_details_or_404(panel_id, db)
    episode = await get_episode_or_404(panel.episode_id, db)
    resolved_body = await _resolve_provider_submit_request(
        db,
        episode=episode,
        task_type="lipsync",
        body=body,
    )
    return ApiResponse(data=await _submit_panel_provider_payload(
        db,
        panel=panel,
        body=resolved_body,
        task_type="lipsync",
        usage_type="panel_lipsync_generate",
        payload=_build_panel_lipsync_payload(panel, resolved_body.payload),
    ))


@router.post("/episodes/{episode_id}/panels/lipsync/submit-batch", response_model=ApiResponse[dict])
async def submit_episode_panels_lipsync_batch(
    episode_id: str,
    body: ProviderBatchSubmitRequest,
    db: AsyncSession = Depends(get_db),
):
    return ApiResponse(data=await _submit_episode_panels_provider_batch(
        db,
        episode_id=episode_id,
        body=body,
        task_type="lipsync",
        usage_type="panel_lipsync_generate",
        payload_builder=_build_panel_lipsync_payload_with_effective,
    ))


@router.get("/panels/{panel_id}/lipsync/status", response_model=ApiResponse[dict])
async def get_panel_lipsync_status(panel_id: str, provider_key: str | None = None, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _build_panel_provider_status_response(
        db,
        panel_id=panel_id,
        task_type="lipsync",
        provider_key=provider_key,
        missing_task_detail="该分镜尚未提交口型同步任务",
    ))


@router.post("/panels/{panel_id}/lipsync/apply", response_model=ApiResponse[PanelResponse])
async def apply_panel_lipsync(panel_id: str, body: ProviderApplyRequest, db: AsyncSession = Depends(get_db)):
    return ApiResponse(data=await _apply_panel_provider_result_response(
        db,
        panel_id=panel_id,
        task_type="lipsync",
        target_field="lipsync_video_url",
        result_url=body.result_url,
        mark_panel_completed=False,
    ))
