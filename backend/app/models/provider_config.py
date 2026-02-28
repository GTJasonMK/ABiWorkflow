from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ProviderConfig(Base):
    """HTTP Provider 统一配置。"""

    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    provider_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    submit_path: Mapped[str] = mapped_column(String(200), default="/submit", nullable=False)
    status_path: Mapped[str] = mapped_column(String(200), default="/status/{task_id}", nullable=False)
    result_path: Mapped[str] = mapped_column(String(200), default="/result/{task_id}", nullable=False)

    auth_scheme: Mapped[str] = mapped_column(String(30), default="bearer", nullable=False)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_header: Mapped[str] = mapped_column(String(100), default="Authorization", nullable=False)
    extra_headers_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    request_template_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    response_mapping_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_mapping_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    timeout_seconds: Mapped[float] = mapped_column(Float, default=60.0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
