from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response_utils import isoformat_or_none
from app.database import get_db
from app.models import UsageCost
from app.schemas.common import ApiResponse
from app.services.costing import summarize_costs
from app.services.json_codec import from_json_text

router = APIRouter(tags=["成本统计"])


def _cost_payload(item: UsageCost) -> dict[str, Any]:
    return {
        "id": item.id,
        "project_id": item.project_id,
        "episode_id": item.episode_id,
        "panel_id": item.panel_id,
        "task_id": item.task_id,
        "provider_type": item.provider_type,
        "provider_name": item.provider_name,
        "model_name": item.model_name,
        "usage_type": item.usage_type,
        "quantity": float(item.quantity or 0.0),
        "unit": item.unit,
        "unit_price": float(item.unit_price or 0.0),
        "total_cost": float(item.total_cost or 0.0),
        "currency": item.currency,
        "metadata": from_json_text(item.metadata_json, {}),
        "created_at": isoformat_or_none(item.created_at),
    }


@router.get("/costs", response_model=ApiResponse[dict])
async def list_costs(
    project_id: str | None = None,
    episode_id: str | None = None,
    panel_id: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(UsageCost).order_by(UsageCost.created_at.desc()).limit(limit)
    if project_id:
        stmt = stmt.where(UsageCost.project_id == project_id)
    if episode_id:
        stmt = stmt.where(UsageCost.episode_id == episode_id)
    if panel_id:
        stmt = stmt.where(UsageCost.panel_id == panel_id)
    rows = (await db.execute(stmt)).scalars().all()

    summary = await summarize_costs(
        db,
        project_id=project_id,
        episode_id=episode_id,
        panel_id=panel_id,
    )
    return ApiResponse(data={
        "summary": summary,
        "items": [_cost_payload(item) for item in rows],
    })


@router.get("/projects/{project_id}/costs", response_model=ApiResponse[dict])
async def get_project_costs(
    project_id: str,
    limit: int = Query(default=200, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(UsageCost)
        .where(UsageCost.project_id == project_id)
        .order_by(UsageCost.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    summary = await summarize_costs(db, project_id=project_id)
    return ApiResponse(data={
        "summary": summary,
        "items": [_cost_payload(item) for item in rows],
    })
