from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.episode_status import EPISODE_STATUS_DRAFT


class Episode(Base):
    """分集实体：一个项目下可包含多个分集。"""

    __tablename__ = "episodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    episode_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    script_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_provider_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    tts_provider_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lipsync_provider_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    provider_payload_defaults_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    skipped_checks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=EPISODE_STATUS_DRAFT, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="episodes")
    panels: Mapped[list["Panel"]] = relationship(
        "Panel",
        back_populates="episode",
        cascade="all, delete-orphan",
        order_by="Panel.panel_order",
    )
    asset_overrides: Mapped[list["EpisodeAssetOverride"]] = relationship(
        "EpisodeAssetOverride",
        back_populates="episode",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
