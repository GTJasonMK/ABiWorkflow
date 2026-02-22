from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Scene(Base):
    """场景描述：剧本拆分后的单个场景"""

    __tablename__ = "scenes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sequence_order: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    video_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    negative_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    camera_movement: Mapped[str | None] = mapped_column(String(200), nullable=True)
    setting: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_keywords: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dialogue: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[float] = mapped_column(Float, default=5.0)
    transition_hint: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="scenes")
    characters: Mapped[list["SceneCharacter"]] = relationship(
        "SceneCharacter", back_populates="scene", cascade="all, delete-orphan"
    )
    video_clips: Mapped[list["VideoClip"]] = relationship(
        "VideoClip", back_populates="scene", cascade="all, delete-orphan", order_by="VideoClip.clip_order"
    )


class SceneCharacter(Base):
    """场景-角色关联表"""

    __tablename__ = "scene_characters"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scene_id: Mapped[str] = mapped_column(String(36), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False)
    character_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    action: Mapped[str | None] = mapped_column(Text, nullable=True)
    emotion: Mapped[str | None] = mapped_column(String(100), nullable=True)

    scene: Mapped["Scene"] = relationship("Scene", back_populates="characters")
    character: Mapped["Character"] = relationship("Character", back_populates="scenes")
