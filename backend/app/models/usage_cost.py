from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UsageCost(Base):
    """成本记录：用于统计而非余额扣减。"""

    __tablename__ = "usage_costs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    episode_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("episodes.id", ondelete="SET NULL"), nullable=True)
    panel_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("panels.id", ondelete="SET NULL"), nullable=True)
    task_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("task_records.id", ondelete="SET NULL"), nullable=True)

    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    usage_type: Mapped[str] = mapped_column(String(80), nullable=False)

    quantity: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    unit: Mapped[str] = mapped_column(String(30), default="count", nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD", nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    project: Mapped["Project"] = relationship("Project")
    episode: Mapped["Episode"] = relationship("Episode")
    panel: Mapped["Panel"] = relationship("Panel")
    task: Mapped["TaskRecord"] = relationship("TaskRecord")
