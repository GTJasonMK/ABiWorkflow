from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Character, Episode, Panel, Project
from app.services.episode_parse_pipeline import parse_project_from_episodes
from app.services.llm_json import extract_json_object
from tests.test_services._script_parser_test_utils import (
    build_character,
    build_fake_two_phase_llm,
    build_narrative_payload,
    build_narrative_scene,
    build_prompt_payload,
    build_prompt_scene,
)


@pytest.mark.asyncio
async def test_parse_service_should_fail_when_scene_counts_mismatch(db_session: AsyncSession):
    project = Project(name="数量不一致测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    llm = build_fake_two_phase_llm(
        first_payload=build_narrative_payload(scenes=[
            build_narrative_scene(title="场景一", narrative="第一场", dialogue="台词一"),
            build_narrative_scene(
                title="场景二",
                narrative="第二场",
                setting="室外",
                mood="紧张",
                character_actions={"主角": "奔跑"},
                dialogue="台词二",
            ),
        ]),
        second_payload=build_prompt_payload(scenes=[
            build_prompt_scene(sequence_order=0, title="场景一", video_prompt="scene one prompt"),
        ]),
    )

    with pytest.raises(RuntimeError, match="不一致"):
        await parse_project_from_episodes(project.id, "测试剧本", llm, db_session)


@pytest.mark.asyncio
async def test_parse_service_should_fail_when_prompt_generation_returns_empty_scenes(db_session: AsyncSession):
    project = Project(name="空提示词测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    llm = build_fake_two_phase_llm(
        first_payload=build_narrative_payload(scenes=[
            build_narrative_scene(title="场景一", narrative="第一场", dialogue="台词一"),
        ]),
        second_payload=build_prompt_payload(scenes=[]),
    )

    with pytest.raises(RuntimeError, match="未生成任何分镜提示词"):
        await parse_project_from_episodes(project.id, "测试剧本", llm, db_session)


@pytest.mark.asyncio
async def test_parse_service_should_persist_character_and_panel_when_scene_name_has_whitespace(
    db_session: AsyncSession,
):
    project = Project(name="角色映射测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    llm = build_fake_two_phase_llm(
        first_payload=build_narrative_payload(
            characters=[build_character(personality="冷静", costume="黑色风衣")],
            scenes=[
                build_narrative_scene(
                    title="场景一",
                    narrative="主角走入房间",
                    character_names=[" 主角 "],
                    character_actions={" 主角 ": "推门进入"},
                    dialogue="到了。",
                )
            ],
        ),
        second_payload=build_prompt_payload(scenes=[
            build_prompt_scene(sequence_order=0, title="场景一", video_prompt="cinematic indoor scene"),
        ]),
    )
    await parse_project_from_episodes(project.id, "测试剧本", llm, db_session)
    await db_session.commit()

    character = (await db_session.execute(
        select(Character).where(Character.project_id == project.id)
    )).scalar_one()
    episode = (await db_session.execute(
        select(Episode).where(Episode.project_id == project.id)
    )).scalar_one()
    panel = (await db_session.execute(
        select(Panel).where(Panel.project_id == project.id)
    )).scalar_one()

    assert episode.project_id == project.id
    assert character.name == "主角"
    assert panel.title == "场景一"
    assert panel.tts_text == "到了。"


@pytest.mark.asyncio
async def test_parse_service_should_create_single_panel_when_character_name_repeats(db_session: AsyncSession):
    project = Project(name="角色去重测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    llm = build_fake_two_phase_llm(
        first_payload=build_narrative_payload(
            characters=[build_character(personality="冷静", costume="黑色风衣")],
            scenes=[
                build_narrative_scene(
                    title="场景一",
                    narrative="主角反复出现",
                    character_names=["主角", "主角", " 主角 "],
                    character_actions={"主角": "看向门口"},
                    dialogue="重复但应去重。",
                )
            ],
        ),
        second_payload=build_prompt_payload(scenes=[
            build_prompt_scene(sequence_order=0, title="场景一", video_prompt="cinematic indoor scene"),
        ]),
    )
    await parse_project_from_episodes(project.id, "测试剧本", llm, db_session)
    await db_session.commit()

    panels = (await db_session.execute(
        select(Panel).where(Panel.project_id == project.id)
    )).scalars().all()
    assert len(panels) == 1


@pytest.mark.asyncio
async def test_parse_service_should_fallback_panel_title_when_prompt_title_blank(db_session: AsyncSession):
    project = Project(name="标题兜底测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    llm = build_fake_two_phase_llm(
        first_payload=build_narrative_payload(
            characters=[build_character(personality="冷静", costume="黑色风衣")],
            scenes=[
                build_narrative_scene(
                    title="叙事标题一",
                    narrative="主角进入房间",
                    character_actions={"主角": "推门"},
                    dialogue="到了。",
                )
            ],
        ),
        second_payload=build_prompt_payload(scenes=[
            build_prompt_scene(sequence_order=0, title="   ", video_prompt="cinematic indoor scene"),
        ]),
    )
    await parse_project_from_episodes(project.id, "测试剧本", llm, db_session)
    await db_session.commit()

    panel = (await db_session.execute(
        select(Panel).where(Panel.project_id == project.id)
    )).scalar_one()
    assert panel.title == "叙事标题一"


def test_extract_json_should_parse_embedded_object_text():
    payload = """
解析结果如下，请继续下一步：
{"foo": "bar", "count": 2}
以上为结构化内容。
"""
    parsed = extract_json_object(payload)
    assert parsed["foo"] == "bar"
    assert parsed["count"] == 2


def test_extract_json_should_parse_fenced_json_with_prefix_suffix():
    payload = """
好的，返回如下：
```json
{"result": {"panel_count": 3}}
```
请查收。
"""
    parsed = extract_json_object(payload)
    assert parsed["result"]["panel_count"] == 3
