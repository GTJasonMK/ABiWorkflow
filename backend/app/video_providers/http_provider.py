from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.config import resolve_runtime_path, settings
from app.video_providers.base import VideoGenerateRequest, VideoProvider, VideoTaskStatus

_STATUS_MAPPING: dict[str, str] = {
    "pending": "pending",
    "queued": "pending",
    "created": "pending",
    "processing": "processing",
    "in_progress": "processing",
    "running": "processing",
    "completed": "completed",
    "complete": "completed",
    "success": "completed",
    "succeeded": "completed",
    "done": "completed",
    "finished": "completed",
    "failed": "failed",
    "error": "failed",
    "errored": "failed",
    "cancelled": "failed",
    "canceled": "failed",
}


def _extract_by_path(data: dict[str, Any], path: str, default: Any = None) -> Any:
    """按点路径读取 JSON 字段，例如 'data.task.id'。"""
    current: Any = data
    for part in path.split("."):
        if not part:
            continue
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def _normalize_status(raw: Any) -> str:
    value = str(raw or "pending").strip().lower()
    return _STATUS_MAPPING.get(value, value)


def _normalize_progress(raw: Any, status: str) -> float:
    try:
        value = float(raw or 0.0)
    except (TypeError, ValueError):
        return 0.0

    # 某些第三方接口返回 0~1 浮点进度。
    if 0.0 < value < 1.0 or (value == 1.0 and status == "completed"):
        value *= 100.0
    return max(0.0, min(100.0, value))


class HttpVideoProvider(VideoProvider):
    """通用 HTTP 视频提供者，适配支持“提交任务 + 轮询状态”的外部服务。"""

    def __init__(self, output_dir: str = "./outputs/videos"):
        if not settings.video_http_base_url:
            raise ValueError("video_http_base_url 未配置，无法使用 HTTP 视频提供者")

        self._output_dir = resolve_runtime_path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "http"

    @property
    def max_duration_seconds(self) -> float:
        return settings.video_provider_max_duration_seconds

    def _build_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if settings.video_http_api_key:
            headers["Authorization"] = f"Bearer {settings.video_http_api_key}"
        return headers

    @staticmethod
    def _should_forward_auth(result_url: str) -> bool:
        """仅在下载地址与 provider base URL 同源时转发鉴权头，避免密钥泄露到第三方域名。"""
        if not settings.video_http_api_key:
            return False

        result_netloc = urlsplit(result_url).netloc.lower()
        base_netloc = urlsplit(settings.video_http_base_url).netloc.lower()
        return bool(result_netloc and base_netloc and result_netloc == base_netloc)

    async def generate(self, request: VideoGenerateRequest) -> str:
        payload = {
            "prompt": request.prompt,
            "duration_seconds": request.duration_seconds,
            "width": request.width,
            "height": request.height,
            "reference_image_url": request.reference_image_url,
            "negative_prompt": request.negative_prompt,
            "seed": request.seed,
        }
        url = urljoin(settings.video_http_base_url.rstrip("/") + "/", settings.video_http_generate_path.lstrip("/"))

        async with httpx.AsyncClient(timeout=settings.video_http_request_timeout_seconds) as client:
            response = await client.post(url, headers=self._build_headers(), json=payload)
            response.raise_for_status()
            body = response.json()

        task_id = _extract_by_path(body, settings.video_http_task_id_path)
        if not task_id:
            raise ValueError(f"生成接口未返回 task_id（字段路径: {settings.video_http_task_id_path}）")
        return str(task_id)

    async def poll_status(self, task_id: str) -> VideoTaskStatus:
        url = urljoin(
            settings.video_http_base_url.rstrip("/") + "/",
            settings.video_http_status_path.format(task_id=task_id).lstrip("/"),
        )

        async with httpx.AsyncClient(timeout=settings.video_http_request_timeout_seconds) as client:
            response = await client.get(url, headers=self._build_headers())
            response.raise_for_status()
            body = response.json()

        status = _normalize_status(_extract_by_path(body, settings.video_http_status_value_path, "pending"))
        progress_raw = _extract_by_path(body, settings.video_http_progress_path, 0.0)
        result_url = _extract_by_path(body, settings.video_http_result_url_path)
        error_message = _extract_by_path(body, settings.video_http_error_path)

        progress = _normalize_progress(progress_raw, status)

        return VideoTaskStatus(
            task_id=task_id,
            status=status,
            progress_percent=progress,
            result_url=str(result_url) if result_url else None,
            error_message=str(error_message) if error_message else None,
        )

    async def download(self, task_id: str, output_path: Path) -> Path:
        status = await self.poll_status(task_id)
        if status.status.lower() != "completed":
            raise RuntimeError(f"任务 {task_id} 尚未完成，当前状态: {status.status}")
        if not status.result_url:
            raise FileNotFoundError(f"任务 {task_id} 缺少结果 URL")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        source = status.result_url

        if source.startswith("http://") or source.startswith("https://"):
            async with httpx.AsyncClient(timeout=settings.video_http_request_timeout_seconds) as client:
                headers = self._build_headers() if self._should_forward_auth(source) else None
                response = await client.get(source, headers=headers, follow_redirects=True)
                response.raise_for_status()
                output_path.write_bytes(response.content)
            return output_path

        source_path = Path(source)
        if not source_path.exists():
            raise FileNotFoundError(f"任务 {task_id} 结果文件不存在: {source}")

        if source_path.resolve() != output_path.resolve():
            shutil.copy2(source_path, output_path)
        return output_path
