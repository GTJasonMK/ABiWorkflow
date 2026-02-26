from __future__ import annotations

import json
from collections.abc import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMAdapter, LLMResponse, Message
from app.models import Character, CompositionTask, Project, Scene
from app.services.script_parser import ScriptParserService


class FakeParserLLM(LLMAdapter):
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
            content = json.dumps({
                "global_style": {
                    "visual_style": "写实",
                    "color_tone": "冷色",
                    "era": "现代",
                    "mood": "紧张",
                },
                "characters": [
                    {
                        "name": "主角",
                        "appearance": "黑发短发",
                        "personality": "沉稳",
                        "costume": "黑色夹克",
                    }
                ],
                "scenes": [
                    {
                        "title": "新场景",
                        "narrative": "主角走进房间",
                        "setting": "室内 夜晚",
                        "mood": "压抑",
                        "character_names": ["主角"],
                        "character_actions": {"主角": "缓慢行走"},
                        "dialogue": "我们开始吧。",
                        "estimated_duration": 5.0,
                    }
                ],
            }, ensure_ascii=False)
            return LLMResponse(content=content)

        content = json.dumps({
            "scenes": [
                {
                    "sequence_order": 0,
                    "title": "新场景",
                    "video_prompt": "A man enters a dark room, cinematic, tracking shot",
                    "negative_prompt": "",
                    "camera_movement": "tracking",
                    "style_keywords": "cinematic, dark",
                    "duration_seconds": 5.0,
                    "transition_hint": "crossfade",
                }
            ]
        }, ensure_ascii=False)
        return LLMResponse(content=content)

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        if False:
            yield ""

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_parse_service_should_not_commit_implicitly(db_session: AsyncSession):
    project = Project(name="事务测试", status="parsing", script_text="一段测试剧本")
    db_session.add(project)
    await db_session.flush()

    old_scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="旧场景",
        video_prompt="old-prompt",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add(old_scene)
    await db_session.commit()

    # rollback() 会将所有 ORM 对象标记为 expired，
    # 之后同步访问 project.id 会触发延迟加载并在异步上下文中抛出 MissingGreenlet。
    # 因此必须在 rollback 之前缓存 project_id。
    project_id = project.id

    parser = ScriptParserService(FakeParserLLM())
    await parser.parse_script(project_id, project.script_text or "", db_session)

    # 不提交直接回滚，应恢复到解析前状态（旧场景仍在，未留下新角色/新场景）。
    await db_session.rollback()

    scenes = (await db_session.execute(
        select(Scene).where(Scene.project_id == project_id).order_by(Scene.sequence_order)
    )).scalars().all()
    characters = (await db_session.execute(
        select(Character).where(Character.project_id == project_id)
    )).scalars().all()
    restored_project = (await db_session.execute(
        select(Project).where(Project.id == project_id)
    )).scalar_one()

    assert len(scenes) == 1
    assert scenes[0].title == "旧场景"
    assert len(characters) == 0
    assert restored_project.status == "parsing"


@pytest.mark.asyncio
async def test_parse_service_should_mark_existing_compositions_stale(db_session: AsyncSession):
    project = Project(name="解析成片失效测试", status="parsing", script_text="一段测试剧本")
    db_session.add(project)
    await db_session.flush()

    old_composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/old.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(old_composition)
    await db_session.commit()

    parser = ScriptParserService(FakeParserLLM())
    await parser.parse_script(project.id, project.script_text or "", db_session)
    await db_session.commit()

    refreshed_composition = (await db_session.execute(
        select(CompositionTask).where(CompositionTask.id == old_composition.id)
    )).scalar_one()
    assert refreshed_composition.status == "stale"
