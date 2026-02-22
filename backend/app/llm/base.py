from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel


class Message(BaseModel):
    """LLM 对话消息"""

    role: str  # system | user | assistant
    content: str


class LLMResponse(BaseModel):
    """LLM 完整回复"""

    content: str
    usage: dict | None = None


class LLMAdapter(ABC):
    """LLM 适配器抽象基类"""

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        response_format: type[BaseModel] | None = None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        """发送消息并获取完整回复，可选结构化 JSON 输出"""

    @abstractmethod
    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        """流式返回文本"""

    @abstractmethod
    async def close(self) -> None:
        """释放资源"""
