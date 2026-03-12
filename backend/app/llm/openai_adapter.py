from __future__ import annotations

import logging
from collections.abc import AsyncIterator

from openai import AsyncOpenAI
from pydantic import BaseModel

from app.llm.base import LLMAdapter, LLMResponse, Message

logger = logging.getLogger(__name__)


class OpenAIAdapter(LLMAdapter):
    """OpenAI Chat Completions 适配器。"""

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str | None = None):
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    async def complete(
        self,
        messages: list[Message],
        response_format: type[BaseModel] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """发送消息并获取完整回复。"""
        api_messages = [{"role": m.role, "content": m.content} for m in messages]

        kwargs: dict = {
            "model": self._model,
            "messages": api_messages,
            "stream": False,
        }

        logger.info("LLM 请求: model=%s, messages=%d条", self._model, len(api_messages))
        logger.debug(
            "LLM 请求附加参数已在传输层忽略: response_format=%s, temperature=%s",
            response_format is not None,
            temperature,
        )
        response = await self._client.chat.completions.create(**kwargs)

        if isinstance(response, str):
            logger.error("LLM 返回了原始字符串而非 ChatCompletion 对象: %s", response[:500])
            raise TypeError(
                f"LLM API 返回格式异常：期望 ChatCompletion 对象，实际收到 str。"
                f"请检查 base_url 配置是否正确。响应前 200 字符: {response[:200]}"
            )

        choice = response.choices[0]
        content = choice.message.content or ""
        logger.info("LLM 响应: %d 字符, finish_reason=%s", len(content), choice.finish_reason)
        logger.debug("LLM 响应内容: %s", content[:300])

        usage = None
        if response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            logger.info("Token 用量: prompt=%d, completion=%d, total=%d",
                         usage["prompt_tokens"], usage["completion_tokens"], usage["total_tokens"])

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
