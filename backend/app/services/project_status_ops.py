from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.tasks.db_session import task_session


async def commit_project_status(db: AsyncSession, project: Project, status: str) -> Project:
    project.status = status
    await db.commit()
    return project


async def restore_project_status_if_exists(
    db: AsyncSession,
    project_id: str,
    restore_status: str,
) -> Project | None:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        return None
    return await commit_project_status(db, project, restore_status)


async def rollback_and_restore_project_status(
    db: AsyncSession,
    *,
    project_id: str,
    restore_status: str,
) -> Project | None:
    await db.rollback()
    return await restore_project_status_if_exists(db, project_id, restore_status)


async def restore_project_status_async(
    project_id: str,
    transient_status: str,
    restore_status: str,
) -> None:
    async with task_session() as db:
        await db.execute(
            update(Project)
            .where(Project.id == project_id, Project.status == transient_status)
            .values(status=restore_status)
        )
        await db.commit()
