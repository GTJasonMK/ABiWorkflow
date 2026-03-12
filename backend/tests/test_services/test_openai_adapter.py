from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.llm.base import Message
from app.llm.openai_adapter import OpenAIAdapter


class _FakeCompletions:
    def __init__(self, calls: list[dict]):
        self._calls = calls

    async def create(self, **kwargs):
        self._calls.append(kwargs)
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="ok"),
                    finish_reason="stop",
                )
            ],
            usage=None,
        )


class _FakeClient:
    def __init__(self, calls: list[dict], *args, **kwargs):
        self.chat = SimpleNamespace(completions=_FakeCompletions(calls))

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_openai_adapter_only_sends_ggk_supported_chat_fields(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []

    monkeypatch.setattr(
        "app.llm.openai_adapter.AsyncOpenAI",
        lambda *args, **kwargs: _FakeClient(calls, *args, **kwargs),
    )

    adapter = OpenAIAdapter(api_key="test-key", model="grok-4.1-fast", base_url="http://127.0.0.1:7321/v1")
    response = await adapter.complete(
        messages=[Message(role="user", content="hello")],
        response_format=Message,
        temperature=0.4,
    )

    assert response.content == "ok"
    assert calls == [
        {
            "model": "grok-4.1-fast",
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        }
    ]
