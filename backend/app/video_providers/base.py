from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel


class VideoGenerateRequest(BaseModel):
    """视频生成请求"""

    prompt: str
    duration_seconds: float = 5.0
    width: int = 1280
    height: int = 720
    reference_image_url: str | None = None
    negative_prompt: str | None = None
    seed: int | None = None


class VideoTaskStatus(BaseModel):
    """视频生成任务状态"""

    task_id: str
    status: str  # pending | processing | completed | failed
    progress_percent: float = 0.0
    result_url: str | None = None
    error_message: str | None = None


class VideoProvider(ABC):
    """视频生成适配器抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """提供者名称"""

    @property
    @abstractmethod
    def max_duration_seconds(self) -> float:
        """单次生成最大时长"""

    @abstractmethod
    async def generate(self, request: VideoGenerateRequest) -> str:
        """提交生成任务，返回 task_id"""

    @abstractmethod
    async def poll_status(self, task_id: str) -> VideoTaskStatus:
        """查询任务状态"""

    @abstractmethod
    async def download(self, task_id: str, output_path: Path) -> Path:
        """下载生成的视频文件"""
