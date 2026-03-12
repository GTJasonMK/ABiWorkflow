from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import ProviderConfig
from app.services.json_codec import to_json_text

logger = logging.getLogger(__name__)


async def ensure_default_provider_configs(db: AsyncSession) -> None:
    """确保内置的 Provider 配置存在（仅在缺失时创建）。

    目标：
    - 降低首次启动/本地开发的配置成本。
    - 不覆盖用户自定义的 provider_key 配置。
    - 对于内置默认 provider_key：缺失则创建，存在但不符合预期则纠正。
    """
    await _ensure_default_video_ggk_provider(db)


async def _ensure_default_video_ggk_provider(db: AsyncSession) -> None:
    provider_key = "video.ggk"
    base_url = (settings.ggk_base_url or "").strip()
    api_key = (settings.ggk_api_key or "").strip()

    if not base_url or not api_key:
        return

    if base_url.endswith("/"):
        logger.warning("GGK_BASE_URL 不能以 / 结尾，跳过默认 Provider 初始化: %s", base_url)
        return
    if not base_url.endswith("/v1"):
        logger.warning("GGK_BASE_URL 必须以 /v1 结尾，跳过默认 Provider 初始化: %s", base_url)
        return

    existing = (await db.execute(
        select(ProviderConfig).where(ProviderConfig.provider_key == provider_key)
    )).scalar_one_or_none()

    # 约定：settings.ggk_base_url 必须以 /v1 结尾（由 Settings 校验保证）
    # 这样 ProviderConfig.base_url 也直接使用 .../v1，并将 submit_path 设为 /chat/completions。
    target_submit_path = "/chat/completions"
    target_status_path = "/chat/completions"

    resolution_setting = (settings.ggk_video_resolution or "").strip()
    if resolution_setting.lower() in {"480p", "720p"}:
        resolution_name = resolution_setting.lower()
    elif resolution_setting.strip().upper() == "HD":
        resolution_name = "720p"
    else:
        resolution_name = "480p"

    preset = (settings.ggk_video_preset or "").strip().lower()
    if preset not in {"fun", "normal", "spicy"}:
        preset = "normal"

    target_request_template = {
        "model": settings.ggk_video_model,
        "stream": True,
        "_allowed_video_lengths": [6, 10, 15],
        "video_config": {
            "aspect_ratio": settings.ggk_video_aspect_ratio,
            "resolution_name": resolution_name,
            "preset": preset,
        },
    }
    target_response_mapping = {
        # /v1/chat/completions 响应结构（视频 URL 在 message.content 内，需要后端提取）
        "task_id_path": "id",
    }

    if existing is not None:
        # 仅当该配置看起来就是“默认自动创建的 GGK 配置”时才进行纠正，
        # 避免覆盖用户手动配置的 provider_key。
        managed_default = (
            existing.provider_type == "video"
            and existing.name == "GGK 视频生成"
        )
        if not managed_default:
            return

        changed = False
        if existing.base_url != base_url:
            existing.base_url = base_url
            changed = True
        if (existing.api_key or "").strip() != api_key:
            existing.api_key = api_key
            changed = True
        if existing.submit_path != target_submit_path:
            existing.submit_path = target_submit_path
            changed = True
        if existing.status_path != target_status_path:
            existing.status_path = target_status_path
            changed = True
        if existing.request_template_json != to_json_text(target_request_template):
            existing.request_template_json = to_json_text(target_request_template)
            changed = True
        if existing.response_mapping_json != to_json_text(target_response_mapping):
            existing.response_mapping_json = to_json_text(target_response_mapping)
            changed = True

        if not changed:
            return

        try:
            await db.commit()
        except Exception:  # noqa: BLE001
            await db.rollback()
            raise
        logger.info("已自动修正默认 Provider 配置: %s", provider_key)
        return

    entity = ProviderConfig(
        provider_key=provider_key,
        provider_type="video",
        name="GGK 视频生成",
        base_url=base_url,
        submit_path=target_submit_path,
        status_path=target_status_path,
        result_path="",
        auth_scheme="bearer",
        api_key=api_key,
        api_key_header="Authorization",
        extra_headers_json=to_json_text({}),
        request_template_json=to_json_text(target_request_template),
        response_mapping_json=to_json_text(target_response_mapping),
        status_mapping_json=to_json_text({}),
        timeout_seconds=float(settings.ggk_request_timeout_seconds or 300.0),
        enabled=True,
    )
    db.add(entity)
    try:
        await db.commit()
    except IntegrityError:
        # 并发启动时可能出现抢占写入；此时忽略即可。
        await db.rollback()
        return
    except Exception:  # noqa: BLE001
        await db.rollback()
        raise
    logger.info("已自动创建默认 Provider 配置: %s", provider_key)
