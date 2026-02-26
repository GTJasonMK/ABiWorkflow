from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SceneUpdate(BaseModel):
    """更新场景请求"""

    title: str | None = Field(None, max_length=200)
    description: str | None = None
    video_prompt: str | None = None
    negative_prompt: str | None = None
    camera_movement: str | None = None
    setting: str | None = None
    style_keywords: str | None = None
    dialogue: str | None = None
    duration_seconds: float | None = Field(None, gt=0, le=60)
    transition_hint: str | None = None


class SceneCharacterResponse(BaseModel):
    """场景中的角色信息"""

    character_id: str
    character_name: str
    action: str | None
    emotion: str | None

    model_config = {"from_attributes": True}


class ClipSummary(BaseModel):
    """场景视频片段统计摘要"""

    total: int = 0
    completed: int = 0
    failed: int = 0


class ClipBrief(BaseModel):
    """视频片段简要信息"""

    id: str
    clip_order: int
    candidate_index: int = 0
    is_selected: bool = True
    status: str
    duration_seconds: float
    error_message: str | None = None


class CandidateClipResponse(BaseModel):
    """候选片段详情（含媒体地址）"""

    id: str
    clip_order: int
    candidate_index: int
    is_selected: bool
    status: str
    duration_seconds: float
    error_message: str | None = None
    media_url: str | None = None


class SceneResponse(BaseModel):
    """场景响应"""

    id: str
    project_id: str
    sequence_order: int
    title: str
    description: str | None
    video_prompt: str | None
    negative_prompt: str | None
    camera_movement: str | None
    setting: str | None
    style_keywords: str | None
    dialogue: str | None
    duration_seconds: float
    transition_hint: str | None
    status: str
    characters: list[SceneCharacterResponse] = []
    clip_summary: ClipSummary = Field(default_factory=ClipSummary)
    clips: list[ClipBrief] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SceneReorderRequest(BaseModel):
    """场景排序请求"""

    scene_ids: list[str] = Field(..., min_length=1)
