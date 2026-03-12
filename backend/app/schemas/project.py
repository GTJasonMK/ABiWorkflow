from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.episode import EpisodeResponse


class WorkflowDefaultsPayload(BaseModel):
    """项目级默认工作流配置。"""

    video_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    tts_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    lipsync_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    provider_payload_defaults: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ProjectCreate(BaseModel):
    """创建项目请求"""

    name: str = Field(..., min_length=1, max_length=200)
    description: str | None = None
    workflow_defaults: WorkflowDefaultsPayload | None = None


class ProjectUpdate(BaseModel):
    """更新项目请求"""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    script_text: str | None = None
    workflow_defaults: WorkflowDefaultsPayload | None = None


class ProjectScriptWorkspaceEpisodePayload(BaseModel):
    id: str | None = None
    title: str | None = Field(default=None, max_length=200)
    summary: str | None = None
    script_text: str | None = None
    video_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    tts_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    lipsync_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    provider_payload_defaults: dict[str, dict[str, Any]] = Field(default_factory=dict)
    skipped_checks: list[str] = Field(default_factory=list)


class ProjectScriptWorkspaceUpdate(BaseModel):
    script_text: str = Field(min_length=1)
    workflow_defaults: WorkflowDefaultsPayload
    episodes: list[ProjectScriptWorkspaceEpisodePayload] = Field(min_length=1)


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
    workflow_defaults: WorkflowDefaultsPayload
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


class ProjectWorkspaceResourceSummary(BaseModel):
    character_entity_count: int = 0
    bound_character_entity_count: int = 0
    location_entity_count: int = 0
    bound_location_entity_count: int = 0
    voice_asset_count: int = 0
    panel_count: int = 0
    clip_count: int = 0
    ready_clip_count: int = 0
    failed_clip_count: int = 0
    composition_count: int = 0


class ProjectWorkspacePreview(BaseModel):
    id: str
    status: str
    duration_seconds: float = 0
    created_at: str | None = None
    updated_at: str | None = None


class ProjectWorkspaceResponse(BaseModel):
    project: ProjectResponse
    episodes: list[EpisodeResponse]
    resource_summary: ProjectWorkspaceResourceSummary
    latest_preview: ProjectWorkspacePreview | None = None
    recommended_episode_id: str | None = None
    recommended_step: str = "script"
