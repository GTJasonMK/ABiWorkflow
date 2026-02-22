from __future__ import annotations

from app.config import settings
from app.llm.base import LLMAdapter


def create_llm_adapter() -> LLMAdapter:
    """根据配置创建 LLM 适配器"""
    if settings.llm_provider == "openai":
        from app.llm.openai_adapter import OpenAIAdapter
        return OpenAIAdapter(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url,
        )
    elif settings.llm_provider == "anthropic":
        from app.llm.anthropic_adapter import AnthropicAdapter
        return AnthropicAdapter(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    raise ValueError(f"不支持的 LLM 提供者: {settings.llm_provider}")
