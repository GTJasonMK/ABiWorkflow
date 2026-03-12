from __future__ import annotations

from typing import Any, Callable

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Panel, TaskRecord
from app.panel_status import PANEL_STATUS_PROCESSING
from app.project_status import PROJECT_STATUS_DRAFT, PROJECT_STATUS_PARSED
from app.schemas.common import ApiResponse
from app.services.costing import record_usage_cost
from app.services.json_codec import from_json_text
from app.services.provider_gateway import submit_provider_task
from app.services.task_records import (
    create_task_record,
    get_task_record_by_id,
    get_task_record_by_source_id,
    serialize_task_record,
    task_record_query,
    update_task_record,
)
from app.task_record_status import TASK_RECORD_READY_STATUSES, TASK_RECORD_STATUS_CANCELLED, TASK_RECORD_STATUS_RUNNING
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/tasks", tags=["任务状态"])


class DismissFailedRequest(BaseModel):
    project_id: str | None = None
    task_ids: list[str] | None = None


RetryHandler = Callable[[TaskRecord, dict[str, Any]], str]

_PROVIDER_USAGE_TYPES: dict[str, str] = {
    "video": "panel_video_generate",
    "tts": "panel_tts_generate",
    "lipsync": "panel_lipsync_generate",
}

_PROVIDER_LABELS: dict[str, str] = {
    "video": "视频",
    "tts": "语音",
    "lipsync": "口型同步",
}


def _normalize_task_payload(record: TaskRecord) -> dict[str, Any]:
    payload = from_json_text(record.payload_json, {})
    return payload if isinstance(payload, dict) else {}


def _payload_text(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _task_project_id(record: TaskRecord, payload: dict[str, Any]) -> str:
    return _payload_text(payload, "project_id") or (record.project_id or "")


def _task_episode_id(record: TaskRecord, payload: dict[str, Any]) -> str | None:
    return _payload_text(payload, "episode_id") or record.episode_id


def _task_options(payload: dict[str, Any]) -> dict[str, Any]:
    options = payload.get("options")
    return dict(options) if isinstance(options, dict) else {}


def _parse_non_negative_float(value: Any) -> float:
    try:
        return max(0.0, float(value or 0.0))
    except (TypeError, ValueError):
        return 0.0


def _provider_task_field(task_type: str) -> str:
    return {
        "video": "video_provider_task_id",
        "tts": "tts_provider_task_id",
        "lipsync": "lipsync_provider_task_id",
    }[task_type]


def _provider_retry_usage_type(task_type: str, payload: dict[str, Any]) -> str:
    return _payload_text(payload, "usage_type") or _PROVIDER_USAGE_TYPES[task_type]


def _provider_retry_label(task_type: str) -> str:
    return _PROVIDER_LABELS[task_type]


def _reset_panel_outputs_for_provider_retry(panel: Panel, task_type: str) -> None:
    if task_type == "video":
        panel.video_url = None
        panel.lipsync_video_url = None
        panel.lipsync_provider_task_id = None
        panel.video_status = "queued"
        panel.lipsync_status = "idle"
        panel.status = PANEL_STATUS_PROCESSING
        panel.error_message = None
        return
    if task_type == "tts":
        panel.tts_audio_url = None
        panel.lipsync_video_url = None
        panel.lipsync_provider_task_id = None
        panel.tts_status = "queued"
        panel.lipsync_status = "idle"
        return
    if task_type == "lipsync":
        panel.lipsync_video_url = None
        panel.lipsync_status = "queued"


async def _load_active_panel_for_provider_retry(
    db: AsyncSession,
    *,
    record: TaskRecord,
    task_type: str,
) -> Panel:
    label = _provider_retry_label(task_type)
    if not record.panel_id:
        raise HTTPException(status_code=400, detail=f"{label}任务缺少 panel_id，无法重试")
    if not record.source_task_id:
        raise HTTPException(status_code=400, detail=f"{label}任务缺少 provider task_id，无法重试")

    panel = await db.get(Panel, record.panel_id)
    if panel is None:
        raise HTTPException(status_code=404, detail="关联分镜不存在")

    active_task_id = getattr(panel, _provider_task_field(task_type))
    if active_task_id != record.source_task_id:
        raise HTTPException(status_code=409, detail=f"当前分镜的{label}任务已变更，请回到对应分镜页面重新提交")
    return panel


async def _enqueue_panel_provider_retry(
    db: AsyncSession,
    *,
    record: TaskRecord,
    payload: dict[str, Any],
) -> dict[str, Any]:
    task_type = record.task_type
    label = _provider_retry_label(task_type)
    provider_key = _payload_text(payload, "provider_key")
    request = payload.get("request")
    if not provider_key or not isinstance(request, dict):
        raise HTTPException(status_code=400, detail=f"{label}任务缺少 provider_key 或 request，无法重试")

    panel = await _load_active_panel_for_provider_retry(db, record=record, task_type=task_type)
    try:
        submitted = await submit_provider_task(db, provider_key=provider_key, payload=dict(request))
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
    new_source_task_id = str(submitted["task_id"])

    _reset_panel_outputs_for_provider_retry(panel, task_type)
    setattr(panel, _provider_task_field(task_type), new_source_task_id)

    unit_price = _parse_non_negative_float(payload.get("unit_price"))
    model_name = _payload_text(payload, "model_name")
    usage_type = _provider_retry_usage_type(task_type, payload)
    return {
        "source_task_id": new_source_task_id,
        "status": TASK_RECORD_STATUS_RUNNING,
        "message": f"{label}重试已提交到 {provider_key}",
        "task_payload": {
            **payload,
            "provider_key": provider_key,
            "request": dict(request),
            "usage_type": usage_type,
            "model_name": model_name,
            "unit_price": unit_price,
        },
        "usage_cost": {
            "provider_type": task_type,
            "provider_name": provider_key,
            "model_name": model_name,
            "usage_type": usage_type,
            "quantity": 1.0,
            "unit": "request",
            "unit_price": unit_price,
            "project_id": record.project_id,
            "episode_id": record.episode_id,
            "panel_id": record.panel_id,
        },
    }


async def _get_task_record_by_ref(db: AsyncSession, task_id: str) -> TaskRecord | None:
    record = await get_task_record_by_id(db, task_id)
    if record is not None:
        return record
    return await get_task_record_by_source_id(db, task_id)


async def _get_task_record_or_404(db: AsyncSession, task_id: str) -> TaskRecord:
    record = await _get_task_record_by_ref(db, task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return record


def _enqueue_parse_retry(record: TaskRecord, payload: dict[str, Any]) -> str:
    project_id = _task_project_id(record, payload)
    if not project_id:
        raise HTTPException(status_code=400, detail="parse 任务缺少 project_id，无法重试")

    from app.tasks.parse_tasks import parse_script_task

    return parse_script_task.delay(project_id, PROJECT_STATUS_DRAFT, None).id


def _enqueue_generate_retry(record: TaskRecord, payload: dict[str, Any]) -> str:
    project_id = _task_project_id(record, payload)
    if not project_id:
        raise HTTPException(status_code=400, detail="generate 任务缺少 project_id，无法重试")
    if _task_episode_id(record, payload):
        raise HTTPException(status_code=400, detail="分集生成任务请回到对应分集页面重试")

    from app.tasks.generate_tasks import generate_videos_task

    force_regenerate = bool(payload.get("force_regenerate"))
    return generate_videos_task.delay(project_id, PROJECT_STATUS_PARSED, force_regenerate).id


def _enqueue_compose_retry(record: TaskRecord, payload: dict[str, Any]) -> str:
    project_id = _task_project_id(record, payload)
    if not project_id:
        raise HTTPException(status_code=400, detail="compose 任务缺少 project_id，无法重试")

    from app.tasks.compose_tasks import compose_video_task

    return compose_video_task.delay(
        project_id,
        _task_options(payload),
        PROJECT_STATUS_PARSED,
        _task_episode_id(record, payload),
    ).id


def _enqueue_episode_split_retry(record: TaskRecord, payload: dict[str, Any]) -> str:
    project_id = _task_project_id(record, payload)
    content = payload.get("content")
    if not project_id or not isinstance(content, str) or not content.strip():
        raise HTTPException(status_code=400, detail="AI 分集任务缺少有效输入内容，无法重试")

    from app.tasks.import_tasks import split_episodes_llm_task

    return split_episodes_llm_task.delay(project_id, content).id


RETRY_HANDLERS: dict[str, RetryHandler] = {
    "parse": _enqueue_parse_retry,
    "generate": _enqueue_generate_retry,
    "compose": _enqueue_compose_retry,
    "episode_split_llm": _enqueue_episode_split_retry,
}


async def _create_retry_task_record(
    db: AsyncSession,
    *,
    record: TaskRecord,
    payload: dict[str, Any],
    source_task_id: str,
    message: str,
    status: str = "pending",
) -> TaskRecord:
    next_record = await create_task_record(
        db,
        task_type=record.task_type,
        target_type=record.target_type,
        target_id=record.target_id,
        project_id=record.project_id,
        episode_id=record.episode_id,
        panel_id=record.panel_id,
        source_task_id=source_task_id,
        status=status,
        message=message,
        payload={**payload, "retry_from": record.id},
    )
    next_record.retry_count = int(record.retry_count or 0) + 1
    await db.flush()
    return next_record


@router.get("", response_model=ApiResponse[list[dict]])
async def list_tasks(
    project_id: str | None = None,
    episode_id: str | None = None,
    panel_id: str | None = None,
    status: str | None = None,
    include_dismissed: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        task_record_query(
            project_id=project_id,
            episode_id=episode_id,
            panel_id=panel_id,
            status=status,
            include_dismissed=include_dismissed,
        )
        .order_by(TaskRecord.updated_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return ApiResponse(data=[serialize_task_record(item) for item in rows])


@router.get("/{task_id}", response_model=ApiResponse[dict])
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_db)):
    """查询任务状态。"""
    record = await _get_task_record_or_404(db, task_id)
    return ApiResponse(data=serialize_task_record(record))


@router.post("/{task_id}/dismiss", response_model=ApiResponse[dict])
async def dismiss_task(task_id: str, db: AsyncSession = Depends(get_db)):
    record = await _get_task_record_or_404(db, task_id)
    record.dismissed = True
    await db.commit()
    await db.refresh(record)
    return ApiResponse(data=serialize_task_record(record))


@router.post("/dismiss-failed", response_model=ApiResponse[dict])
async def dismiss_failed_tasks(body: DismissFailedRequest, db: AsyncSession = Depends(get_db)):
    """批量忽略失败任务（用于任务中心清理）。"""
    stmt = task_record_query(project_id=body.project_id, include_dismissed=True).where(
        TaskRecord.status.in_(["failed", "cancelled"])
    )
    if body.task_ids:
        stmt = stmt.where(TaskRecord.id.in_(body.task_ids))
    rows = (await db.execute(stmt)).scalars().all()

    dismissed = 0
    for task in rows:
        if task.dismissed:
            continue
        task.dismissed = True
        dismissed += 1

    await db.commit()
    return ApiResponse(data={"dismissed": dismissed})


@router.post("/{task_id}/retry", response_model=ApiResponse[dict])
async def retry_task(task_id: str, db: AsyncSession = Depends(get_db)):
    """重试指定任务，支持 parse / generate / compose / episode_split_llm / video / tts / lipsync。"""
    record = await _get_task_record_or_404(db, task_id)
    if record.status not in TASK_RECORD_READY_STATUSES:
        raise HTTPException(status_code=409, detail="任务仍在执行中，暂不支持重试")

    payload = _normalize_task_payload(record)
    if record.task_type in _PROVIDER_USAGE_TYPES:
        retry_result = await _enqueue_panel_provider_retry(db, record=record, payload=payload)
        next_record = await _create_retry_task_record(
            db,
            record=record,
            payload=retry_result["task_payload"],
            source_task_id=retry_result["source_task_id"],
            message=retry_result["message"],
            status=retry_result["status"],
        )
        usage_cost = retry_result.get("usage_cost")
        if isinstance(usage_cost, dict):
            await record_usage_cost(db, task_id=next_record.id, **usage_cost)
        await db.commit()
        await db.refresh(next_record)
        return ApiResponse(data=serialize_task_record(next_record))

    retry_handler = RETRY_HANDLERS.get(record.task_type)
    if retry_handler is None:
        raise HTTPException(status_code=400, detail=f"任务类型 {record.task_type} 暂不支持重试")

    next_record = await _create_retry_task_record(
        db,
        record=record,
        payload=payload,
        source_task_id=retry_handler(record, payload),
        message="重试任务已排队",
    )
    await db.commit()
    await db.refresh(next_record)
    return ApiResponse(data=serialize_task_record(next_record))


@router.post("/{task_id}/cancel", response_model=ApiResponse[dict])
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db)):
    record = await _get_task_record_or_404(db, task_id)
    if record.task_type in _PROVIDER_USAGE_TYPES and record.status not in TASK_RECORD_READY_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="外部 provider 任务暂不支持从任务中心取消，请回到 provider 侧处理或等待完成",
        )

    if record.source_task_id:
        try:
            celery_app.control.revoke(record.source_task_id, terminate=True)
        except Exception:  # noqa: BLE001
            pass

    if record.status not in TASK_RECORD_READY_STATUSES:
        await update_task_record(
            db,
            task=record,
            status=TASK_RECORD_STATUS_CANCELLED,
            message="任务已取消",
            error_message="任务被用户取消",
            event_type="cancelled",
        )
        await db.commit()
        await db.refresh(record)
    return ApiResponse(data=serialize_task_record(record))
