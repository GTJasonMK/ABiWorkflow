from __future__ import annotations

import asyncio
from types import SimpleNamespace
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Project, Scene
from app.tasks.compose_tasks import compose_video_task
from app.tasks.generate_tasks import generate_videos_task
from app.tasks.parse_tasks import _run_parse, parse_script_task


class _FakeTaskDispatcher:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.calls: list[tuple[tuple, dict]] = []

    def delay(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(id=self.task_id)


def _force_worker_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.tasks.health.has_celery_worker", lambda: True)
    # task_mode.py 在模块顶层 import 了 has_celery_worker，需同时 patch 该引用
    monkeypatch.setattr("app.api.task_mode.has_celery_worker", lambda: True)


@pytest.mark.asyncio
async def test_parse_async_should_queue_task(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _force_worker_available(monkeypatch)
    project = Project(name="异步解析测试", status="draft", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    fake_dispatcher = _FakeTaskDispatcher("parse-task-1")
    monkeypatch.setattr("app.tasks.parse_tasks.parse_script_task", fake_dispatcher)

    response = await client.post(f"/api/projects/{project.id}/parse", params={"async_mode": "true"})
    assert response.status_code == 200
    assert response.json()["data"]["task_id"] == "parse-task-1"
    assert len(fake_dispatcher.calls) == 1
    assert fake_dispatcher.calls[0][0] == (project.id, "draft", "测试剧本")

    await db_session.refresh(project)
    assert project.status == "parsing"


@pytest.mark.asyncio
async def test_generate_async_should_queue_task(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _force_worker_available(monkeypatch)
    project = Project(name="异步生成测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add(scene)
    await db_session.commit()

    fake_dispatcher = _FakeTaskDispatcher("gen-task-1")
    monkeypatch.setattr("app.tasks.generate_tasks.generate_videos_task", fake_dispatcher)

    response = await client.post(f"/api/projects/{project.id}/generate", params={"async_mode": "true"})
    assert response.status_code == 200
    assert response.json()["data"]["task_id"] == "gen-task-1"

    await db_session.refresh(project)
    assert project.status == "generating"


@pytest.mark.asyncio
async def test_generate_async_should_not_queue_when_no_scene_needs_regeneration(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _force_worker_available(monkeypatch)
    project = Project(name="异步空生成直返测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.commit()

    fake_dispatcher = _FakeTaskDispatcher("gen-task-unused")
    monkeypatch.setattr("app.tasks.generate_tasks.generate_videos_task", fake_dispatcher)

    response = await client.post(f"/api/projects/{project.id}/generate", params={"async_mode": "true"})
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_scenes"] == 1
    assert payload["completed"] == 1
    assert payload["failed"] == 0
    assert "task_id" not in payload
    assert fake_dispatcher.calls == []

    await db_session.refresh(project)
    assert project.status == "completed"


@pytest.mark.asyncio
async def test_compose_async_should_queue_task(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    _force_worker_available(monkeypatch)
    project = Project(name="异步合成测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.commit()

    fake_dispatcher = _FakeTaskDispatcher("compose-task-1")
    monkeypatch.setattr("app.tasks.compose_tasks.compose_video_task", fake_dispatcher)

    response = await client.post(
        f"/api/projects/{project.id}/compose",
        params={"async_mode": "true"},
        json={"include_subtitles": False, "include_tts": False},
    )
    assert response.status_code == 200
    assert response.json()["data"]["task_id"] == "compose-task-1"

    await db_session.refresh(project)
    assert project.status == "composing"


@pytest.mark.asyncio
async def test_task_status_endpoint_should_return_result(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    class FakeAsyncResult:
        state = "SUCCESS"
        result = {"composition_id": "comp-1"}

        def __init__(self, task_id: str, app):
            self.task_id = task_id
            self.app = app

        def ready(self) -> bool:
            return True

        def successful(self) -> bool:
            return True

    monkeypatch.setattr("app.api.tasks.AsyncResult", FakeAsyncResult)

    response = await client.get("/api/tasks/comp-task-1")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["task_id"] == "comp-task-1"
    assert data["state"] == "success"
    assert data["successful"] is True
    assert data["result"]["composition_id"] == "comp-1"


@pytest.mark.asyncio
async def test_parse_async_should_fallback_to_sync_when_worker_unavailable(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.tasks.health.has_celery_worker", lambda: False)

    class FakeLLM:
        async def close(self) -> None:
            return None

    async def fake_parse_script(self, project_id: str, script_text: str, db: AsyncSession):  # noqa: ANN001
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = "parsed"
        return SimpleNamespace(character_count=2, scene_count=3)

    monkeypatch.setattr("app.llm.factory.create_llm_adapter", lambda: FakeLLM())
    monkeypatch.setattr("app.services.script_parser.ScriptParserService.parse_script", fake_parse_script)

    project = Project(name="异步解析降级测试", status="draft", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/parse", params={"async_mode": "true"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["character_count"] == 2
    assert data["scene_count"] == 3
    assert "task_id" not in data


@pytest.mark.asyncio
async def test_generate_async_should_fallback_to_sync_when_worker_unavailable(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.tasks.health.has_celery_worker", lambda: False)

    async def fake_generate_all(self, project_id: str, db: AsyncSession):  # noqa: ANN001
        scenes = (await db.execute(select(Scene).where(Scene.project_id == project_id))).scalars().all()
        for scene in scenes:
            scene.status = "generated"
        await db.flush()

    monkeypatch.setattr("app.services.video_generator.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="异步生成降级测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate", params={"async_mode": "true"})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_scenes"] == 1
    assert data["completed"] == 1
    assert data["failed"] == 0
    assert "task_id" not in data


@pytest.mark.asyncio
async def test_compose_async_should_fallback_to_sync_when_worker_unavailable(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr("app.tasks.health.has_celery_worker", lambda: False)

    project = Project(name="异步降级测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.commit()

    async def fake_compose(self, project_id: str, options, db: AsyncSession):  # noqa: ANN001
        return "comp-sync-1"

    monkeypatch.setattr("app.api.composition.VideoEditorService.compose", fake_compose)

    response = await client.post(
        f"/api/projects/{project.id}/compose",
        params={"async_mode": "true"},
        json={"include_subtitles": False, "include_tts": False},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["composition_id"] == "comp-sync-1"
    assert "task_id" not in data


@pytest.mark.asyncio
async def test_run_parse_should_restore_status_when_llm_init_failed(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="异步解析回滚测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    test_db_url = f"sqlite+aiosqlite:///{Path('test.db').resolve().as_posix()}"
    monkeypatch.setattr(settings, "database_url", test_db_url)

    def _raise_init_error():  # noqa: ANN202
        raise RuntimeError("llm init failed")

    monkeypatch.setattr("app.llm.factory.create_llm_adapter", _raise_init_error)

    with pytest.raises(RuntimeError, match="llm init failed"):
        await _run_parse(project.id, "draft", project.script_text)

    await db_session.refresh(project)
    assert project.status == "draft"


@pytest.mark.asyncio
async def test_parse_task_wrapper_should_restore_status_when_run_parse_failed_early(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="解析包装回滚测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    test_db_url = f"sqlite+aiosqlite:///{Path('test.db').resolve().as_posix()}"
    monkeypatch.setattr(settings, "database_url", test_db_url)
    # 禁用 reload_settings 防止 Celery 任务入口覆盖 monkeypatch 的 database_url
    monkeypatch.setattr("app.config.reload_settings", lambda: None)

    async def fake_run_parse(project_id: str, previous_status: str, script_text: str | None = None):  # noqa: ANN001
        raise RuntimeError("parse wrapper failed early")

    monkeypatch.setattr("app.tasks.parse_tasks._run_parse", fake_run_parse)

    with pytest.raises(RuntimeError, match="parse wrapper failed early"):
        await asyncio.to_thread(parse_script_task.run, project.id, "draft", project.script_text)

    await db_session.refresh(project)
    assert project.status == "draft"


@pytest.mark.asyncio
async def test_generate_task_wrapper_should_restore_status_when_run_generate_failed_early(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="生成包装回滚测试", status="generating")
    db_session.add(project)
    await db_session.commit()

    test_db_url = f"sqlite+aiosqlite:///{Path('test.db').resolve().as_posix()}"
    monkeypatch.setattr(settings, "database_url", test_db_url)
    # 禁用 reload_settings 防止 Celery 任务入口覆盖 monkeypatch 的 database_url
    monkeypatch.setattr("app.config.reload_settings", lambda: None)

    async def fake_run_generate(project_id: str, previous_status: str, force_regenerate: bool = False):  # noqa: ANN001
        raise RuntimeError("generate wrapper failed early")

    monkeypatch.setattr("app.tasks.generate_tasks._run_generate", fake_run_generate)

    with pytest.raises(RuntimeError, match="generate wrapper failed early"):
        await asyncio.to_thread(generate_videos_task.run, project.id, "parsed")

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_compose_task_wrapper_should_restore_status_when_run_compose_failed_early(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="合成包装回滚测试", status="composing")
    db_session.add(project)
    await db_session.commit()

    test_db_url = f"sqlite+aiosqlite:///{Path('test.db').resolve().as_posix()}"
    monkeypatch.setattr(settings, "database_url", test_db_url)
    # 禁用 reload_settings 防止 Celery 任务入口覆盖 monkeypatch 的 database_url
    monkeypatch.setattr("app.config.reload_settings", lambda: None)

    async def fake_run_compose(project_id: str, options: dict | None, previous_status: str):  # noqa: ANN001
        raise RuntimeError("compose wrapper failed early")

    monkeypatch.setattr("app.tasks.compose_tasks._run_compose", fake_run_compose)

    with pytest.raises(RuntimeError, match="compose wrapper failed early"):
        await asyncio.to_thread(compose_video_task.run, project.id, {"include_subtitles": False}, "parsed")

    await db_session.refresh(project)
    assert project.status == "parsed"
