from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.episode_status import EPISODE_STATUS_DRAFT
from app.models import Episode, Panel, Project, Scene
from app.panel_status import PANEL_STATUS_COMPLETED, PANEL_STATUS_PENDING
from app.services.storyboard_bridge import migrate_legacy_scenes_to_panels


@pytest.mark.asyncio
async def test_migrate_legacy_scenes_to_panels_should_convert_scene_only_project(
    db_session: AsyncSession,
):
    project = Project(name="历史场景项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    db_session.add_all([
        Scene(
            project_id=project.id,
            sequence_order=0,
            title="场景一",
            description="剧情一",
            video_prompt="prompt-1",
            duration_seconds=4.0,
            status="generated",
        ),
        Scene(
            project_id=project.id,
            sequence_order=1,
            title="场景二",
            description="剧情二",
            video_prompt="prompt-2",
            duration_seconds=5.0,
            status="pending",
        ),
    ])
    await db_session.commit()

    migrated_projects, migrated_panels = await migrate_legacy_scenes_to_panels(db_session)
    await db_session.commit()

    assert migrated_projects == 1
    assert migrated_panels == 2

    episodes = (await db_session.execute(
        select(Episode).where(Episode.project_id == project.id)
    )).scalars().all()
    assert len(episodes) == 1
    assert episodes[0].status == EPISODE_STATUS_DRAFT

    panels = (await db_session.execute(
        select(Panel).where(Panel.project_id == project.id).order_by(Panel.panel_order)
    )).scalars().all()
    assert len(panels) == 2
    assert panels[0].title == "场景一"
    assert panels[0].visual_prompt == "prompt-1"
    assert panels[0].status == PANEL_STATUS_COMPLETED
    assert panels[1].title == "场景二"
    assert panels[1].visual_prompt == "prompt-2"
    assert panels[1].status == PANEL_STATUS_PENDING


@pytest.mark.asyncio
async def test_migrate_legacy_scenes_to_panels_should_skip_project_with_existing_panels(
    db_session: AsyncSession,
):
    project = Project(name="已有分镜项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    db_session.add(Scene(
        project_id=project.id,
        sequence_order=0,
        title="历史场景",
        video_prompt="legacy-prompt",
        duration_seconds=4.0,
        status="generated",
    ))

    episode = Episode(
        project_id=project.id,
        episode_order=0,
        title="第1集",
        summary=None,
        status=EPISODE_STATUS_DRAFT,
    )
    db_session.add(episode)
    await db_session.flush()

    panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="已有分镜",
        visual_prompt="panel-prompt",
        duration_seconds=5.0,
        status=PANEL_STATUS_PENDING,
    )
    db_session.add(panel)
    await db_session.commit()

    migrated_projects, migrated_panels = await migrate_legacy_scenes_to_panels(db_session)
    await db_session.commit()

    assert migrated_projects == 0
    assert migrated_panels == 0

    panels = (await db_session.execute(
        select(Panel).where(Panel.project_id == project.id)
    )).scalars().all()
    assert len(panels) == 1
    assert panels[0].title == "已有分镜"
