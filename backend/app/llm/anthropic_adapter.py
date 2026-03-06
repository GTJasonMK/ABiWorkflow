from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.llm.base import LLMAdapter, LLMResponse, Message

logger = logging.getLogger(__name__)


class AnthropicAdapter(LLMAdapter):
    """Anthropic LLM 适配器"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514", base_url: str | None = None):
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        # 同时带 Bearer 头，确保代理服务（OneAPI/NewAPI 等）能正确识别认证信息。
        # 官方 API 使用 x-api-key（SDK 内置），代理使用 Authorization: Bearer，两者互不干扰。
        kwargs["default_headers"] = {"Authorization": f"Bearer {api_key}"}
        self._client = AsyncAnthropic(**kwargs)
        self._model = model

    async def complete(
        self,
        messages: list[Message],
        response_format: type[BaseModel] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """发送消息，通过提示词引导 JSON 输出"""
        system_text, api_messages = self._split_messages(messages)

        if response_format is not None:
            system_text += "\n请严格按照 JSON 格式输出，不要包含任何其他文字说明。"

        kwargs: dict = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": 8192,
            "temperature": temperature,
        }
        if system_text.strip():
            kwargs["system"] = system_text.strip()

        logger.info("Anthropic 请求: model=%s, messages=%d条, temperature=%.1f",
                     self._model, len(api_messages), temperature)

        response = await self._client.messages.create(**kwargs)

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        logger.info("Anthropic 响应: %d 字符, tokens=%d+%d",
                     len(content), usage["input_tokens"], usage["output_tokens"])

        return LLMResponse(content=content, usage=usage)

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        """流式返回文本"""
        system_text, api_messages = self._split_messages(messages)

        kwargs: dict = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": 8192,
        }
        if system_text.strip():
            kwargs["system"] = system_text.strip()

        logger.info("Anthropic 流式请求: model=%s, messages=%d条", self._model, len(api_messages))

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def close(self) -> None:
        await self._client.close()

    @staticmethod
    def _split_messages(messages: list[Message]) -> tuple[str, list[dict]]:
        """分离 system 消息（Anthropic 要求 system 作为独立参数传递）。"""
        system_text = ""
        api_messages: list[dict] = []
        for m in messages:
            if m.role == "system":
                system_text += m.content + "\n"
            else:
                api_messages.append({"role": m.role, "content": m.content})
        return system_text, api_messages
