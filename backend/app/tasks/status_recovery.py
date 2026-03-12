from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable
from typing import TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.project_status_ops import (
    commit_project_status as commit_project_status_base,
)
from app.services.project_status_ops import (
    restore_project_status_async,
)
from app.services.project_status_ops import (
    rollback_and_restore_project_status as rollback_and_restore_project_status_base,
)
from app.tasks.task_record_sync import sync_task_record_status

commit_project_status = commit_project_status_base

T = TypeVar("T")


def run_async_in_new_loop(awaitable: Awaitable[T]) -> T:
    """在独立 event loop 中运行协程，适配 Celery 同步任务上下文。"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(awaitable)
    finally:
        loop.close()


async def rollback_and_restore_project_status(
    db: AsyncSession,
    *,
    project_id: str,
    restore_status: str,
):
    return await rollback_and_restore_project_status_base(
        db,
        project_id=project_id,
        restore_status=restore_status,
    )


def restore_project_status_after_task_failure(
    project_id: str,
    transient_status: str,
    fallback_status: str,
    *,
    task_name: str,
    logger: logging.Logger | None = None,
) -> None:
    """在任务异常提前退出时兜底回滚项目状态。"""
    try:
        run_async_in_new_loop(restore_project_status_async(project_id, transient_status, fallback_status))
    except Exception as err:  # noqa: BLE001 - 兜底逻辑不应影响原始异常传播
        if logger is not None:
            logger.warning("%s状态回滚失败: project=%s, err=%s", task_name, project_id, err)


def sync_worker_task_status(
    source_task_id: str,
    *,
    status: str,
    message: str,
    progress_percent: float | None = None,
    error_message: str | None = None,
    result: dict | None = None,
    event_type: str,
) -> None:
    run_async_in_new_loop(
        sync_task_record_status(
            source_task_id=source_task_id,
            status=status,
            progress_percent=progress_percent,
            message=message,
            error_message=error_message,
            result=result,
            event_type=event_type,
        )
    )


def mark_worker_task_started(source_task_id: str, message: str, *, progress_percent: float = 2.0) -> None:
    sync_worker_task_status(
        source_task_id,
        status="running",
        progress_percent=progress_percent,
        message=message,
        event_type="worker_started",
    )


def mark_worker_task_completed(source_task_id: str, message: str, result: dict) -> None:
    sync_worker_task_status(
        source_task_id,
        status="completed",
        progress_percent=100.0,
        message=message,
        result=result,
        event_type="worker_completed",
    )


def mark_worker_task_failed(source_task_id: str, message: str, error_message: str) -> None:
    sync_worker_task_status(
        source_task_id,
        status="failed",
        progress_percent=100.0,
        message=message,
        error_message=error_message,
        event_type="worker_failed",
    )
