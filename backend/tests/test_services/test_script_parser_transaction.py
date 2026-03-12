from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.episode_status import EPISODE_STATUS_DRAFT
from app.models import Character, CompositionTask, Episode, Panel, Project
from app.services.episode_parse_pipeline import parse_project_from_episodes
from tests.test_services._script_parser_test_utils import (
    build_fake_two_phase_llm,
    build_narrative_payload,
    build_narrative_scene,
    build_prompt_payload,
    build_prompt_scene,
)


def _build_llm():
    return build_fake_two_phase_llm(
        first_payload=build_narrative_payload(scenes=[
            build_narrative_scene(
                title="新场景",
                narrative="主角走进房间",
                setting="室内 夜晚",
                character_actions={"主角": "缓慢行走"},
                dialogue="我们开始吧。",
            )
        ]),
        second_payload=build_prompt_payload(scenes=[
            build_prompt_scene(
                sequence_order=0,
                title="新场景",
                video_prompt="A man enters a dark room, cinematic, tracking shot",
                style_keywords="cinematic, dark",
            )
        ]),
    )


@pytest.mark.asyncio
async def test_parse_service_should_not_commit_implicitly(db_session: AsyncSession):
    project = Project(name="事务测试", status="parsing", script_text="一段测试剧本")
    db_session.add(project)
    await db_session.flush()

    old_episode = Episode(
        project_id=project.id,
        episode_order=0,
        title="第1集",
        status=EPISODE_STATUS_DRAFT,
    )
    db_session.add(old_episode)
    await db_session.flush()

    old_panel = Panel(
        project_id=project.id,
        episode_id=old_episode.id,
        panel_order=0,
        title="旧场景",
        visual_prompt="old-prompt",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add(old_panel)
    await db_session.commit()

    project_id = project.id

    llm = _build_llm()
    await parse_project_from_episodes(project_id, project.script_text or "", llm, db_session)

    await db_session.rollback()

    panels = (await db_session.execute(
        select(Panel).where(Panel.project_id == project_id).order_by(Panel.panel_order)
    )).scalars().all()
    characters = (await db_session.execute(
        select(Character).where(Character.project_id == project_id)
    )).scalars().all()
    restored_project = (await db_session.execute(
        select(Project).where(Project.id == project_id)
    )).scalar_one()

    assert len(panels) == 1
    assert panels[0].title == "旧场景"
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

    llm = _build_llm()
    await parse_project_from_episodes(project.id, project.script_text or "", llm, db_session)
    await db_session.commit()

    refreshed_composition = (await db_session.execute(
        select(CompositionTask).where(CompositionTask.id == old_composition.id)
    )).scalar_one()
    assert refreshed_composition.status == "stale"
