from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageCost
from app.services.json_codec import to_json_text


async def record_usage_cost(
    db: AsyncSession,
    *,
    provider_type: str,
    usage_type: str,
    quantity: float,
    unit_price: float,
    unit: str = "count",
    currency: str = "USD",
    provider_name: str | None = None,
    model_name: str | None = None,
    project_id: str | None = None,
    episode_id: str | None = None,
    panel_id: str | None = None,
    task_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> UsageCost:
    quantity_value = float(quantity or 0.0)
    unit_price_value = float(unit_price or 0.0)
    total_cost = quantity_value * unit_price_value
    entry = UsageCost(
        provider_type=provider_type,
        provider_name=provider_name,
        model_name=model_name,
        usage_type=usage_type,
        quantity=quantity_value,
        unit=unit,
        unit_price=unit_price_value,
        total_cost=total_cost,
        currency=currency,
        project_id=project_id,
        episode_id=episode_id,
        panel_id=panel_id,
        task_id=task_id,
        metadata_json=to_json_text(metadata),
    )
    db.add(entry)
    await db.flush()
    return entry


def _apply_cost_filters(
    stmt,
    *,
    project_id: str | None = None,
    episode_id: str | None = None,
    panel_id: str | None = None,
):
    if project_id:
        stmt = stmt.where(UsageCost.project_id == project_id)
    if episode_id:
        stmt = stmt.where(UsageCost.episode_id == episode_id)
    if panel_id:
        stmt = stmt.where(UsageCost.panel_id == panel_id)
    return stmt


async def summarize_costs(
    db: AsyncSession,
    *,
    project_id: str | None = None,
    episode_id: str | None = None,
    panel_id: str | None = None,
) -> dict[str, Any]:
    sum_stmt = _apply_cost_filters(
        select(
            func.count(UsageCost.id),
            func.coalesce(func.sum(UsageCost.total_cost), 0.0),
            func.coalesce(func.sum(UsageCost.quantity), 0.0),
        ),
        project_id=project_id,
        episode_id=episode_id,
        panel_id=panel_id,
    )
    count_value, total_cost, total_quantity = (await db.execute(sum_stmt)).one()

    group_stmt = _apply_cost_filters(
        select(
            UsageCost.provider_type,
            func.count(UsageCost.id),
            func.coalesce(func.sum(UsageCost.total_cost), 0.0),
        ).group_by(UsageCost.provider_type),
        project_id=project_id,
        episode_id=episode_id,
        panel_id=panel_id,
    )
    by_provider = [
        {
            "provider_type": provider_type,
            "count": int(count or 0),
            "total_cost": float(cost or 0.0),
        }
        for provider_type, count, cost in (await db.execute(group_stmt)).all()
    ]

    return {
        "count": int(count_value or 0),
        "total_cost": float(total_cost or 0.0),
        "total_quantity": float(total_quantity or 0.0),
        "currency": "USD",
        "by_provider": by_provider,
    }
