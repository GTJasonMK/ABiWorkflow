"""角色立绘生成服务。

通过 OpenAI 兼容的 /v1/images/generations API 调用生图模型，
为角色生成立绘并下载到本地。
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from app.config import resolve_runtime_path, settings

logger = logging.getLogger(__name__)


def _build_v1_base_url(raw_base: str) -> str:
    """确保 base_url 以 /v1 结尾。"""
    base = raw_base.strip().rstrip("/")
    if not base:
        raise ValueError("PORTRAIT_API_BASE_URL 未配置，无法生成立绘")
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _build_portrait_prompt(
    name: str,
    appearance: str | None,
    costume: str | None,
    personality: str | None,
) -> str:
    """根据角色档案构造立绘生成提示词。"""
    parts = [
        "Character portrait illustration for animation and video production.",
        f"Character name: {name}.",
    ]
    if appearance:
        parts.append(f"Appearance: {appearance}.")
    if costume:
        parts.append(f"Costume and outfit: {costume}.")
    if personality:
        parts.append(f"Personality vibe: {personality}.")
    parts.append(
        "Style: Semi-realistic character design, upper body portrait, "
        "clean solid color background, high detail, "
        "suitable as a visual reference sheet for consistent video generation."
    )
    return "\n".join(parts)


def _extract_image_from_response(body: dict) -> tuple[str | None, bytes | None]:
    """从 /v1/images/generations 响应中提取图片。

    响应格式：{"data": [{"url": "...", "revised_prompt": "..."}, ...]}
    或 b64_json 模式：{"data": [{"b64_json": "...", "revised_prompt": "..."}, ...]}

    返回 (url_or_none, raw_bytes_or_none)。
    """
    data_list = body.get("data")
    if not isinstance(data_list, list) or not data_list:
        return (None, None)

    for item in data_list:
        if not isinstance(item, dict):
            continue

        # URL 模式
        url = (item.get("url") or "").strip()
        if url and url.startswith(("http://", "https://")):
            return (url, None)

        # base64 模式
        b64 = (item.get("b64_json") or "").strip()
        if b64:
            try:
                return (None, base64.b64decode(b64))
            except Exception:
                pass

    return (None, None)


async def generate_portrait(
    character_id: str,
    name: str,
    appearance: str | None = None,
    costume: str | None = None,
    personality: str | None = None,
) -> str:
    """为角色生成立绘，返回可访问的本地 URL 路径（/media/portraits/...）。

    Raises:
        ValueError: 配置缺失或生图 API 返回中未找到图片。
    """
    prompt = _build_portrait_prompt(name, appearance, costume, personality)
    return await generate_image_from_prompt(character_id, prompt)


def _sanitize_output_subdir(subdir: str | None) -> Path:
    """清理并限制输出子目录，避免路径穿越。"""
    raw = (subdir or "").strip().replace("\\", "/").strip("/")
    if not raw:
        return Path(".")
    parts = [part for part in raw.split("/") if part and part not in {".", ".."}]
    return Path(*parts) if parts else Path(".")


async def generate_image_from_prompt(
    asset_id: str,
    prompt: str,
    *,
    output_subdir: str | None = None,
) -> str:
    """按提示词生成图片并落盘，返回可访问的媒体 URL（/media/portraits/...）。"""
    prompt_text = (prompt or "").strip()
    if not prompt_text:
        raise ValueError("提示词为空，无法生成图片")

    api_base = _build_v1_base_url(settings.portrait_api_base_url)
    if not settings.portrait_api_key.strip():
        raise ValueError("PORTRAIT_API_KEY 未配置，无法生成图片")

    # xAI /v1/images/generations 端点请求格式
    payload = {
        "model": settings.portrait_image_model,
        "prompt": prompt_text,
        "n": 1,
        "response_format": "url",
    }

    headers = {
        "Authorization": f"Bearer {settings.portrait_api_key}",
        "Content-Type": "application/json",
    }

    endpoint = f"{api_base}/images/generations"
    timeout = settings.portrait_request_timeout_seconds
    logger.info(
        "开始生成图片: asset_id=%s, model=%s, endpoint=%s, subdir=%s",
        asset_id,
        settings.portrait_image_model,
        endpoint,
        output_subdir or ".",
    )
    logger.debug("生图提示词: %s", prompt_text)

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        if response.status_code >= 400:
            error_body = response.text[:500]
            logger.error("生图 API 返回错误 %d: %s", response.status_code, error_body)
            raise ValueError(
                f"生图 API 返回 {response.status_code}: {error_body}"
            )
        body = response.json()

    logger.debug("生图 API 原始响应（前 800 字符）: %s", str(body)[:800])

    # 从响应中提取图片
    image_url, image_bytes = _extract_image_from_response(body)

    if not image_url and not image_bytes:
        logger.error("生图 API 返回中未找到图片。完整响应: %s", str(body)[:2000])
        raise ValueError(f"生图 API 返回中未找到图片数据: {str(body)[:300]}")

    # 准备本地存储
    output_root = resolve_runtime_path(settings.portrait_output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    safe_subdir = _sanitize_output_subdir(output_subdir)
    output_dir = output_root if str(safe_subdir) == "." else (output_root / safe_subdir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if image_bytes:
        # base64 内嵌图片 → 直接写入文件
        ext = _guess_extension_from_bytes(image_bytes)
        local_filename = f"{asset_id}{ext}"
        local_path = output_dir / local_filename
        local_path.write_bytes(image_bytes)
        logger.info(
            "图片已生成（base64）: asset_id=%s, path=%s, size=%d bytes",
            asset_id,
            local_path,
            len(image_bytes),
        )
    else:
        # URL → 下载到本地
        assert image_url is not None
        ext = _guess_extension(image_url)
        local_filename = f"{asset_id}{ext}"
        local_path = output_dir / local_filename

        logger.info("下载图片: %s → %s", image_url, local_path)
        async with httpx.AsyncClient(timeout=timeout) as client:
            img_response = await client.get(image_url, follow_redirects=True)
            img_response.raise_for_status()
            local_path.write_bytes(img_response.content)
        logger.info(
            "图片已生成: asset_id=%s, path=%s, size=%d bytes",
            asset_id,
            local_path,
            local_path.stat().st_size,
        )

    media_rel_path = local_path.relative_to(output_root).as_posix()
    return f"/media/portraits/{media_rel_path}"


def _guess_extension(url: str) -> str:
    """从 URL 中推断图片扩展名。"""
    path = url.split("?")[0].split("#")[0]
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if path.lower().endswith(ext):
            return ext
    # xAI 默认生成 JPG 格式
    return ".jpg"


def _guess_extension_from_bytes(data: bytes) -> str:
    """根据文件头魔术字节推断图片格式。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:2] == b"\xff\xd8":
        return ".jpg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    return ".jpg"
