from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.task_record_status import TASK_RECORD_STATUS_PENDING


class TaskRecord(Base):
    """统一任务中心记录。"""

    __tablename__ = "task_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    episode_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("episodes.id", ondelete="SET NULL"), nullable=True)
    panel_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("panels.id", ondelete="SET NULL"), nullable=True)

    source_task_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default=TASK_RECORD_STATUS_PENDING, nullable=False)
    progress_percent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    dismissed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    project: Mapped["Project"] = relationship("Project")
    episode: Mapped["Episode"] = relationship("Episode")
    panel: Mapped["Panel"] = relationship("Panel")
    events: Mapped[list["TaskEvent"]] = relationship(
        "TaskEvent",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskEvent.event_no",
    )


class TaskEvent(Base):
    """任务事件流，支持 SSE replay。"""

    __tablename__ = "task_events"

    event_no: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id: Mapped[str] = mapped_column(String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    task_id: Mapped[str] = mapped_column(String(36), ForeignKey("task_records.id", ondelete="CASCADE"), nullable=False)

    project_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    episode_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("episodes.id", ondelete="SET NULL"), nullable=True)
    panel_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("panels.id", ondelete="SET NULL"), nullable=True)

    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    task: Mapped["TaskRecord"] = relationship("TaskRecord", back_populates="events")
