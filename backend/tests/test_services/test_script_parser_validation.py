from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMAdapter, LLMResponse, Message
from app.models import Character, Project, Scene, SceneCharacter
from app.services.script_parser import ScriptParserService, _extract_json


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


class FakeEmptyPromptsLLM(LLMAdapter):
    """第二阶段返回空场景，验证服务会显式失败而非写入空数据。"""

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
                    }
                ],
            }, ensure_ascii=False))

        return LLMResponse(content=json.dumps({"scenes": []}, ensure_ascii=False))

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        if False:
            yield ""

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_parse_service_should_fail_when_prompt_generation_returns_empty_scenes(db_session: AsyncSession):
    parser = ScriptParserService(FakeEmptyPromptsLLM())

    with pytest.raises(RuntimeError, match="未生成任何场景提示词"):
        await parser.parse_script("project-id", "测试剧本", db_session)


class FakeWhitespaceCharacterLLM(LLMAdapter):
    """角色命名含前后空白，验证关联写入是否稳定。"""

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
                        "personality": "冷静",
                        "costume": "黑色风衣",
                    }
                ],
                "scenes": [
                    {
                        "title": "场景一",
                        "narrative": "主角走入房间",
                        "setting": "室内",
                        "mood": "压抑",
                        "character_names": [" 主角 "],
                        "character_actions": {" 主角 ": "推门进入"},
                        "dialogue": "到了。",
                        "estimated_duration": 5.0,
                    }
                ],
            }, ensure_ascii=False))

        return LLMResponse(content=json.dumps({
            "scenes": [
                {
                    "sequence_order": 0,
                    "title": "场景一",
                    "video_prompt": "cinematic indoor scene",
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
async def test_parse_service_should_link_character_even_when_scene_name_has_whitespace(db_session: AsyncSession):
    project = Project(name="角色映射测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    parser = ScriptParserService(FakeWhitespaceCharacterLLM())
    await parser.parse_script(project.id, "测试剧本", db_session)
    await db_session.commit()

    character = (await db_session.execute(
        select(Character).where(Character.project_id == project.id)
    )).scalar_one()
    scene = (await db_session.execute(
        select(Scene).where(Scene.project_id == project.id)
    )).scalar_one()
    links = (await db_session.execute(
        select(SceneCharacter).where(SceneCharacter.scene_id == scene.id)
    )).scalars().all()

    assert len(links) == 1
    assert links[0].character_id == character.id
    assert links[0].action == "推门进入"


class FakeDuplicateCharacterNamesLLM(LLMAdapter):
    """同一场景重复输出角色名，验证不会写入重复关联。"""

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
                        "personality": "冷静",
                        "costume": "黑色风衣",
                    }
                ],
                "scenes": [
                    {
                        "title": "场景一",
                        "narrative": "主角反复出现",
                        "setting": "室内",
                        "mood": "压抑",
                        "character_names": ["主角", "主角", " 主角 "],
                        "character_actions": {"主角": "看向门口"},
                        "dialogue": "重复但应去重。",
                        "estimated_duration": 5.0,
                    }
                ],
            }, ensure_ascii=False))

        return LLMResponse(content=json.dumps({
            "scenes": [
                {
                    "sequence_order": 0,
                    "title": "场景一",
                    "video_prompt": "cinematic indoor scene",
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
async def test_parse_service_should_deduplicate_scene_character_links(db_session: AsyncSession):
    project = Project(name="角色去重测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    parser = ScriptParserService(FakeDuplicateCharacterNamesLLM())
    await parser.parse_script(project.id, "测试剧本", db_session)
    await db_session.commit()

    scene = (await db_session.execute(
        select(Scene).where(Scene.project_id == project.id)
    )).scalar_one()
    links = (await db_session.execute(
        select(SceneCharacter).where(SceneCharacter.scene_id == scene.id)
    )).scalars().all()

    assert len(links) == 1


class FakeBlankSceneTitleLLM(LLMAdapter):
    """第二阶段返回空白场景标题，验证解析服务会自动兜底。"""

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
                        "personality": "冷静",
                        "costume": "黑色风衣",
                    }
                ],
                "scenes": [
                    {
                        "title": "叙事标题一",
                        "narrative": "主角进入房间",
                        "setting": "室内",
                        "mood": "压抑",
                        "character_names": ["主角"],
                        "character_actions": {"主角": "推门"},
                        "dialogue": "到了。",
                        "estimated_duration": 5.0,
                    }
                ],
            }, ensure_ascii=False))

        return LLMResponse(content=json.dumps({
            "scenes": [
                {
                    "sequence_order": 0,
                    "title": "   ",
                    "video_prompt": "cinematic indoor scene",
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
async def test_parse_service_should_fallback_scene_title_when_prompt_title_blank(db_session: AsyncSession):
    project = Project(name="标题兜底测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    parser = ScriptParserService(FakeBlankSceneTitleLLM())
    await parser.parse_script(project.id, "测试剧本", db_session)
    await db_session.commit()

    scene = (await db_session.execute(
        select(Scene).where(Scene.project_id == project.id)
    )).scalar_one()
    assert scene.title == "叙事标题一"


def test_extract_json_should_parse_embedded_object_text():
    payload = """
解析结果如下，请继续下一步：
{"foo": "bar", "count": 2}
以上为结构化内容。
"""
    parsed = _extract_json(payload)
    assert parsed["foo"] == "bar"
    assert parsed["count"] == 2


def test_extract_json_should_parse_fenced_json_with_prefix_suffix():
    payload = """
好的，返回如下：
```json
{"result": {"scene_count": 3}}
```
请查收。
"""
    parsed = _extract_json(payload)
    assert parsed["result"]["scene_count"] == 3
