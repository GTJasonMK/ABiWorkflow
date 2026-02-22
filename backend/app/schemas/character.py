from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CharacterUpdate(BaseModel):
    """更新角色请求"""

    name: str | None = Field(None, max_length=100)
    appearance: str | None = None
    personality: str | None = None
    costume: str | None = None
    reference_image_url: str | None = None


class CharacterResponse(BaseModel):
    """角色响应"""

    id: str
    project_id: str
    name: str
    appearance: str | None
    personality: str | None
    costume: str | None
    reference_image_url: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
