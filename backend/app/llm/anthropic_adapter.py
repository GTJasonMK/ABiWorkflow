from __future__ import annotations

from collections.abc import AsyncIterator

from anthropic import AsyncAnthropic
from pydantic import BaseModel

from app.llm.base import LLMAdapter, LLMResponse, Message


class AnthropicAdapter(LLMAdapter):
    """Anthropic LLM 适配器"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(
        self,
        messages: list[Message],
        response_format: type[BaseModel] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """发送消息，通过提示词引导 JSON 输出"""
        # 分离 system 消息
        system_text = ""
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_text += m.content + "\n"
            else:
                api_messages.append({"role": m.role, "content": m.content})

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

        response = await self._client.messages.create(**kwargs)

        content = ""
        for block in response.content:
            if block.type == "text":
                content += block.text

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        return LLMResponse(content=content, usage=usage)

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        """流式返回文本"""
        system_text = ""
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_text += m.content + "\n"
            else:
                api_messages.append({"role": m.role, "content": m.content})

        kwargs: dict = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": 8192,
        }
        if system_text.strip():
            kwargs["system"] = system_text.strip()

        async with self._client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text

    async def close(self) -> None:
        await self._client.close()
