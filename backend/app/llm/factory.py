from __future__ import annotations

import logging
import re

from app.config import settings
from app.llm.base import LLMAdapter

logger = logging.getLogger(__name__)

_SCHEME_RE = re.compile(r"^(https?://)(.*)$", re.IGNORECASE)


def _fix_base_url(url: str) -> str:
    """去尾斜杠，修复路径中的双斜杠（协议部分保留）。"""
    if not url:
        return url
    fixed = url.rstrip("/")
    m = _SCHEME_RE.match(fixed)
    scheme, rest = (m.group(1), m.group(2)) if m else ("", fixed)
    if "//" in rest:
        rest = re.sub(r"/{2,}", "/", rest)
        fixed = f"{scheme}{rest}" if scheme else rest
        logger.warning("base_url 包含双斜杠，已自动修复: %s -> %s", url, fixed)
    return fixed


def _normalize_for_openai(base_url: str | None) -> str | None:
    """OpenAI SDK 的 base_url 需要以 /v1 结尾（SDK 在后面拼 /chat/completions）。

    用户可能填：
    - https://api.deepseek.com       → 补为 https://api.deepseek.com/v1
    - https://api.deepseek.com/v1    → 保持不变
    - https://api.openai.com/v1/     → 去尾斜杠
    """
    if not base_url:
        return base_url
    fixed = _fix_base_url(base_url)
    if not fixed.endswith("/v1"):
        fixed = f"{fixed}/v1"
    return fixed


def _normalize_for_anthropic(base_url: str | None) -> str | None:
    """Anthropic SDK 的 base_url 不能含 /v1（SDK 自己拼 /v1/messages）。

    用户可能填：
    - https://proxy.com              → 保持不变
    - https://proxy.com/v1           → 剥为 https://proxy.com
    - https://proxy.com/v1/messages  → 剥为 https://proxy.com
    """
    if not base_url:
        return base_url
    fixed = _fix_base_url(base_url)
    for suffix in ("/v1/messages", "/v1"):
        if fixed.endswith(suffix):
            fixed = fixed[: -len(suffix)]
            break
    return fixed or None


def create_llm_adapter() -> LLMAdapter:
    """根据模型名自动检测 API 格式并创建 LLM 适配器。

    模型名包含 'claude' → Anthropic Messages API，其余 → OpenAI Chat Completions API。
    """
    model = settings.llm_model
    if "claude" in model.lower():
        from app.llm.anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter(
            api_key=settings.llm_api_key,
            model=model,
            base_url=_normalize_for_anthropic(settings.llm_base_url),
        )
    from app.llm.openai_adapter import OpenAIAdapter
    return OpenAIAdapter(
        api_key=settings.llm_api_key,
        model=model,
        base_url=_normalize_for_openai(settings.llm_base_url),
    )
