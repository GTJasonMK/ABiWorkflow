from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProviderConfig
from app.services.json_codec import from_json_text

_DEFAULT_STATUS_MAPPING: dict[str, str] = {
    "pending": "pending",
    "queued": "pending",
    "created": "pending",
    "running": "running",
    "processing": "running",
    "in_progress": "running",
    "completed": "completed",
    "success": "completed",
    "succeeded": "completed",
    "failed": "failed",
    "error": "failed",
    "cancelled": "cancelled",
    "canceled": "cancelled",
}


def _extract_path(data: Any, path: str, default: Any = None) -> Any:
    current = data
    for part in (path or "").split("."):
        token = part.strip()
        if not token:
            continue
        if isinstance(current, dict):
            if token not in current:
                return default
            current = current[token]
            continue
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError:
                return default
            if index < 0 or index >= len(current):
                return default
            current = current[index]
            continue
        return default
    return current


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
        r"""<source[^>]*?\bsrc=['\"]([^'\"]+)['\"]""",
        r"""<video[^>]*?\bsrc=['\"]([^'\"]+)['\"]""",
        r"""(https?://[^\s'\"<>]+\.mp4(?:\?[^\s'\"<>]+)?)""",
        r"""(/v1/files/video/[^\s'\"<>]+)""",
    ]
    for pattern in patterns:
        match = re.search(pattern, content, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _to_root_base(base_url: str) -> str:
    normalized = (base_url or "").strip()
    if normalized.endswith("/v1"):
        return normalized[:-3]
    return normalized


def _coerce_chat_completions_video_request(payload: dict[str, Any]) -> dict[str, Any]:
    """将简化的视频 payload 转成 /v1/chat/completions 的视频请求格式。

    约定：外部 UI/后端业务层传入的 video payload 形如：
    - prompt
    - negative_prompt
    - seconds
    - reference_image_url

    ProviderConfig.request_template_json 负责提供 model / video_config 默认值。
    """
    if "model" not in payload:
        raise ValueError("chat/completions 视频请求缺少 model（请在 ProviderConfig.request_template_json 中配置）")

    allowed_lengths: list[int] = []
    allowed_raw = payload.pop("_allowed_video_lengths", None)
    if isinstance(allowed_raw, list):
        for item in allowed_raw:
            try:
                allowed_lengths.append(int(item))
            except (TypeError, ValueError):
                continue
    allowed_lengths = sorted({value for value in allowed_lengths if value > 0})
    if not allowed_lengths:
        raise ValueError(
            "视频 Provider 未配置 _allowed_video_lengths，无法确定 video_config.video_length 的合法取值范围。"
            "请在 ProviderConfig.request_template_json 中显式配置，例如: "
            "{\"_allowed_video_lengths\":[6,10,15]}"
        )

    seconds_raw = payload.pop("seconds", None)
    # 注意：当前接入的 GGK(OpenAI 兼容) 视频接口在 messages 中携带 image_url 时，
    # 会直接返回空内容并结束，无法获得视频链接；并且本地 /media/... 路径会触发 400。
    # 因此这里将 reference_image_url 视为“仅供将来扩展”的输入，先从 payload 中移除，
    # 但不参与 messages 组装，确保视频生成稳定可用。
    payload.pop("reference_image_url", None)

    video_config = payload.get("video_config")
    if not isinstance(video_config, dict):
        video_config = {}
    else:
        video_config = dict(video_config)

    requested_length: int | None = None
    if seconds_raw is not None:
        try:
            requested_length = int(round(float(seconds_raw or 0.0)))
        except (TypeError, ValueError):
            requested_length = 0
    if requested_length is None and "video_length" in video_config:
        try:
            requested_length = int(round(float(video_config.get("video_length") or 0.0)))
        except (TypeError, ValueError):
            requested_length = 0

    if requested_length is None:
        requested_length = allowed_lengths[0]

    requested_length = max(1, requested_length)
    if requested_length not in allowed_lengths:
        allowed_text = ", ".join(str(value) for value in allowed_lengths)
        raise ValueError(f"video_config.video_length 必须为 {allowed_text} 秒之一（当前={requested_length}）")
    video_config["video_length"] = requested_length
    payload["video_config"] = video_config

    if "messages" not in payload:
        prompt = str(payload.pop("prompt", "") or "").strip()
        negative_prompt = str(payload.pop("negative_prompt", "") or "").strip()
        if negative_prompt:
            prompt = f"{prompt}\n\n请避免出现：{negative_prompt}"
        if not prompt:
            raise ValueError("视频生成缺少 prompt")
        payload["messages"] = [{"role": "user", "content": prompt}]
    else:
        # 兼容已提供 messages 的高级用法；此时 prompt/negative_prompt 仅可能是冗余字段。
        payload.pop("prompt", None)
        payload.pop("negative_prompt", None)

    payload.setdefault("stream", False)
    return payload


def _normalize_status(raw: Any, custom_mapping: dict[str, Any] | None = None) -> str:
    value = str(raw or "pending").strip().lower()
    if custom_mapping and value in custom_mapping:
        return str(custom_mapping[value]).strip().lower()
    return _DEFAULT_STATUS_MAPPING.get(value, value)


def _build_headers(config: ProviderConfig) -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if config.api_key:
        if config.auth_scheme.lower() == "bearer":
            headers[config.api_key_header] = f"Bearer {config.api_key}"
        elif config.auth_scheme.lower() == "plain":
            headers[config.api_key_header] = config.api_key
        else:
            headers[config.api_key_header] = f"{config.auth_scheme} {config.api_key}".strip()

    extras = from_json_text(config.extra_headers_json, {})
    if isinstance(extras, dict):
        for key, value in extras.items():
            if key:
                headers[str(key)] = str(value)
    return headers


def _join_url(base_url: str, path: str) -> str:
    return urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))


def _merge_request_payload(config: ProviderConfig, payload: dict[str, Any]) -> dict[str, Any]:
    template = from_json_text(config.request_template_json, {})
    if not isinstance(template, dict):
        template = {}
    merged: dict[str, Any] = {**template, **payload}
    if isinstance(template.get("video_config"), dict) and isinstance(payload.get("video_config"), dict):
        merged["video_config"] = {**template["video_config"], **payload["video_config"]}
    return merged


async def get_provider_config_or_404(db: AsyncSession, provider_key: str) -> ProviderConfig:
    config = (
        await db.execute(select(ProviderConfig).where(ProviderConfig.provider_key == provider_key))
    ).scalar_one_or_none()
    if config is None:
        raise ValueError(f"provider_key 不存在: {provider_key}")
    if not config.enabled:
        raise ValueError(f"provider_key 已禁用: {provider_key}")
    return config


async def submit_provider_task(
    db: AsyncSession,
    *,
    provider_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    config = await get_provider_config_or_404(db, provider_key)
    url = _join_url(config.base_url, config.submit_path)
    request_payload = _merge_request_payload(config, payload)

    is_chat_completions = (
        config.provider_type == "video"
        and "chat/completions" in (config.submit_path or "").strip().lower()
    )
    if is_chat_completions:
        request_payload = _coerce_chat_completions_video_request(request_payload)

    headers = _build_headers(config)
    stream_enabled = bool(request_payload.get("stream"))

    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        if is_chat_completions and stream_enabled:
            collected_chunks: list[str] = []
            stream_task_id: str | None = None

            async with client.stream("POST", url, headers=headers, json=request_payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    text = (line or "").strip()
                    if not text or not text.startswith("data:"):
                        continue
                    data_text = text[5:].strip()
                    if not data_text:
                        continue
                    if data_text == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_text)
                    except json.JSONDecodeError:
                        continue

                    if stream_task_id is None:
                        chunk_id = chunk.get("id")
                        if isinstance(chunk_id, str) and chunk_id.strip():
                            stream_task_id = chunk_id.strip()

                    delta_content = _extract_path(chunk, "choices.0.delta.content")
                    if isinstance(delta_content, str) and delta_content:
                        collected_chunks.append(delta_content)

            body = {
                "id": stream_task_id or "stream",
                "choices": [{"message": {"content": "".join(collected_chunks)}}],
            }
        else:
            response = await client.post(url, headers=headers, json=request_payload)
            response.raise_for_status()
            body = response.json()

    response_mapping = from_json_text(config.response_mapping_json, {}) or {}
    task_id_path = str(response_mapping.get("task_id_path") or "task_id")
    task_id = _extract_path(body, task_id_path)
    if not task_id:
        raise ValueError(f"提交成功但响应中缺少 task_id（路径: {task_id_path}）")

    status_path = str(response_mapping.get("status_path") or "").strip()
    progress_path = str(response_mapping.get("progress_path") or "").strip()
    result_url_path = str(response_mapping.get("result_url_path") or "").strip()
    error_path = str(response_mapping.get("error_path") or "").strip()
    status_mapping = from_json_text(config.status_mapping_json, {}) or {}

    raw_status = _extract_path(body, status_path) if status_path else None
    status = (
        _normalize_status(raw_status, status_mapping if isinstance(status_mapping, dict) else None)
        if raw_status is not None
        else None
    )
    raw_progress = _extract_path(body, progress_path) if progress_path else None
    raw_result_url = _extract_path(body, result_url_path) if result_url_path else None
    raw_error_message = _extract_path(body, error_path) if error_path else None

    if raw_result_url is None and is_chat_completions:
        content = _extract_path(body, "choices.0.message.content")
        text = _content_to_text(content)
        extracted = _extract_video_url(text)
        if extracted and not str(extracted).startswith(("http://", "https://")):
            extracted = urljoin(f"{_to_root_base(config.base_url).rstrip('/')}/", str(extracted).lstrip("/"))
        raw_result_url = extracted
        if raw_error_message is None and raw_result_url is None:
            snippet = text[:200].replace("\n", " ").strip()
            raw_error_message = (
                f"视频 Provider 返回内容中未找到视频地址: {snippet}"
                if snippet
                else "视频 Provider 返回内容中未找到视频地址"
            )

    progress_percent: float | None = None
    if raw_progress is not None:
        try:
            progress_percent = float(raw_progress or 0.0)
        except (TypeError, ValueError):
            progress_percent = 0.0
        if progress_percent is not None and 0.0 < progress_percent <= 1.0 and status in {"running", "completed"}:
            progress_percent *= 100.0
        if progress_percent is not None:
            progress_percent = max(0.0, min(100.0, progress_percent))

    if status is None and raw_result_url:
        status = "completed"
    if status == "completed" and progress_percent is None:
        progress_percent = 100.0

    return {
        "provider_key": provider_key,
        "task_id": str(task_id),
        "status": status,
        "progress_percent": progress_percent,
        "result_url": str(raw_result_url).strip() if raw_result_url else None,
        "error_message": str(raw_error_message).strip() if raw_error_message else None,
        "raw": body,
    }


async def query_provider_task_status(
    db: AsyncSession,
    *,
    provider_key: str,
    task_id: str,
) -> dict[str, Any]:
    config = await get_provider_config_or_404(db, provider_key)
    url = _join_url(config.base_url, config.status_path.format(task_id=task_id))

    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url, headers=_build_headers(config))
        response.raise_for_status()
        body = response.json()

    response_mapping = from_json_text(config.response_mapping_json, {}) or {}
    status_path = str(response_mapping.get("status_path") or "status")
    progress_path = str(response_mapping.get("progress_path") or "progress_percent")
    result_url_path = str(response_mapping.get("result_url_path") or "result_url")
    error_path = str(response_mapping.get("error_path") or "error_message")
    task_id_path = str(response_mapping.get("task_id_path") or "task_id")
    status_mapping = from_json_text(config.status_mapping_json, {}) or {}

    raw_status = _extract_path(body, status_path, "pending")
    status = _normalize_status(raw_status, status_mapping if isinstance(status_mapping, dict) else None)
    progress = _extract_path(body, progress_path, 0.0)
    result_url = _extract_path(body, result_url_path)
    error_message = _extract_path(body, error_path)
    remote_task_id = _extract_path(body, task_id_path, task_id)

    try:
        progress_percent = float(progress or 0.0)
    except (TypeError, ValueError):
        progress_percent = 0.0
    if 0.0 < progress_percent <= 1.0 and status in {"running", "completed"}:
        progress_percent *= 100.0

    return {
        "provider_key": provider_key,
        "task_id": str(remote_task_id or task_id),
        "status": status,
        "progress_percent": max(0.0, min(100.0, progress_percent)),
        "result_url": str(result_url) if result_url else None,
        "error_message": str(error_message) if error_message else None,
        "raw": body,
    }


async def fetch_provider_task_result(
    db: AsyncSession,
    *,
    provider_key: str,
    task_id: str,
) -> dict[str, Any]:
    config = await get_provider_config_or_404(db, provider_key)
    if not config.result_path.strip():
        return await query_provider_task_status(db, provider_key=provider_key, task_id=task_id)

    url = _join_url(config.base_url, config.result_path.format(task_id=task_id))
    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.get(url, headers=_build_headers(config))
        response.raise_for_status()
        body = response.json()
    return {
        "provider_key": provider_key,
        "task_id": task_id,
        "raw": body,
    }


async def test_provider_connectivity(db: AsyncSession, provider_key: str) -> dict[str, Any]:
    config = await get_provider_config_or_404(db, provider_key)
    url = _join_url(config.base_url, config.submit_path)
    async with httpx.AsyncClient(timeout=min(config.timeout_seconds, 10.0)) as client:
        response = await client.options(url, headers=_build_headers(config))
    return {
        "provider_key": provider_key,
        "url": url,
        "status_code": response.status_code,
        "ok": response.status_code < 500,
    }
