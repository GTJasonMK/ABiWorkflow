from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import TaskRecord
from app.project_status import PROJECT_STATUS_DRAFT, PROJECT_STATUS_PARSED
from app.schemas.common import ApiResponse
from app.services.json_codec import from_json_text
from app.services.task_records import (
    create_task_record,
    get_task_record_by_id,
    get_task_record_by_source_id,
    serialize_task_record,
    update_task_record,
)
from app.task_record_status import TASK_RECORD_READY_STATUSES, TASK_RECORD_STATUS_CANCELLED
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/tasks", tags=["任务状态"])


class DismissFailedRequest(BaseModel):
    project_id: str | None = None
    task_ids: list[str] | None = None


def _normalize_task_payload(record: TaskRecord) -> dict:
    payload = from_json_text(record.payload_json, {})
    return payload if isinstance(payload, dict) else {}


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
    stmt = select(TaskRecord).order_by(TaskRecord.updated_at.desc()).limit(limit)
    if project_id:
        stmt = stmt.where(TaskRecord.project_id == project_id)
    if episode_id:
        stmt = stmt.where(TaskRecord.episode_id == episode_id)
    if panel_id:
        stmt = stmt.where(TaskRecord.panel_id == panel_id)
    if status:
        stmt = stmt.where(TaskRecord.status == status)
    if not include_dismissed:
        stmt = stmt.where(TaskRecord.dismissed == False)  # noqa: E712
    rows = (await db.execute(stmt)).scalars().all()
    return ApiResponse(data=[serialize_task_record(item) for item in rows])


@router.get("/{task_id}", response_model=ApiResponse[dict])
async def get_task_status(task_id: str, db: AsyncSession = Depends(get_db)):
    """查询任务状态，优先返回统一任务中心记录，不存在时回退到 Celery AsyncResult。"""
    record = await get_task_record_by_id(db, task_id)
    if record is None:
        record = await get_task_record_by_source_id(db, task_id)
    if record is not None:
        return ApiResponse(data=serialize_task_record(record))

    result = AsyncResult(task_id, app=celery_app)

    payload: dict = {
        "task_id": task_id,
        "state": result.state.lower(),
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else False,
    }

    if result.ready():
        if result.successful():
            task_result = result.result
            payload["result"] = task_result if isinstance(task_result, dict) else {"value": str(task_result)}
        else:
            payload["error"] = str(result.result)

    return ApiResponse(data=payload)


@router.post("/{task_id}/dismiss", response_model=ApiResponse[dict])
async def dismiss_task(task_id: str, db: AsyncSession = Depends(get_db)):
    record = await get_task_record_by_id(db, task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    record.dismissed = True
    await db.commit()
    await db.refresh(record)
    return ApiResponse(data=serialize_task_record(record))


@router.post("/dismiss-failed", response_model=ApiResponse[dict])
async def dismiss_failed_tasks(body: DismissFailedRequest, db: AsyncSession = Depends(get_db)):
    """批量忽略失败任务（用于任务中心清理）。"""
    stmt = select(TaskRecord).where(TaskRecord.status.in_(["failed", "cancelled"]))
    if body.project_id:
        stmt = stmt.where(TaskRecord.project_id == body.project_id)
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
    """重试指定任务（当前支持 parse / generate / compose / episode_split_llm）。"""
    record = await get_task_record_by_id(db, task_id)
    if record is None:
        record = await get_task_record_by_source_id(db, task_id)
    if record is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if record.status not in TASK_RECORD_READY_STATUSES:
        raise HTTPException(status_code=409, detail="任务仍在执行中，暂不支持重试")

    payload = _normalize_task_payload(record)
    project_id = (
        str(payload.get("project_id")).strip()
        if isinstance(payload.get("project_id"), str)
        else (record.project_id or "")
    )

    celery_task_id: str | None = None
    enqueue_message = "重试任务已排队"
    if record.task_type == "parse":
        if not project_id:
            raise HTTPException(status_code=400, detail="parse 任务缺少 project_id，无法重试")
        from app.tasks.parse_tasks import parse_script_task

        task = parse_script_task.delay(project_id, PROJECT_STATUS_DRAFT, None)
        celery_task_id = task.id
    elif record.task_type == "generate":
        if not project_id:
            raise HTTPException(status_code=400, detail="generate 任务缺少 project_id，无法重试")

        episode_id = (
            str(payload.get("episode_id")).strip()
            if isinstance(payload.get("episode_id"), str)
            else (record.episode_id or None)
        )
        if episode_id:
            raise HTTPException(status_code=400, detail="分集生成任务请回到对应分集页面重试")

        from app.tasks.generate_tasks import generate_videos_task

        force_regenerate = bool(payload.get("force_regenerate"))
        task = generate_videos_task.delay(project_id, PROJECT_STATUS_PARSED, force_regenerate)
        celery_task_id = task.id
    elif record.task_type == "compose":
        if not project_id:
            raise HTTPException(status_code=400, detail="compose 任务缺少 project_id，无法重试")
        from app.tasks.compose_tasks import compose_video_task

        options = payload.get("options")
        options_dict = options if isinstance(options, dict) else {}
        episode_id = (
            str(payload.get("episode_id")).strip()
            if isinstance(payload.get("episode_id"), str)
            else (record.episode_id or None)
        )
        task = compose_video_task.delay(project_id, options_dict, PROJECT_STATUS_PARSED, episode_id)
        celery_task_id = task.id
    elif record.task_type == "episode_split_llm":
        content = payload.get("content")
        if not project_id or not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=400, detail="AI 分集任务缺少有效输入内容，无法重试")
        from app.tasks.import_tasks import split_episodes_llm_task

        task = split_episodes_llm_task.delay(project_id, content)
        celery_task_id = task.id
    else:
        raise HTTPException(status_code=400, detail=f"任务类型 {record.task_type} 暂不支持重试")

    next_payload = {**payload, "retry_from": record.id}
    next_record = await create_task_record(
        db,
        task_type=record.task_type,
        target_type=record.target_type,
        target_id=record.target_id,
        project_id=record.project_id,
        episode_id=record.episode_id,
        panel_id=record.panel_id,
        source_task_id=celery_task_id,
        status="pending",
        message=enqueue_message,
        payload=next_payload,
    )
    next_record.retry_count = int(record.retry_count or 0) + 1
    await db.commit()
    await db.refresh(next_record)
    return ApiResponse(data=serialize_task_record(next_record))


@router.post("/{task_id}/cancel", response_model=ApiResponse[dict])
async def cancel_task(task_id: str, db: AsyncSession = Depends(get_db)):
    record = await get_task_record_by_id(db, task_id)
    if record is None:
        record = await get_task_record_by_source_id(db, task_id)

    celery_id = record.source_task_id if record else task_id
    if celery_id:
        try:
            celery_app.control.revoke(celery_id, terminate=True)
        except Exception:  # noqa: BLE001
            pass

    if record is None:
        result = AsyncResult(task_id, app=celery_app)
        payload = {
            "task_id": task_id,
            "state": result.state.lower(),
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else False,
            "cancel_requested": True,
        }
        return ApiResponse(data=payload)

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
