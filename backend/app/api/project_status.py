from __future__ import annotations

from collections.abc import Iterable

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project


async def claim_project_status_or_409(
    db: AsyncSession,
    *,
    project_id: str,
    target_status: str,
    allowed_from_statuses: Iterable[str],
    action_label: str,
    recover_hint_status: str | None = None,
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

    detail = f"项目状态 {current.status} 不允许{action_label}"
    if recover_hint_status and current.status == recover_hint_status:
        detail += "；若任务已中断，可传 force_recover=true 强制恢复后重试"
    raise HTTPException(status_code=409, detail=detail)


async def try_restore_project_status(db: AsyncSession, project_id: str, fallback_status: str) -> None:
    """尽力恢复项目状态；项目不存在时静默跳过。"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        return
    project.status = fallback_status
    await db.commit()


async def force_recover_project_status(
    db: AsyncSession,
    *,
    project: Project,
    busy_status: str,
    recovered_status: str,
) -> bool:
    """在 force_recover 场景下，将项目从忙状态恢复到可操作状态。"""
    if project.status != busy_status:
        return False
    project.status = recovered_status
    await db.commit()
    await db.refresh(project)
    return True


async def restore_project_status_and_raise_submit_error(
    db: AsyncSession,
    *,
    project_id: str,
    fallback_status: str,
    detail_prefix: str,
    error: Exception,
) -> None:
    """异步任务提交失败时，先尽力恢复项目状态，再统一抛出 500。"""
    await try_restore_project_status(db, project_id, fallback_status)
    raise HTTPException(status_code=500, detail=f"{detail_prefix}: {error}") from error
