from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ScriptEntity(Base):
    """剧本级实体：角色 / 地点 / 说话人。"""

    __tablename__ = "script_entities"
    __table_args__ = (
        UniqueConstraint("project_id", "entity_type", "name", name="uq_script_entity_name"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # character|location|speaker
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    alias: Mapped[str | None] = mapped_column(String(120), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="script_entities")
    bindings: Mapped[list["ScriptEntityAssetBinding"]] = relationship(
        "ScriptEntityAssetBinding",
        back_populates="entity",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    episode_overrides: Mapped[list["EpisodeAssetOverride"]] = relationship(
        "EpisodeAssetOverride",
        back_populates="entity",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    panel_overrides: Mapped[list["PanelAssetOverride"]] = relationship(
        "PanelAssetOverride",
        back_populates="entity",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ScriptEntityAssetBinding(Base):
    """剧本实体默认资产绑定。"""

    __tablename__ = "script_entity_asset_bindings"
    __table_args__ = (
        UniqueConstraint("entity_id", "asset_type", "asset_id", "role_tag", name="uq_script_entity_asset_binding"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("script_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # character|location|voice
    asset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    strategy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project", back_populates="script_entity_bindings")
    entity: Mapped["ScriptEntity"] = relationship("ScriptEntity", back_populates="bindings")


class EpisodeAssetOverride(Base):
    """分集级资产覆盖。"""

    __tablename__ = "episode_asset_overrides"
    __table_args__ = (
        UniqueConstraint("episode_id", "entity_id", "asset_type", "asset_id", "role_tag", name="uq_episode_asset_override"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    episode_id: Mapped[str] = mapped_column(String(36), ForeignKey("episodes.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("script_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    strategy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    episode: Mapped["Episode"] = relationship("Episode", back_populates="asset_overrides")
    entity: Mapped["ScriptEntity"] = relationship("ScriptEntity", back_populates="episode_overrides")


class PanelAssetOverride(Base):
    """分镜级资产覆盖。"""

    __tablename__ = "panel_asset_overrides"
    __table_args__ = (
        UniqueConstraint("panel_id", "entity_id", "asset_type", "asset_id", "role_tag", name="uq_panel_asset_override"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    panel_id: Mapped[str] = mapped_column(String(36), ForeignKey("panels.id", ondelete="CASCADE"), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(36), ForeignKey("script_entities.id", ondelete="CASCADE"), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    asset_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    asset_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role_tag: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    strategy_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    panel: Mapped["Panel"] = relationship("Panel", back_populates="asset_overrides")
    entity: Mapped["ScriptEntity"] = relationship("ScriptEntity", back_populates="panel_overrides")


class PanelEffectiveBinding(Base):
    """分镜编译后的生效绑定快照。"""

    __tablename__ = "panel_effective_bindings"

    panel_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("panels.id", ondelete="CASCADE"),
        primary_key=True,
    )
    compiled_json: Mapped[str] = mapped_column(Text, nullable=False)
    compiled_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    compiler_version: Mapped[str] = mapped_column(String(32), default="v1", nullable=False)
    compiled_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    panel: Mapped["Panel"] = relationship("Panel", back_populates="effective_binding")

