from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.composition_status import COMPOSITION_STATUS_PENDING
from app.database import Base

if TYPE_CHECKING:
    from app.models.episode import Episode
    from app.models.project import Project


class CompositionTask(Base):
    """合成任务：将多段视频合成为完整视频"""

    __tablename__ = "composition_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    episode_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("episodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    output_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    transition_type: Mapped[str] = mapped_column(String(50), default="crossfade")
    include_subtitles: Mapped[bool] = mapped_column(default=True)
    include_tts: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(String(20), default=COMPOSITION_STATUS_PENDING)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="composition_tasks")
    episode: Mapped["Episode | None"] = relationship("Episode")
