from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.panel_status import PANEL_STATUS_DRAFT


class Panel(Base):
    """分镜实体：分集下可执行生成、配音、口型同步的最小单元。"""

    __tablename__ = "panels"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    episode_id: Mapped[str] = mapped_column(String(36), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False)
    panel_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    script_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera_hint: Mapped[str | None] = mapped_column(String(200), nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    style_preset: Mapped[str | None] = mapped_column(String(100), nullable=True)
    reference_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    voice_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("global_voices.id"), nullable=True)
    tts_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    tts_audio_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lipsync_video_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_provider_task_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tts_provider_task_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    lipsync_provider_task_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    video_status: Mapped[str] = mapped_column(String(20), default="idle", nullable=False)
    tts_status: Mapped[str] = mapped_column(String(20), default="idle", nullable=False)
    lipsync_status: Mapped[str] = mapped_column(String(20), default="idle", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=PANEL_STATUS_DRAFT, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="panels")
    episode: Mapped["Episode"] = relationship("Episode", back_populates="panels")
    voice: Mapped["GlobalVoice"] = relationship("GlobalVoice", back_populates="panels")
    asset_overrides: Mapped[list["PanelAssetOverride"]] = relationship(
        "PanelAssetOverride",
        back_populates="panel",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    video_clips: Mapped[list["VideoClip"]] = relationship(
        "VideoClip",
        back_populates="panel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="VideoClip.clip_order",
    )
    effective_binding: Mapped["PanelEffectiveBinding | None"] = relationship(
        "PanelEffectiveBinding",
        back_populates="panel",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
