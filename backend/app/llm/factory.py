from __future__ import annotations

import logging

from app.config import settings
from app.llm.base import LLMAdapter

logger = logging.getLogger(__name__)


def _validate_base_url(*, provider: str, base_url: str | None) -> str | None:
    """严格校验 base_url，不做自动补全/兼容修复。"""
    if base_url is None:
        return None

    value = base_url.strip()
    if not value:
        return None

    if not (value.startswith("http://") or value.startswith("https://")):
        raise ValueError("llm_base_url 必须以 http:// 或 https:// 开头")

    if value.endswith("/"):
        raise ValueError("llm_base_url 不能以 / 结尾")

    if provider == "openai":
        if not value.endswith("/v1"):
            raise ValueError("openai provider 的 llm_base_url 必须以 /v1 结尾，例如 https://glk.jia4u.de/v1")
        return value

    if provider == "anthropic":
        if value.endswith("/v1") or "/v1/" in value:
            raise ValueError("anthropic provider 的 llm_base_url 不应包含 /v1（SDK 会自动拼接 /v1/messages）")
        return value

    raise ValueError(f"不支持的 llm_provider: {provider}")


def create_llm_adapter() -> LLMAdapter:
    """按 settings.llm_provider 创建 LLM 适配器（不做模型名猜测）。"""
    provider = settings.llm_provider
    model = settings.llm_model
    base_url = _validate_base_url(provider=provider, base_url=settings.llm_base_url)

    logger.info("创建 LLM 适配器: provider=%s, model=%s, base_url=%s", provider, model, base_url or "<default>")

    if provider == "anthropic":
        from app.llm.anthropic_adapter import AnthropicAdapter

        return AnthropicAdapter(
            api_key=settings.llm_api_key,
            model=model,
            base_url=base_url,
        )

    from app.llm.openai_adapter import OpenAIAdapter

    return OpenAIAdapter(
        api_key=settings.llm_api_key,
        model=model,
        base_url=base_url,
    )

