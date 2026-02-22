from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMAdapter, LLMResponse, Message
from app.services.script_parser import ScriptParserService


class FakeMismatchLLM(LLMAdapter):
    """返回场景数量不一致的假 LLM。"""

    def __init__(self):
        self._calls = 0

    async def complete(
        self,
        messages: list[Message],
        response_format=None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self._calls += 1
        if self._calls == 1:
            return LLMResponse(content=json.dumps({
                "global_style": {
                    "visual_style": "写实",
                    "color_tone": "冷色",
                    "era": "现代",
                    "mood": "紧张",
                },
                "characters": [
                    {
                        "name": "主角",
                        "appearance": "黑发",
                        "personality": "沉稳",
                        "costume": "黑色夹克",
                    }
                ],
                "scenes": [
                    {
                        "title": "场景一",
                        "narrative": "第一场",
                        "setting": "室内",
                        "mood": "压抑",
                        "character_names": ["主角"],
                        "character_actions": {"主角": "走动"},
                        "dialogue": "台词一",
                        "estimated_duration": 5.0,
                    },
                    {
                        "title": "场景二",
                        "narrative": "第二场",
                        "setting": "室外",
                        "mood": "紧张",
                        "character_names": ["主角"],
                        "character_actions": {"主角": "奔跑"},
                        "dialogue": "台词二",
                        "estimated_duration": 5.0,
                    },
                ],
            }, ensure_ascii=False))

        return LLMResponse(content=json.dumps({
            "scenes": [
                {
                    "sequence_order": 0,
                    "title": "场景一",
                    "video_prompt": "scene one prompt",
                    "negative_prompt": "",
                    "camera_movement": "tracking",
                    "style_keywords": "cinematic",
                    "duration_seconds": 5.0,
                    "transition_hint": "crossfade",
                }
            ]
        }, ensure_ascii=False))

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        if False:
            yield ""

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_parse_service_should_fail_when_scene_counts_mismatch(db_session: AsyncSession):
    parser = ScriptParserService(FakeMismatchLLM())

    with pytest.raises(RuntimeError, match="不一致"):
        await parser.parse_script("project-id", "测试剧本", db_session)

