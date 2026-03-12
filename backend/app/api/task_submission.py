from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.task_records import create_task_record


async def submit_async_task_with_record(
    db: AsyncSession,
    *,
    submit: Callable[[], Any],
    task_type: str,
    target_type: str,
    target_id: str,
    project_id: str | None,
    episode_id: str | None = None,
    panel_id: str | None = None,
    message: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    task = submit()
    await create_task_record(
        db,
        task_type=task_type,
        target_type=target_type,
        target_id=target_id,
        project_id=project_id,
        episode_id=episode_id,
        panel_id=panel_id,
        source_task_id=task.id,
        status="pending",
        message=message,
        payload=payload,
    )
    await db.commit()
    return {
        "task_id": task.id,
        "mode": "async",
        "status": "queued",
    }
