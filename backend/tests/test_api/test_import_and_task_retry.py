from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.projects_workflow as workflow_api
import app.tasks.compose_tasks as compose_tasks
import app.tasks.import_tasks as import_tasks
from app.models import Episode, Panel, Project, TaskRecord
from app.schemas.common import ApiResponse


@pytest.mark.asyncio
async def test_marker_split_should_detect_episode_markers(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="导入测试项目", status="draft")
    db_session.add(project)
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/import/marker-split",
        json={
            "content": (
                "第1集：开场\n"
                "小明走进教室，看到大家都在讨论新老师。老师点名后安排了一次分组展示，\n"
                "小明因为准备不足有些紧张，但还是决定主动承担介绍环节。\n\n"
                "第2集：冲突\n"
                "班长与小明因为社团名额发生争执，气氛紧张。两人围绕活动安排和资源分配继续争论，\n"
                "其他同学也被卷入其中，整个班级的关系迅速变得微妙起来。"
            )
        },
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["method"] in {"markers", "llm_fallback", "heuristic"}
    assert len(payload["episodes"]) >= 2
    assert payload["episodes"][0]["title"]
    assert payload["episodes"][0]["script_text"]


@pytest.mark.asyncio
async def test_import_commit_should_merge_script_and_delegate_parse(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="导入落库项目", status="draft")
    db_session.add(project)
    await db_session.commit()

    async def fake_parse_script(*_args, **_kwargs):
        return ApiResponse(data={"character_count": 2, "panel_count": 3, "episode_count": 1})

    monkeypatch.setattr(workflow_api, "parse_script", fake_parse_script)

    response = await client.post(
        f"/api/projects/{project.id}/import/commit",
        json={
            "episodes": [
                {
                    "title": "第1集 开端",
                    "summary": "故事开场",
                    "script_text": "主角来到新城市，准备开始新生活。",
                },
                {
                    "title": "第2集 冲突",
                    "summary": "矛盾升级",
                    "script_text": "竞争对手出现，双方冲突逐渐升级。",
                },
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["episode_count"] == 2
    assert data["script_char_count"] > 0
    assert data["parse"]["character_count"] == 2
    assert data["parse"]["panel_count"] == 3

    refreshed = (await db_session.execute(select(Project).where(Project.id == project.id))).scalar_one()
    assert "第1集 开端" in (refreshed.script_text or "")
    assert "第2集 冲突" in (refreshed.script_text or "")

    episodes = (await db_session.execute(select(Episode).where(Episode.project_id == project.id))).scalars().all()
    panels = (await db_session.execute(select(Panel).where(Panel.project_id == project.id))).scalars().all()
    assert len(episodes) == 0
    assert len(panels) == 0


@pytest.mark.asyncio
async def test_dismiss_failed_tasks_should_mark_failed_and_cancelled(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="任务忽略项目", status="draft")
    db_session.add(project)
    await db_session.flush()

    rows = [
        TaskRecord(task_type="parse", status="failed", project_id=project.id, message="failed"),
        TaskRecord(task_type="generate", status="cancelled", project_id=project.id, message="cancelled"),
        TaskRecord(task_type="compose", status="completed", project_id=project.id, message="done"),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    response = await client.post("/api/tasks/dismiss-failed", json={"project_id": project.id})
    assert response.status_code == 200
    assert response.json()["data"]["dismissed"] == 2


@pytest.mark.asyncio
async def test_retry_task_should_enqueue_new_llm_split_task(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="任务重试项目", status="draft")
    db_session.add(project)
    await db_session.flush()

    task = TaskRecord(
        task_type="episode_split_llm",
        status="failed",
        project_id=project.id,
        payload_json='{"project_id":"%s","content":"第1集：开场\\n内容\\n\\n第2集：冲突\\n内容"}' % project.id,
        message="原任务失败",
        source_task_id="old-task-id",
    )
    db_session.add(task)
    await db_session.commit()

    monkeypatch.setattr(
        import_tasks.split_episodes_llm_task,
        "delay",
        lambda *_args, **_kwargs: SimpleNamespace(id="retry-task-001"),
    )

    response = await client.post(f"/api/tasks/{task.id}/retry")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["source_task_id"] == "retry-task-001"
    assert payload["task_type"] == "episode_split_llm"
    assert payload["retry_count"] >= 1


@pytest.mark.asyncio
async def test_retry_episode_generate_task_should_reject_project_wide_fallback(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分集生成重试作用域测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(project_id=project.id, episode_order=0, title="第1集")
    db_session.add(episode)
    await db_session.flush()

    task = TaskRecord(
        task_type="generate",
        status="failed",
        project_id=project.id,
        episode_id=episode.id,
        payload_json=(
            '{"project_id":"%s","episode_id":"%s","scope":"episode","force_regenerate":true}'
            % (project.id, episode.id)
        ),
        message="原分集生成任务失败",
    )
    db_session.add(task)
    await db_session.commit()

    response = await client.post(f"/api/tasks/{task.id}/retry")
    assert response.status_code == 400
    assert response.json()["detail"] == "分集生成任务请回到对应分集页面重试"


@pytest.mark.asyncio
async def test_retry_compose_task_should_preserve_episode_scope(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="合成重试作用域测试", status="completed")
    db_session.add(project)
    await db_session.flush()
    episode = Episode(project_id=project.id, episode_order=0, title="第1集")
    db_session.add(episode)
    await db_session.flush()

    task = TaskRecord(
        task_type="compose",
        status="failed",
        project_id=project.id,
        episode_id=episode.id,
        payload_json=(
            '{"project_id":"%s","episode_id":"%s","options":{"include_subtitles":false,"include_tts":false}}'
            % (project.id, episode.id)
        ),
        message="原合成任务失败",
        source_task_id="old-compose-task",
    )
    db_session.add(task)
    await db_session.commit()

    captured: dict[str, str | None] = {"project_id": None, "episode_id": None}

    def fake_delay(  # noqa: ANN001
        project_id: str,
        options_dict: dict | None = None,
        previous_status: str = "parsed",
        episode_id: str | None = None,
    ):
        captured["project_id"] = project_id
        captured["episode_id"] = episode_id
        return SimpleNamespace(id="retry-compose-001")

    monkeypatch.setattr(compose_tasks.compose_video_task, "delay", fake_delay)

    response = await client.post(f"/api/tasks/{task.id}/retry")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["source_task_id"] == "retry-compose-001"
    assert payload["task_type"] == "compose"
    assert payload["episode_id"] == episode.id
    assert captured["project_id"] == project.id
    assert captured["episode_id"] == episode.id
