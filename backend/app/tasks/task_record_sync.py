from __future__ import annotations

from typing import Any

from app.services.task_records import get_task_record_by_source_id, update_task_record
from app.tasks.db_session import task_session


async def sync_task_record_status(
    *,
    source_task_id: str,
    status: str,
    progress_percent: float | None = None,
    message: str | None = None,
    error_message: str | None = None,
    result: dict[str, Any] | None = None,
    event_type: str = "worker_update",
) -> None:
    async with task_session() as db:
        record = await get_task_record_by_source_id(db, source_task_id)
        if record is None:
            return
        await update_task_record(
            db,
            task=record,
            status=status,
            progress_percent=progress_percent,
            message=message,
            error_message=error_message,
            result=result,
            event_type=event_type,
        )
        await db.commit()
