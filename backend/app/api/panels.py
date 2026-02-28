from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Episode, Panel
from app.panel_status import PANEL_STATUS_COMPLETED, PANEL_STATUS_FAILED, PANEL_STATUS_PROCESSING
from app.schemas.common import ApiResponse
from app.services.costing import record_usage_cost
from app.services.provider_gateway import query_provider_task_status, submit_provider_task
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


class PanelCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    script_text: str | None = None
    visual_prompt: str | None = None
    negative_prompt: str | None = None
    duration_seconds: float = 5.0


class PanelUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    script_text: str | None = None
    visual_prompt: str | None = None
    negative_prompt: str | None = None
    camera_hint: str | None = None
    duration_seconds: float | None = None
    style_preset: str | None = None
    reference_image_url: str | None = None
    voice_id: str | None = None
    voice_binding_json: dict[str, Any] | None = None
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
    voice_binding_json: dict[str, Any] | None
    tts_text: str | None
    tts_audio_url: str | None
    video_url: str | None
    lipsync_video_url: str | None
    provider_task_id: str | None
    status: str
    error_message: str | None
    created_at: str
    updated_at: str


def _safe_json_object(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    from app.services.json_codec import from_json_text

    value = from_json_text(raw, None)
    return value if isinstance(value, dict) else None


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
        voice_binding_json=_safe_json_object(panel.voice_binding_json),
        tts_text=panel.tts_text,
        tts_audio_url=panel.tts_audio_url,
        video_url=panel.video_url,
        lipsync_video_url=panel.lipsync_video_url,
        provider_task_id=panel.provider_task_id,
        status=panel.status,
        error_message=panel.error_message,
        created_at=panel.created_at.isoformat() if panel.created_at else "",
        updated_at=panel.updated_at.isoformat() if panel.updated_at else "",
    )


async def _get_episode_or_404(episode_id: str, db: AsyncSession) -> Episode:
    episode = (await db.execute(select(Episode).where(Episode.id == episode_id))).scalar_one_or_none()
    if episode is None:
        raise HTTPException(status_code=404, detail="分集不存在")
    return episode


async def _get_panel_or_404(panel_id: str, db: AsyncSession) -> Panel:
    panel = (await db.execute(select(Panel).where(Panel.id == panel_id))).scalar_one_or_none()
    if panel is None:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return panel


@router.get("/projects/{project_id}/panels", response_model=ApiResponse[list[PanelResponse]])
async def list_project_panels(project_id: str, db: AsyncSession = Depends(get_db)):
    panels = (await db.execute(
        select(Panel).where(Panel.project_id == project_id).order_by(Panel.episode_id, Panel.panel_order)
    )).scalars().all()
    return ApiResponse(data=[_to_panel_response(item) for item in panels])


@router.get("/episodes/{episode_id}/panels", response_model=ApiResponse[list[PanelResponse]])
async def list_panels(episode_id: str, db: AsyncSession = Depends(get_db)):
    await _get_episode_or_404(episode_id, db)
    panels = (await db.execute(
        select(Panel).where(Panel.episode_id == episode_id).order_by(Panel.panel_order, Panel.created_at)
    )).scalars().all()
    return ApiResponse(data=[_to_panel_response(item) for item in panels])


@router.post("/episodes/{episode_id}/panels", response_model=ApiResponse[PanelResponse])
async def create_panel(episode_id: str, body: PanelCreate, db: AsyncSession = Depends(get_db)):
    episode = await _get_episode_or_404(episode_id, db)
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
    return ApiResponse(data=_to_panel_response(panel))


@router.put("/episodes/{episode_id}/panels/reorder", response_model=ApiResponse[None])
async def reorder_panels(episode_id: str, body: PanelReorderRequest, db: AsyncSession = Depends(get_db)):
    await _get_episode_or_404(episode_id, db)
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
    panel = await _get_panel_or_404(panel_id, db)
    return ApiResponse(data=_to_panel_response(panel))


@router.put("/panels/{panel_id}", response_model=ApiResponse[PanelResponse])
async def update_panel(panel_id: str, body: PanelUpdate, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
    updates = body.model_dump(exclude_unset=True)
    from app.services.json_codec import to_json_text

    for key, value in updates.items():
        if key == "title" and value is not None:
            normalized = str(value).strip()
            if not normalized:
                raise HTTPException(status_code=400, detail="分镜标题不能为空")
            panel.title = normalized
            continue
        if key == "voice_binding_json":
            panel.voice_binding_json = to_json_text(value) if value else None
            continue
        if key in {"script_text", "visual_prompt", "negative_prompt", "camera_hint", "style_preset", "reference_image_url", "tts_text", "tts_audio_url", "video_url", "lipsync_video_url"}:
            setattr(panel, key, (str(value).strip() if isinstance(value, str) else value) or None)
            continue
        if key == "duration_seconds" and value is not None:
            panel.duration_seconds = max(0.1, float(value))
            continue
        setattr(panel, key, value)

    await db.commit()
    await db.refresh(panel)
    return ApiResponse(data=_to_panel_response(panel))


@router.delete("/panels/{panel_id}", response_model=ApiResponse[None])
async def delete_panel(panel_id: str, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
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


@router.post("/panels/{panel_id}/video/submit", response_model=ApiResponse[dict])
async def submit_panel_video(panel_id: str, body: ProviderSubmitRequest, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
    payload = {
        "prompt": panel.visual_prompt or panel.script_text or panel.title,
        "negative_prompt": panel.negative_prompt,
        "duration_seconds": panel.duration_seconds,
        "reference_image_url": panel.reference_image_url,
        **body.payload,
    }
    data = await _submit_panel_provider_task(
        db,
        panel=panel,
        task_type="video",
        usage_type="panel_video_generate",
        body=body,
        payload=payload,
    )
    return ApiResponse(data=data)


@router.get("/panels/{panel_id}/video/status", response_model=ApiResponse[dict])
async def get_panel_video_status(panel_id: str, provider_key: str, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
    if not panel.provider_task_id:
        raise HTTPException(status_code=400, detail="该分镜尚未提交视频任务")

    status_data = await query_provider_task_status(
        db,
        provider_key=provider_key,
        task_id=panel.provider_task_id,
    )
    task = await get_task_record_by_source_id(db, panel.provider_task_id)
    if task:
        mapped_status = {
            "pending": TASK_RECORD_STATUS_RUNNING,
            "running": TASK_RECORD_STATUS_RUNNING,
            "completed": TASK_RECORD_STATUS_COMPLETED,
            "failed": TASK_RECORD_STATUS_FAILED,
            "cancelled": TASK_RECORD_STATUS_FAILED,
        }.get(status_data["status"], TASK_RECORD_STATUS_RUNNING)
        await update_task_record(
            db,
            task=task,
            status=mapped_status,
            progress_percent=float(status_data.get("progress_percent") or 0.0),
            message=status_data.get("error_message") or f"provider={provider_key}",
            result={"provider_status": status_data},
            event_type="provider_status",
        )

    if status_data["status"] == "completed":
        panel.status = PANEL_STATUS_COMPLETED
    elif status_data["status"] in {"failed", "cancelled"}:
        panel.status = PANEL_STATUS_FAILED
        panel.error_message = status_data.get("error_message")
    else:
        panel.status = PANEL_STATUS_PROCESSING
    await db.commit()
    return ApiResponse(data={
        "panel": _to_panel_response(panel).model_dump(),
        "provider_status": status_data,
    })


@router.post("/panels/{panel_id}/video/apply", response_model=ApiResponse[PanelResponse])
async def apply_panel_video(panel_id: str, body: ProviderApplyRequest, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
    panel.video_url = body.result_url.strip()
    panel.status = PANEL_STATUS_COMPLETED
    panel.error_message = None
    await db.commit()
    await db.refresh(panel)
    return ApiResponse(data=_to_panel_response(panel))


@router.post("/panels/{panel_id}/voice/analyze", response_model=ApiResponse[dict])
async def analyze_panel_voice(panel_id: str, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
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
    panel = await _get_panel_or_404(panel_id, db)
    from app.services.json_codec import to_json_text

    binding = _safe_json_object(panel.voice_binding_json) or {}
    if body.mood is not None:
        binding["mood"] = body.mood.strip()
    if body.speed is not None:
        binding["speed"] = float(body.speed)
    if body.pitch is not None:
        binding["pitch"] = float(body.pitch)
    binding["designed_at"] = datetime.now(timezone.utc).isoformat()
    panel.voice_binding_json = to_json_text(binding)
    await db.commit()
    return ApiResponse(data={"panel_id": panel.id, "binding": binding})


@router.post("/panels/{panel_id}/voice/generate-lines", response_model=ApiResponse[dict])
async def generate_panel_voice_lines(panel_id: str, body: ProviderSubmitRequest, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
    payload = {
        "text": (panel.tts_text or panel.script_text or panel.title),
        "voice_id": panel.voice_id,
        "binding": _safe_json_object(panel.voice_binding_json) or {},
        **body.payload,
    }
    data = await _submit_panel_provider_task(
        db,
        panel=panel,
        task_type="tts",
        usage_type="panel_tts_generate",
        body=body,
        payload=payload,
    )
    return ApiResponse(data=data)


@router.put("/panels/{panel_id}/voice/binding", response_model=ApiResponse[PanelResponse])
async def bind_panel_voice(panel_id: str, body: VoiceBindingRequest, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
    from app.services.json_codec import to_json_text

    panel.voice_id = body.voice_id
    panel.voice_binding_json = to_json_text(body.binding)
    await db.commit()
    await db.refresh(panel)
    return ApiResponse(data=_to_panel_response(panel))


@router.post("/panels/{panel_id}/lipsync/submit", response_model=ApiResponse[dict])
async def submit_panel_lipsync(panel_id: str, body: ProviderSubmitRequest, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
    if not panel.video_url:
        raise HTTPException(status_code=400, detail="请先提供原始视频（panel.video_url）")
    if not panel.tts_audio_url:
        raise HTTPException(status_code=400, detail="请先提供语音音频（panel.tts_audio_url）")

    payload = {
        "video_url": panel.video_url,
        "audio_url": panel.tts_audio_url,
        "panel_id": panel.id,
        **body.payload,
    }
    data = await _submit_panel_provider_task(
        db,
        panel=panel,
        task_type="lipsync",
        usage_type="panel_lipsync_generate",
        body=body,
        payload=payload,
    )
    return ApiResponse(data=data)


@router.get("/panels/{panel_id}/lipsync/status", response_model=ApiResponse[dict])
async def get_panel_lipsync_status(panel_id: str, provider_key: str, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
    if not panel.provider_task_id:
        raise HTTPException(status_code=400, detail="该分镜尚未提交口型同步任务")

    status_data = await query_provider_task_status(
        db,
        provider_key=provider_key,
        task_id=panel.provider_task_id,
    )
    task = await get_task_record_by_source_id(db, panel.provider_task_id)
    if task:
        mapped_status = {
            "pending": TASK_RECORD_STATUS_RUNNING,
            "running": TASK_RECORD_STATUS_RUNNING,
            "completed": TASK_RECORD_STATUS_COMPLETED,
            "failed": TASK_RECORD_STATUS_FAILED,
            "cancelled": TASK_RECORD_STATUS_FAILED,
        }.get(status_data["status"], TASK_RECORD_STATUS_RUNNING)
        await update_task_record(
            db,
            task=task,
            status=mapped_status,
            progress_percent=float(status_data.get("progress_percent") or 0.0),
            message=status_data.get("error_message") or f"provider={provider_key}",
            result={"provider_status": status_data},
            event_type="provider_status",
        )
    await db.commit()
    return ApiResponse(data=status_data)


@router.post("/panels/{panel_id}/lipsync/apply", response_model=ApiResponse[PanelResponse])
async def apply_panel_lipsync(panel_id: str, body: ProviderApplyRequest, db: AsyncSession = Depends(get_db)):
    panel = await _get_panel_or_404(panel_id, db)
    panel.lipsync_video_url = body.result_url.strip()
    panel.status = PANEL_STATUS_COMPLETED
    panel.error_message = None
    await db.commit()
    await db.refresh(panel)
    return ApiResponse(data=_to_panel_response(panel))
