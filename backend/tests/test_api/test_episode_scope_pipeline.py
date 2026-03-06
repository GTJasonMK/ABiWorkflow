from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CompositionTask, Episode, Panel, Project, Scene, TaskRecord


@pytest.mark.asyncio
async def test_generate_should_scope_to_episode_and_force_sync_mode(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    captured_scene_ids: set[str] = set()

    class _FakeProvider:
        max_duration_seconds = 5.0

    async def fake_generate_all(
        self,
        project_id: str,
        db: AsyncSession,
        *,
        scene_ids: set[str] | None = None,
    ):  # noqa: ANN001
        nonlocal captured_scene_ids
        captured_scene_ids = set(scene_ids or set())
        stmt = select(Scene).where(Scene.project_id == project_id)
        if scene_ids:
            stmt = stmt.where(Scene.id.in_(list(scene_ids)))
        scenes = (await db.execute(stmt)).scalars().all()
        for item in scenes:
            if item.status in {"pending", "failed", "generating"}:
                item.status = "generated"
        await db.flush()

    monkeypatch.setattr("app.api.generation.get_provider", lambda: _FakeProvider())
    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="单集生成作用域测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode_1 = Episode(project_id=project.id, episode_order=0, title="第1集")
    episode_2 = Episode(project_id=project.id, episode_order=1, title="第2集")
    db_session.add_all([episode_1, episode_2])
    await db_session.flush()

    panel_1 = Panel(
        project_id=project.id,
        episode_id=episode_1.id,
        panel_order=0,
        title="分镜 1",
        visual_prompt="镜头一提示词",
        duration_seconds=5.0,
        status="pending",
    )
    panel_2 = Panel(
        project_id=project.id,
        episode_id=episode_2.id,
        panel_order=0,
        title="分镜 2",
        visual_prompt="镜头二提示词",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add_all([panel_1, panel_2])
    await db_session.flush()

    scene_1 = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景 1",
        video_prompt="镜头一提示词",
        duration_seconds=5.0,
        status="pending",
    )
    scene_2 = Scene(
        project_id=project.id,
        sequence_order=1,
        title="场景 2",
        video_prompt="镜头二提示词",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add_all([scene_1, scene_2])
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/generate",
        params={"episode_id": episode_1.id, "async_mode": "true"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_panels"] == 1
    assert payload["completed"] == 1
    assert payload["failed"] == 0
    assert "task_id" not in payload

    await db_session.refresh(scene_1)
    await db_session.refresh(scene_2)
    await db_session.refresh(project)
    assert captured_scene_ids == {scene_1.id}
    assert scene_1.status == "generated"
    assert scene_2.status == "generated"
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_compose_should_scope_to_episode_and_force_sync_mode(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    captured_episode_id: str | None = None

    async def fake_compose(
        self,
        project_id: str,
        options,
        db: AsyncSession,
        episode_id: str | None = None,
    ):  # noqa: ANN001
        nonlocal captured_episode_id
        captured_episode_id = episode_id
        task = CompositionTask(
            id="composition-episode-only",
            project_id=project_id,
            episode_id=episode_id,
            output_path="./outputs/compositions/composition-episode-only.mp4",
            transition_type=options.transition_type.value,
            include_subtitles=options.include_subtitles,
            include_tts=options.include_tts,
            status="completed",
        )
        db.add(task)
        await db.flush()
        return task.id

    monkeypatch.setattr("app.api.composition.VideoEditorService.compose", fake_compose)

    project = Project(name="单集合成作用域测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode_1 = Episode(project_id=project.id, episode_order=0, title="第1集")
    episode_2 = Episode(project_id=project.id, episode_order=1, title="第2集")
    db_session.add_all([episode_1, episode_2])
    await db_session.flush()

    db_session.add_all([
        Panel(
            project_id=project.id,
            episode_id=episode_1.id,
            panel_order=0,
            title="分镜 1",
            visual_prompt="镜头一提示词",
            duration_seconds=5.0,
            status="completed",
            video_url="/media/videos/fake1.mp4",
        ),
        Panel(
            project_id=project.id,
            episode_id=episode_2.id,
            panel_order=0,
            title="分镜 2",
            visual_prompt="镜头二提示词",
            duration_seconds=5.0,
            status="completed",
            video_url="/media/videos/fake2.mp4",
        ),
    ])
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/compose",
        params={"episode_id": episode_1.id, "async_mode": "true"},
        json={"include_subtitles": False, "include_tts": False},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["composition_id"] == "composition-episode-only"
    assert payload["episode_id"] == episode_1.id
    assert "task_id" not in payload

    await db_session.refresh(project)
    assert captured_episode_id == episode_1.id
    assert project.status == "parsed"

    saved_task = (await db_session.execute(
        select(CompositionTask).where(CompositionTask.id == "composition-episode-only")
    )).scalar_one()
    assert saved_task.episode_id == episode_1.id


@pytest.mark.asyncio
async def test_generate_should_not_pollute_project_status_when_episode_scope_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_all(
        self,
        project_id: str,
        db: AsyncSession,
        *,
        scene_ids: set[str] | None = None,
    ):  # noqa: ANN001
        stmt = select(Scene).where(Scene.project_id == project_id)
        if scene_ids:
            stmt = stmt.where(Scene.id.in_(list(scene_ids)))
        scenes = (await db.execute(stmt)).scalars().all()
        for item in scenes:
            item.status = "failed"
        await db.flush()

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="分集失败不污染全局测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode_1 = Episode(project_id=project.id, episode_order=0, title="第1集")
    episode_2 = Episode(project_id=project.id, episode_order=1, title="第2集")
    db_session.add_all([episode_1, episode_2])
    await db_session.flush()

    db_session.add_all([
        Panel(
            project_id=project.id,
            episode_id=episode_1.id,
            panel_order=0,
            title="分镜 1",
            visual_prompt="镜头一提示词",
            duration_seconds=5.0,
            status="pending",
        ),
        Panel(
            project_id=project.id,
            episode_id=episode_2.id,
            panel_order=0,
            title="分镜 2",
            visual_prompt="镜头二提示词",
            duration_seconds=5.0,
            status="completed",
            video_url="/media/videos/fake2.mp4",
        ),
    ])
    await db_session.flush()

    scene_1 = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景 1",
        video_prompt="镜头一提示词",
        duration_seconds=5.0,
        status="pending",
    )
    scene_2 = Scene(
        project_id=project.id,
        sequence_order=1,
        title="场景 2",
        video_prompt="镜头二提示词",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add_all([scene_1, scene_2])
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/generate",
        params={"episode_id": episode_1.id},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_panels"] == 1
    assert payload["completed"] == 0
    assert payload["failed"] == 1

    await db_session.refresh(project)
    assert project.status == "parsed"

    task = (await db_session.execute(
        select(TaskRecord)
        .where(TaskRecord.project_id == project.id, TaskRecord.episode_id == episode_1.id)
        .order_by(TaskRecord.created_at.desc())
    )).scalars().first()
    assert task is not None
    assert task.status == "failed"
    assert task.error_message == "仍有 1 个分镜生成失败"


@pytest.mark.asyncio
async def test_latest_composition_should_filter_by_episode_scope(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分集 latest 成片过滤测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode_1 = Episode(project_id=project.id, episode_order=0, title="第1集")
    episode_2 = Episode(project_id=project.id, episode_order=1, title="第2集")
    db_session.add_all([episode_1, episode_2])
    await db_session.flush()

    db_session.add_all([
        CompositionTask(
            id="comp-episode-1",
            project_id=project.id,
            episode_id=episode_1.id,
            status="completed",
            transition_type="crossfade",
            include_subtitles=True,
            include_tts=True,
            output_path="./outputs/compositions/comp-episode-1.mp4",
        ),
        CompositionTask(
            id="comp-episode-2",
            project_id=project.id,
            episode_id=episode_2.id,
            status="completed",
            transition_type="crossfade",
            include_subtitles=True,
            include_tts=True,
            output_path="./outputs/compositions/comp-episode-2.mp4",
        ),
    ])
    await db_session.commit()

    response = await client.get(
        f"/api/projects/{project.id}/compositions/latest",
        params={"episode_id": episode_1.id},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["id"] == "comp-episode-1"
    assert payload["episode_id"] == episode_1.id


@pytest.mark.asyncio
async def test_latest_composition_should_return_404_when_episode_not_in_project(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project_a = Project(name="Project A", status="completed")
    project_b = Project(name="Project B", status="completed")
    db_session.add_all([project_a, project_b])
    await db_session.flush()

    foreign_episode = Episode(project_id=project_b.id, episode_order=0, title="B-第1集")
    db_session.add(foreign_episode)
    await db_session.commit()

    response = await client.get(
        f"/api/projects/{project_a.id}/compositions/latest",
        params={"episode_id": foreign_episode.id},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "分集不存在"
