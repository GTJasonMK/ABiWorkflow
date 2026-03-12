from __future__ import annotations

from types import SimpleNamespace

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.projects_workflow as workflow_api
import app.tasks.compose_tasks as compose_tasks
import app.tasks.import_tasks as import_tasks
from app.models import Episode, Panel, Project, TaskRecord


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
    assert payload["method"] == "markers"
    assert len(payload["episodes"]) >= 2
    assert payload["episodes"][0]["title"]
    assert payload["episodes"][0]["script_text"]


@pytest.mark.asyncio
async def test_llm_split_sync_should_fail_when_llm_returns_no_valid_episodes(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="同步 AI 分集失败测试", status="draft")
    db_session.add(project)
    await db_session.commit()

    async def fake_split(_content: str):
        raise ValueError("LLM 未返回有效分集结果")

    monkeypatch.setattr(workflow_api, "split_with_llm", fake_split)

    response = await client.post(
        f"/api/projects/{project.id}/import/llm-split",
        params={"async_mode": "false"},
        json={"content": "第1集：开场\n" + ("测试内容" * 40)},
    )
    assert response.status_code == 500
    assert "LLM 未返回有效分集结果" in response.json()["detail"]


@pytest.mark.asyncio
async def test_llm_split_async_should_fallback_to_sync_when_worker_unavailable(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="异步 AI 分集自动降级测试", status="draft")
    db_session.add(project)
    await db_session.commit()

    monkeypatch.setattr("app.tasks.health.has_celery_worker", lambda: False)
    monkeypatch.setattr("app.api.task_mode.has_celery_worker", lambda: False)

    async def fake_split(_content: str):
        return {
            "method": "llm",
            "confidence": 0.82,
            "episodes": [
                {
                    "title": "第1集 开场",
                    "summary": "故事开始",
                    "script_text": "主角来到城市，故事由此展开。",
                    "order": 0,
                }
            ],
        }

    monkeypatch.setattr(workflow_api, "split_with_llm", fake_split)

    response = await client.post(
        f"/api/projects/{project.id}/import/llm-split",
        params={"async_mode": "true"},
        json={"content": "第1集：开场\n" + ("测试内容" * 40)},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["method"] == "llm"
    assert payload["confidence"] == 0.82
    assert len(payload["episodes"]) == 1
    assert payload["episodes"][0]["title"] == "第1集 开场"


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


@pytest.mark.asyncio
async def test_retry_panel_video_provider_task_should_resubmit_and_replace_active_task(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜 provider 重试测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(project_id=project.id, episode_order=0, title="第1集")
    db_session.add(episode)
    await db_session.flush()

    panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="分镜一",
        visual_prompt="cinematic retry",
        status="failed",
        video_url="/media/videos/old-video.mp4",
        lipsync_video_url="/media/videos/old-lipsync.mp4",
        video_provider_task_id="provider-video-old",
        lipsync_provider_task_id="provider-lipsync-old",
        error_message="old failed",
    )
    db_session.add(panel)
    await db_session.flush()

    task = TaskRecord(
        task_type="video",
        target_type="panel",
        target_id=panel.id,
        project_id=project.id,
        episode_id=episode.id,
        panel_id=panel.id,
        source_task_id="provider-video-old",
        status="failed",
        payload_json=(
            '{"provider_key":"mock-video","request":{"prompt":"cinematic retry","seconds":5},'
            '"usage_type":"panel_video_generate","unit_price":0.25,"model_name":"demo-video-v1"}'
        ),
        message="旧视频任务失败",
    )
    db_session.add(task)
    await db_session.commit()

    captured: dict[str, object] = {}

    async def fake_submit_provider_task(db, *, provider_key: str, payload: dict):  # noqa: ANN001
        captured["provider_key"] = provider_key
        captured["payload"] = payload
        return {"task_id": "provider-video-retry-1", "status": "submitted"}

    async def fake_record_usage_cost(db, **kwargs):  # noqa: ANN001
        captured["usage_cost"] = kwargs
        return None

    monkeypatch.setattr("app.api.tasks.submit_provider_task", fake_submit_provider_task)
    monkeypatch.setattr("app.api.tasks.record_usage_cost", fake_record_usage_cost)

    response = await client.post(f"/api/tasks/{task.id}/retry")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["task_type"] == "video"
    assert data["status"] == "running"
    assert data["source_task_id"] == "provider-video-retry-1"
    assert data["payload"]["retry_from"] == task.id
    assert data["payload"]["provider_key"] == "mock-video"
    assert data["payload"]["unit_price"] == 0.25
    assert data["payload"]["model_name"] == "demo-video-v1"

    await db_session.refresh(panel)
    assert panel.video_provider_task_id == "provider-video-retry-1"
    assert panel.video_url is None
    assert panel.lipsync_video_url is None
    assert panel.lipsync_provider_task_id is None
    assert panel.status == "processing"
    assert panel.error_message is None

    assert captured["provider_key"] == "mock-video"
    assert captured["payload"] == {"prompt": "cinematic retry", "seconds": 5}
    assert isinstance(captured.get("usage_cost"), dict)
    assert captured["usage_cost"]["provider_type"] == "video"
    assert captured["usage_cost"]["provider_name"] == "mock-video"
    assert captured["usage_cost"]["usage_type"] == "panel_video_generate"
    assert captured["usage_cost"]["unit_price"] == 0.25
    assert captured["usage_cost"]["task_id"] == data["id"]


@pytest.mark.asyncio
async def test_retry_panel_provider_task_should_reject_when_panel_active_task_changed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜 provider 任务变更保护测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(project_id=project.id, episode_order=0, title="第1集")
    db_session.add(episode)
    await db_session.flush()

    panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="分镜一",
        visual_prompt="cinematic retry",
        status="processing",
        video_provider_task_id="provider-video-newer",
    )
    db_session.add(panel)
    await db_session.flush()

    task = TaskRecord(
        task_type="video",
        target_type="panel",
        target_id=panel.id,
        project_id=project.id,
        episode_id=episode.id,
        panel_id=panel.id,
        source_task_id="provider-video-old",
        status="failed",
        payload_json='{"provider_key":"mock-video","request":{"prompt":"old"}}',
        message="旧视频任务失败",
    )
    db_session.add(task)
    await db_session.commit()

    response = await client.post(f"/api/tasks/{task.id}/retry")
    assert response.status_code == 409
    assert response.json()["detail"] == "当前分镜的视频任务已变更，请回到对应分镜页面重新提交"


@pytest.mark.asyncio
async def test_cancel_running_panel_provider_task_should_reject_fake_celery_cancel(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜 provider 取消保护测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(project_id=project.id, episode_order=0, title="第1集")
    db_session.add(episode)
    await db_session.flush()

    panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="分镜一",
        visual_prompt="cancel guard",
        status="processing",
        video_provider_task_id="provider-video-running",
    )
    db_session.add(panel)
    await db_session.flush()

    task = TaskRecord(
        task_type="video",
        target_type="panel",
        target_id=panel.id,
        project_id=project.id,
        episode_id=episode.id,
        panel_id=panel.id,
        source_task_id="provider-video-running",
        status="running",
        payload_json='{"provider_key":"mock-video","request":{"prompt":"cancel guard"}}',
        message="视频任务运行中",
    )
    db_session.add(task)
    await db_session.commit()

    response = await client.post(f"/api/tasks/{task.id}/cancel")
    assert response.status_code == 400
    assert response.json()["detail"] == "外部 provider 任务暂不支持从任务中心取消，请回到 provider 侧处理或等待完成"

    await db_session.refresh(task)
    assert task.status == "running"
