from __future__ import annotations

import asyncio
import uuid
from pathlib import Path

from moviepy import ColorClip, CompositeVideoClip, TextClip

from app.video_providers.base import VideoGenerateRequest, VideoProvider, VideoTaskStatus


class MockVideoProvider(VideoProvider):
    """Mock 视频提供者：使用 moviepy 生成带文字的纯色测试视频"""

    def __init__(self, output_dir: str = "./outputs/videos"):
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, dict] = {}

    @property
    def name(self) -> str:
        return "mock"

    @property
    def max_duration_seconds(self) -> float:
        return 10.0

    async def generate(self, request: VideoGenerateRequest) -> str:
        """生成带提示词文字的测试视频"""
        task_id = str(uuid.uuid4())
        output_path = self._output_dir / f"{task_id}.mp4"

        self._tasks[task_id] = {"status": "processing", "output_path": str(output_path)}

        # 在线程中执行 moviepy 渲染（避免阻塞事件循环）
        await asyncio.to_thread(self._render_video, request, output_path)

        self._tasks[task_id]["status"] = "completed"
        return task_id

    async def poll_status(self, task_id: str) -> VideoTaskStatus:
        """查询任务状态"""
        task = self._tasks.get(task_id)
        if task is None:
            return VideoTaskStatus(task_id=task_id, status="failed", error_message="任务不存在")
        return VideoTaskStatus(
            task_id=task_id,
            status=task["status"],
            progress_percent=100.0 if task["status"] == "completed" else 50.0,
            result_url=task.get("output_path"),
        )

    async def download(self, task_id: str, output_path: Path) -> Path:
        """Mock 下载：直接返回本地路径"""
        task = self._tasks.get(task_id)
        if task and task.get("output_path"):
            source = Path(task["output_path"])
            if source != output_path:
                import shutil
                shutil.copy2(source, output_path)
            return output_path
        raise FileNotFoundError(f"任务 {task_id} 的视频文件不存在")

    def _render_video(self, request: VideoGenerateRequest, output_path: Path) -> None:
        """渲染测试视频（同步方法，在线程中执行）"""
        duration = min(request.duration_seconds, self.max_duration_seconds)
        width, height = request.width, request.height

        # 纯色背景
        bg = ColorClip(size=(width, height), color=(30, 30, 60), duration=duration)

        # 提示词文字（截断显示）
        prompt_text = request.prompt[:100] + "..." if len(request.prompt) > 100 else request.prompt

        try:
            txt = TextClip(
                text=prompt_text,
                font_size=24,
                color="white",
                size=(width - 40, None),
                method="caption",
                duration=duration,
            )
            txt = txt.with_position("center")
            video = CompositeVideoClip([bg, txt])
        except Exception:
            # TextClip 可能因字体问题失败，降级为纯色视频
            video = bg

        video.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio=False,
            logger=None,
        )
        video.close()
