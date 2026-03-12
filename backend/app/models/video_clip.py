from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clip_status import CLIP_STATUS_PENDING
from app.database import Base


class VideoClip(Base):
    """视频片段：单个分镜生成的视频文件"""

    __tablename__ = "video_clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    panel_id: Mapped[str] = mapped_column(String(36), ForeignKey("panels.id", ondelete="CASCADE"), nullable=False, index=True)
    clip_order: Mapped[int] = mapped_column(Integer, default=0)
    candidate_index: Mapped[int] = mapped_column(Integer, default=0)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    provider_task_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=CLIP_STATUS_PENDING)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    panel: Mapped["Panel"] = relationship("Panel", back_populates="video_clips")
