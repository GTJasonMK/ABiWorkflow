from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import TaskRecord
from app.schemas.common import ApiResponse
from app.services.task_records import (
    get_task_record_by_id,
    get_task_record_by_source_id,
    serialize_task_record,
    update_task_record,
)
from app.task_record_status import TASK_RECORD_READY_STATUSES, TASK_RECORD_STATUS_CANCELLED
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/tasks", tags=["任务状态"])


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
