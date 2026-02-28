from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import resolve_database_url, settings
from app.services.task_records import get_task_record_by_source_id, update_task_record


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
    engine = create_async_engine(resolve_database_url(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db:
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
    finally:
        await engine.dispose()
