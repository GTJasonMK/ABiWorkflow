from __future__ import annotations

from collections.abc import AsyncIterator

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.llm.base import LLMAdapter, LLMResponse, Message


class OpenAIAdapter(LLMAdapter):
    """OpenAI LLM 适配器"""

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def complete(
        self,
        messages: list[Message],
        response_format: type[BaseModel] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """发送消息，支持结构化 JSON 输出"""
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs: dict = {
            "model": self._model,
            "messages": api_messages,
            "temperature": temperature,
        }

        if response_format is not None:
            # 使用 JSON mode 并在系统提示中要求 JSON 格式
            kwargs["response_format"] = {"type": "json_object"}

        response = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        content = choice.message.content or ""

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        return LLMResponse(content=content, usage=usage)

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        """流式返回文本"""
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=api_messages,
            stream=True,
        )
        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def close(self) -> None:
        await self._client.close()
