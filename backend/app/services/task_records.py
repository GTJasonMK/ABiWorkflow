from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import TaskEvent, TaskRecord
from app.services.json_codec import from_json_text, to_json_text
from app.task_record_status import TASK_RECORD_READY_STATUSES, TASK_RECORD_STATUS_RUNNING


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def create_task_record(
    db: AsyncSession,
    *,
    task_type: str,
    target_type: str | None = None,
    target_id: str | None = None,
    project_id: str | None = None,
    episode_id: str | None = None,
    panel_id: str | None = None,
    source_task_id: str | None = None,
    status: str = "pending",
    progress_percent: float = 0.0,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> TaskRecord:
    record = TaskRecord(
        task_type=task_type,
        target_type=target_type,
        target_id=target_id,
        project_id=project_id,
        episode_id=episode_id,
        panel_id=panel_id,
        source_task_id=source_task_id,
        status=status,
        progress_percent=progress_percent,
        message=message,
        payload_json=to_json_text(payload),
        started_at=utcnow() if status == TASK_RECORD_STATUS_RUNNING else None,
    )
    db.add(record)
    await db.flush()

    await append_task_event(
        db,
        task=record,
        event_type="created",
        status=status,
        progress_percent=progress_percent,
        message=message,
        payload=payload,
    )
    return record


async def append_task_event(
    db: AsyncSession,
    *,
    task: TaskRecord,
    event_type: str,
    status: str | None = None,
    progress_percent: float | None = None,
    message: str | None = None,
    payload: dict[str, Any] | None = None,
) -> TaskEvent:
    event = TaskEvent(
        task_id=task.id,
        project_id=task.project_id,
        episode_id=task.episode_id,
        panel_id=task.panel_id,
        event_type=event_type,
        status=status,
        progress_percent=progress_percent,
        message=message,
        payload_json=to_json_text(payload),
    )
    db.add(event)
    await db.flush()
    return event


async def update_task_record(
    db: AsyncSession,
    *,
    task: TaskRecord,
    status: str | None = None,
    progress_percent: float | None = None,
    message: str | None = None,
    error_message: str | None = None,
    payload: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    event_type: str = "updated",
) -> TaskRecord:
    if status is not None:
        task.status = status
    if progress_percent is not None:
        task.progress_percent = progress_percent
    if message is not None:
        task.message = message
    if error_message is not None:
        task.error_message = error_message
    if payload is not None:
        task.payload_json = to_json_text(payload)
    if result is not None:
        task.result_json = to_json_text(result)

    if task.status == TASK_RECORD_STATUS_RUNNING and task.started_at is None:
        task.started_at = utcnow()
    if task.status in TASK_RECORD_READY_STATUSES and task.finished_at is None:
        task.finished_at = utcnow()

    await append_task_event(
        db,
        task=task,
        event_type=event_type,
        status=task.status,
        progress_percent=task.progress_percent,
        message=task.message or message,
        payload=payload or result,
    )
    await db.flush()
    return task


def task_record_query(
    *,
    project_id: str | None = None,
    episode_id: str | None = None,
    panel_id: str | None = None,
    status: str | None = None,
    include_dismissed: bool = False,
) -> Select[tuple[TaskRecord]]:
    stmt = select(TaskRecord)
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
    return stmt


async def get_task_record_by_id(db: AsyncSession, task_id: str) -> TaskRecord | None:
    return (await db.execute(select(TaskRecord).where(TaskRecord.id == task_id))).scalar_one_or_none()


async def get_task_record_by_source_id(db: AsyncSession, source_task_id: str) -> TaskRecord | None:
    return (
        await db.execute(select(TaskRecord).where(TaskRecord.source_task_id == source_task_id))
    ).scalar_one_or_none()


def serialize_task_record(task: TaskRecord) -> dict[str, Any]:
    ready = task.status in TASK_RECORD_READY_STATUSES
    successful = task.status == "completed"
    return {
        "id": task.id,
        "task_id": task.id,
        "source_task_id": task.source_task_id,
        "task_type": task.task_type,
        "target_type": task.target_type,
        "target_id": task.target_id,
        "project_id": task.project_id,
        "episode_id": task.episode_id,
        "panel_id": task.panel_id,
        "status": task.status,
        "state": task.status,
        "ready": ready,
        "successful": successful,
        "dismissed": task.dismissed,
        "progress_percent": float(task.progress_percent or 0.0),
        "message": task.message,
        "payload": from_json_text(task.payload_json, {}),
        "result": from_json_text(task.result_json, {}),
        "error": task.error_message,
        "retry_count": task.retry_count,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def serialize_task_event(event: TaskEvent) -> dict[str, Any]:
    return {
        "event_no": event.event_no,
        "id": event.id,
        "task_id": event.task_id,
        "project_id": event.project_id,
        "episode_id": event.episode_id,
        "panel_id": event.panel_id,
        "event_type": event.event_type,
        "status": event.status,
        "progress_percent": event.progress_percent,
        "message": event.message,
        "payload": from_json_text(event.payload_json, {}),
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
