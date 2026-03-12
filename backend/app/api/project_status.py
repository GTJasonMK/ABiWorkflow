from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.services.project_status_ops import (
    commit_project_status as commit_project_status_base,
)
from app.services.project_status_ops import (
    restore_project_status_if_exists,
)
from app.services.project_status_ops import (
    rollback_and_restore_project_status as rollback_and_restore_project_status_base,
)

commit_project_status = commit_project_status_base


async def claim_project_status_or_409(
    db: AsyncSession,
    *,
    project_id: str,
    target_status: str,
    allowed_from_statuses: Iterable[str],
    action_label: str,
) -> None:
    """抢占项目状态；失败时统一抛出 409。"""
    claim_result = await db.execute(
        update(Project)
        .where(
            Project.id == project_id,
            Project.status.in_(list(allowed_from_statuses)),
        )
        .values(status=target_status)
    )
    if claim_result.rowcount > 0:
        return

    current = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if current is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    raise HTTPException(status_code=409, detail=f"项目状态 {current.status} 不允许{action_label}")


async def rollback_and_restore_project_status(
    db: AsyncSession,
    *,
    project_id: str,
    fallback_status: str,
) -> Project | None:
    return await rollback_and_restore_project_status_base(
        db,
        project_id=project_id,
        restore_status=fallback_status,
    )


async def restore_project_status_and_raise_submit_error(
    db: AsyncSession,
    *,
    project_id: str,
    fallback_status: str,
    detail_prefix: str,
    error: Exception,
) -> None:
    """异步任务提交失败时，先尽力恢复项目状态，再统一抛出 500。"""
    await restore_project_status_if_exists(db, project_id, fallback_status)
    raise HTTPException(status_code=500, detail=f"{detail_prefix}: {error}") from error
