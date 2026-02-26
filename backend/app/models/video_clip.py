from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class VideoClip(Base):
    """视频片段：单个场景生成的视频文件"""

    __tablename__ = "video_clips"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scene_id: Mapped[str] = mapped_column(String(36), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    clip_order: Mapped[int] = mapped_column(Integer, default=0)
    candidate_index: Mapped[int] = mapped_column(Integer, default=0)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=True)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0.0)
    provider_task_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    scene: Mapped["Scene"] = relationship("Scene", back_populates="video_clips")
