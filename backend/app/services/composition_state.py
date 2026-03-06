from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition_status import COMPOSITION_STATUS_COMPLETED, COMPOSITION_STATUS_STALE
from app.models import CompositionTask


async def mark_completed_compositions_stale(
    db: AsyncSession,
    project_id: str,
    *,
    episode_id: str | None = None,
    exclude_composition_id: str | None = None,
) -> None:
    """将受影响范围内的已完成成片标记为 stale；分集变更同时失效项目级总成片。"""
    stmt = (
        update(CompositionTask)
        .where(
            CompositionTask.project_id == project_id,
            CompositionTask.status == COMPOSITION_STATUS_COMPLETED,
        )
        .values(status=COMPOSITION_STATUS_STALE)
    )
    if episode_id:
        stmt = stmt.where(
            (CompositionTask.episode_id == episode_id)
            | (CompositionTask.episode_id.is_(None))
        )
    if exclude_composition_id:
        stmt = stmt.where(CompositionTask.id != exclude_composition_id)
    await db.execute(stmt)
