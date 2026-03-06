from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    """创建项目请求"""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None


class ProjectUpdate(BaseModel):
    """更新项目请求"""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    script_text: str | None = None


class ProjectResponse(BaseModel):
    """项目响应"""

    id: str
    name: str
    description: str | None
    script_text: str | None
    status: str
    episode_count: int = 0
    panel_count: int = 0
    generated_panel_count: int = 0
    character_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListItem(BaseModel):
    """项目列表项（不含剧本全文）"""

    id: str
    name: str
    description: str | None
    status: str
    episode_count: int = 0
    panel_count: int = 0
    generated_panel_count: int = 0
    character_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
