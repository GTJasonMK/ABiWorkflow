from __future__ import annotations

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
        if not isinstance(current, dict) or token not in current:
            return default
        current = current[token]
    return current


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
    return {**template, **payload}


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

    async with httpx.AsyncClient(timeout=config.timeout_seconds) as client:
        response = await client.post(url, headers=_build_headers(config), json=request_payload)
        response.raise_for_status()
        body = response.json()

    response_mapping = from_json_text(config.response_mapping_json, {}) or {}
    task_id_path = str(response_mapping.get("task_id_path") or "task_id")
    task_id = _extract_path(body, task_id_path)
    if not task_id:
        raise ValueError(f"提交成功但响应中缺少 task_id（路径: {task_id_path}）")

    return {
        "provider_key": provider_key,
        "task_id": str(task_id),
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
