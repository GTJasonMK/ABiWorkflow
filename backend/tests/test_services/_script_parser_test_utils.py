from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from app.llm.base import LLMAdapter, LLMResponse, Message


def build_character(
    *,
    name: str = "主角",
    appearance: str = "黑发",
    personality: str = "沉稳",
    costume: str = "黑色夹克",
) -> dict[str, Any]:
    return {
        "name": name,
        "appearance": appearance,
        "personality": personality,
        "costume": costume,
    }


def build_narrative_scene(
    *,
    title: str,
    narrative: str,
    setting: str = "室内",
    mood: str = "压抑",
    character_names: list[str] | None = None,
    character_actions: dict[str, str] | None = None,
    dialogue: str | None = None,
    estimated_duration: float = 5.0,
) -> dict[str, Any]:
    return {
        "title": title,
        "narrative": narrative,
        "setting": setting,
        "mood": mood,
        "character_names": character_names or ["主角"],
        "character_actions": character_actions or {"主角": "走动"},
        "dialogue": dialogue,
        "estimated_duration": estimated_duration,
    }


def build_prompt_scene(
    *,
    sequence_order: int,
    title: str,
    video_prompt: str,
    negative_prompt: str = "",
    camera_movement: str = "tracking",
    style_keywords: str = "cinematic",
    duration_seconds: float = 5.0,
    transition_hint: str = "crossfade",
) -> dict[str, Any]:
    return {
        "sequence_order": sequence_order,
        "title": title,
        "video_prompt": video_prompt,
        "negative_prompt": negative_prompt,
        "camera_movement": camera_movement,
        "style_keywords": style_keywords,
        "duration_seconds": duration_seconds,
        "transition_hint": transition_hint,
    }


def build_narrative_payload(
    *,
    characters: list[dict[str, Any]] | None = None,
    scenes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "global_style": {
            "visual_style": "写实",
            "color_tone": "冷色",
            "era": "现代",
            "mood": "紧张",
        },
        "characters": characters or [build_character()],
        "scenes": scenes or [],
    }


def build_prompt_payload(*, scenes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"scenes": scenes}


class FakeTwoPhaseLLM(LLMAdapter):
    def __init__(self, *, first_payload: dict[str, Any], second_payload: dict[str, Any]):
        self._calls = 0
        self._first_payload = first_payload
        self._second_payload = second_payload

    async def complete(
        self,
        messages: list[Message],
        response_format=None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self._calls += 1
        payload = self._first_payload if self._calls == 1 else self._second_payload
        return LLMResponse(content=json.dumps(payload, ensure_ascii=False))

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        if False:
            yield ""

    async def close(self) -> None:
        return None


def build_fake_two_phase_llm(
    *,
    first_payload: dict[str, Any],
    second_payload: dict[str, Any],
) -> FakeTwoPhaseLLM:
    return FakeTwoPhaseLLM(first_payload=first_payload, second_payload=second_payload)
