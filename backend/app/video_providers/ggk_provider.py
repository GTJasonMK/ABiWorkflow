from __future__ import annotations

import json
import logging
import re
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import resolve_runtime_path, settings
from app.video_providers.base import VideoGenerateRequest, VideoProvider, VideoTaskStatus

_ASPECT_RATIOS: tuple[str, ...] = ("2:3", "3:2", "1:1", "9:16", "16:9")
_RATIO_VALUES: dict[str, float] = {
    "2:3": 2 / 3,
    "3:2": 3 / 2,
    "1:1": 1.0,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
}
_RESOLUTIONS: set[str] = {"SD", "HD"}
_PRESETS: set[str] = {"fun", "normal", "spicy", "custom"}
_DEFAULT_DURATION_PROFILE: dict[str, Any] = {
    "min_seconds": 5,
    "max_seconds": 6,
    "allowed_seconds": [5, 6],
    "prompt_hint_template": "请将该镜头时长控制在约 {seconds} 秒，保证动作节奏完整。",
}

logger = logging.getLogger(__name__)


def _build_v1_base_url(raw_base: str) -> str:
    base = raw_base.strip().rstrip("/")
    if not base:
        raise ValueError("GGK_BASE_URL 未配置，无法使用 GGK 视频提供者")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _to_root_base(base_url: str) -> str:
    if base_url.endswith("/v1"):
        return base_url[:-3]
    return base_url


def _pick_aspect_ratio(width: int, height: int, configured: str) -> str:
    value = configured.strip()
    if value in _ASPECT_RATIOS:
        return value

    if width <= 0 or height <= 0:
        return "16:9"

    target = width / height
    return min(_RATIO_VALUES, key=lambda ratio: abs(_RATIO_VALUES[ratio] - target))


def _normalize_resolution(value: str) -> str:
    candidate = value.strip().upper()
    return candidate if candidate in _RESOLUTIONS else "SD"


def _normalize_preset(value: str) -> str:
    candidate = value.strip().lower()
    return candidate if candidate in _PRESETS else "normal"


def _to_int(value: Any, *, default: int, min_value: int = 1, max_value: int = 600) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        return default
    return min(max_value, max(min_value, parsed))


def _normalize_allowed_seconds(value: Any, *, min_seconds: int, max_seconds: int) -> list[int]:
    if not isinstance(value, list):
        return []

    items: set[int] = set()
    for raw in value:
        parsed = _to_int(raw, default=min_seconds, min_value=min_seconds, max_value=max_seconds)
        items.add(parsed)
    return sorted(items)


def _normalize_duration_profile(raw: Any) -> dict[str, Any]:
    profile = dict(_DEFAULT_DURATION_PROFILE)
    if not isinstance(raw, dict):
        return profile

    min_seconds = _to_int(raw.get("min_seconds"), default=profile["min_seconds"], min_value=1, max_value=600)
    max_seconds = _to_int(raw.get("max_seconds"), default=profile["max_seconds"], min_value=1, max_value=600)
    if max_seconds < min_seconds:
        max_seconds = min_seconds

    profile["min_seconds"] = min_seconds
    profile["max_seconds"] = max_seconds
    allowed = _normalize_allowed_seconds(raw.get("allowed_seconds"), min_seconds=min_seconds, max_seconds=max_seconds)
    if allowed:
        profile["allowed_seconds"] = allowed
    else:
        profile["allowed_seconds"] = []

    template = raw.get("prompt_hint_template")
    if isinstance(template, str):
        profile["prompt_hint_template"] = template.strip()

    return profile


def parse_model_duration_profiles(raw: str) -> dict[str, dict[str, Any]]:
    """解析模型级时长策略配置（JSON 字符串）。"""
    value = (raw or "").strip()
    if not value:
        return {}

    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON 解析失败: {exc.msg}") from exc

    if not isinstance(payload, dict):
        raise ValueError("配置必须是对象（key 为模型名）")

    result: dict[str, dict[str, Any]] = {}
    for model_name, model_profile in payload.items():
        model_key = str(model_name).strip()
        if not model_key:
            continue
        result[model_key] = _normalize_duration_profile(model_profile)
    return result


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    chunks.append(text)
            elif isinstance(item, str):
                chunks.append(item)
        return "\n".join(chunks)
    return str(content or "")


def _extract_video_url(content: str) -> str | None:
    if not content.strip():
        return None

    patterns = [
        r"""<source[^>]*?\bsrc=['"]([^'"]+)['"]""",
        r"""<video[^>]*?\bsrc=['"]([^'"]+)['"]""",
        r"""(https?://[^\s"'<>]+\.mp4(?:\?[^\s"'<>]+)?)""",
        r"""(/v1/files/video/[^\s"'<>]+)""",
    ]

    for pattern in patterns:
        match = re.search(pattern, content, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


class GgkVideoProvider(VideoProvider):
    """GGK 视频提供者，适配 /v1/chat/completions 的非流式视频生成。"""

    def __init__(self, output_dir: str = "./outputs/videos"):
        self._api_base = _build_v1_base_url(settings.ggk_base_url)
        self._root_base = _to_root_base(self._api_base)
        if not settings.ggk_api_key.strip():
            raise ValueError("GGK_API_KEY 未配置，无法使用 GGK 视频提供者")

        self._output_dir = resolve_runtime_path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._tasks: dict[str, VideoTaskStatus] = {}
        self._model_duration_profiles = parse_model_duration_profiles(settings.ggk_video_model_duration_profiles)
        self._duration_profile = self._resolve_duration_profile(settings.ggk_video_model)

    @property
    def name(self) -> str:
        return "ggk"

    @property
    def max_duration_seconds(self) -> float:
        profile_max = float(self._duration_profile["max_seconds"])
        return min(profile_max, max(1.0, settings.video_provider_max_duration_seconds))

    def _resolve_duration_profile(self, model_name: str) -> dict[str, Any]:
        custom = self._model_duration_profiles.get((model_name or "").strip())
        if not custom:
            return dict(_DEFAULT_DURATION_PROFILE)
        return dict(custom)

    def _resolve_video_length(self, requested_duration: float) -> int:
        profile = self._duration_profile
        min_seconds = int(profile["min_seconds"])
        max_seconds = int(profile["max_seconds"])
        allowed_seconds: list[int] = profile.get("allowed_seconds") or []

        requested = float(requested_duration or min_seconds)
        if allowed_seconds:
            nearest = min(allowed_seconds, key=lambda second: abs(second - requested))
            return _to_int(nearest, default=min_seconds, min_value=min_seconds, max_value=max_seconds)
        return _to_int(requested, default=min_seconds, min_value=min_seconds, max_value=max_seconds)

    def _append_duration_hint(self, prompt: str, seconds: int) -> str:
        template = str(self._duration_profile.get("prompt_hint_template") or "").strip()
        if not template:
            return prompt

        try:
            hint = template.format(seconds=seconds, model=settings.ggk_video_model)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GGK 时长提示模板渲染失败，将使用默认模板: %s", exc)
            hint = f"请将该镜头时长控制在约 {seconds} 秒。"

        hint = hint.strip()
        if not hint or hint in prompt:
            return prompt
        return f"{prompt}\n\n{hint}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.ggk_api_key}",
            "Content-Type": "application/json",
        }

    async def generate(self, request: VideoGenerateRequest) -> str:
        prompt = (request.prompt or "").strip()
        if request.negative_prompt:
            prompt += f"\n\n请避免出现：{request.negative_prompt.strip()}"
        if not prompt:
            raise ValueError("GGK 视频生成请求缺少 prompt")

        video_length = self._resolve_video_length(request.duration_seconds)
        prompt = self._append_duration_hint(prompt, video_length)
        aspect_ratio = _pick_aspect_ratio(request.width, request.height, settings.ggk_video_aspect_ratio)
        payload_messages: list[dict[str, Any]] = []
        if request.reference_image_url:
            payload_messages.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": request.reference_image_url}},
                ],
            })
        else:
            payload_messages.append({"role": "user", "content": prompt})

        payload = {
            "model": settings.ggk_video_model,
            "messages": payload_messages,
            "stream": False,
            "video_config": {
                "aspect_ratio": aspect_ratio,
                "video_length": video_length,
                "resolution": _normalize_resolution(settings.ggk_video_resolution),
                "preset": _normalize_preset(settings.ggk_video_preset),
            },
        }

        endpoint = f"{self._api_base}/chat/completions"
        logger.info("GGK 视频生成请求: model=%s, video_length=%d, aspect_ratio=%s, endpoint=%s",
                     settings.ggk_video_model, video_length, aspect_ratio, endpoint)
        logger.debug("GGK 视频请求 payload: %s", str(payload)[:500])
        async with httpx.AsyncClient(timeout=settings.ggk_request_timeout_seconds) as client:
            response = await client.post(endpoint, headers=self._headers(), json=payload)
            if response.status_code >= 400:
                error_body = response.text[:1000]
                logger.error("GGK 视频 API 返回错误 %d: %s", response.status_code, error_body)
                raise ValueError(
                    f"GGK 视频 API 返回 {response.status_code}: {error_body}"
                )
            body = response.json()

        task_id = str(body.get("id") or uuid.uuid4())
        content = _content_to_text(((body.get("choices") or [{}])[0].get("message") or {}).get("content"))
        video_url = _extract_video_url(content)
        if not video_url:
            self._tasks[task_id] = VideoTaskStatus(
                task_id=task_id,
                status="failed",
                progress_percent=100,
                error_message="GGK 返回内容中未找到视频地址",
            )
            snippet = content[:300].replace("\n", " ")
            raise ValueError(f"GGK 返回内容中未找到视频地址: {snippet}")

        if not video_url.startswith(("http://", "https://")):
            video_url = urljoin(f"{self._root_base.rstrip('/')}/", video_url.lstrip("/"))

        self._tasks[task_id] = VideoTaskStatus(
            task_id=task_id,
            status="completed",
            progress_percent=100,
            result_url=video_url,
        )
        return task_id

    async def poll_status(self, task_id: str) -> VideoTaskStatus:
        return self._tasks.get(
            task_id,
            VideoTaskStatus(task_id=task_id, status="failed", error_message="任务不存在"),
        )

    async def download(self, task_id: str, output_path: Path) -> Path:
        status = await self.poll_status(task_id)
        if status.status != "completed":
            raise RuntimeError(f"任务 {task_id} 尚未完成，当前状态: {status.status}")
        if not status.result_url:
            raise FileNotFoundError(f"任务 {task_id} 缺少结果 URL")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        if status.result_url.startswith(("http://", "https://")):
            async with httpx.AsyncClient(timeout=settings.ggk_request_timeout_seconds) as client:
                response = await client.get(status.result_url, follow_redirects=True)
                response.raise_for_status()
                output_path.write_bytes(response.content)
            return output_path

        source_path = Path(status.result_url)
        if not source_path.exists():
            raise FileNotFoundError(f"任务 {task_id} 结果文件不存在: {status.result_url}")
        if source_path.resolve() != output_path.resolve():
            output_path.write_bytes(source_path.read_bytes())
        return output_path
