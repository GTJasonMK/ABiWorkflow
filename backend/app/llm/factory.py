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
    elif settings.llm_provider == "deepseek":
        from app.llm.openai_adapter import OpenAIAdapter

        return OpenAIAdapter(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url,
        )
    elif settings.llm_provider == "ggk":
        from app.llm.openai_adapter import OpenAIAdapter

        if not settings.ggk_base_url.strip():
            raise ValueError("llm_provider=ggk 时必须配置 GGK_BASE_URL")
        if not settings.ggk_api_key.strip():
            raise ValueError("llm_provider=ggk 时必须配置 GGK_API_KEY")
        ggk_base_url = settings.ggk_base_url.strip().rstrip("/")
        if not ggk_base_url.endswith("/v1"):
            ggk_base_url = f"{ggk_base_url}/v1"

        return OpenAIAdapter(
            api_key=settings.ggk_api_key,
            model=settings.ggk_text_model,
            base_url=ggk_base_url,
        )
    raise ValueError(f"不支持的 LLM 提供者: {settings.llm_provider}")
