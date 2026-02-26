from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompositionTask


async def mark_completed_compositions_stale(
    db: AsyncSession,
    project_id: str,
    *,
    exclude_composition_id: str | None = None,
) -> None:
    """将项目下已完成成片统一标记为 stale。"""
    stmt = (
        update(CompositionTask)
        .where(
            CompositionTask.project_id == project_id,
            CompositionTask.status == "completed",
        )
        .values(status="stale")
    )
    if exclude_composition_id:
        stmt = stmt.where(CompositionTask.id != exclude_composition_id)
    await db.execute(stmt)
