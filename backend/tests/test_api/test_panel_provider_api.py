from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from tests.test_api._workflow_test_utils import build_episode, build_panel


@pytest.mark.asyncio
async def test_submit_panel_video_should_build_payload_from_effective_panel_binding(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜视频提交测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜一",
        visual_prompt="cinematic rainy street",
        duration_seconds=6.0,
        status="pending",
    )
    db_session.add(panel)
    await db_session.commit()

    captured: dict[str, object] = {}

    async def fake_submit_provider_task(db, *, provider_key: str, payload: dict):  # noqa: ANN001
        captured["provider_key"] = provider_key
        captured["payload"] = payload
        return {"task_id": "provider-video-task-1", "status": "submitted"}

    async def fake_record_usage_cost(*args, **kwargs):  # noqa: ANN001
        return None

    monkeypatch.setattr("app.api.panels.submit_provider_task", fake_submit_provider_task)
    monkeypatch.setattr("app.api.panels.record_usage_cost", fake_record_usage_cost)

    response = await client.post(
        f"/api/panels/{panel.id}/video/submit",
        json={"provider_key": "mock-video", "payload": {"seed": 42}},
    )
    assert response.status_code == 200
    assert response.json()["data"]["provider"]["task_id"] == "provider-video-task-1"
    assert captured["provider_key"] == "mock-video"
    assert captured["payload"] == {
        "prompt": "cinematic rainy street",
        "negative_prompt": None,
        "duration_seconds": 6.0,
        "reference_image_url": None,
        "seed": 42,
    }

    await db_session.refresh(panel)
    assert panel.provider_task_id == "provider-video-task-1"
    assert panel.status == "processing"


@pytest.mark.asyncio
async def test_submit_panel_lipsync_should_include_required_media_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜口型提交测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜二",
        visual_prompt="close-up portrait",
        status="completed",
        video_url="/media/videos/panel.mp4",
    )
    panel.tts_audio_url = "/media/audio/panel.mp3"
    db_session.add(panel)
    await db_session.commit()

    captured: dict[str, object] = {}

    async def fake_submit_provider_task(db, *, provider_key: str, payload: dict):  # noqa: ANN001
        captured["provider_key"] = provider_key
        captured["payload"] = payload
        return {"task_id": "provider-lipsync-task-1", "status": "submitted"}

    async def fake_record_usage_cost(*args, **kwargs):  # noqa: ANN001
        return None

    monkeypatch.setattr("app.api.panels.submit_provider_task", fake_submit_provider_task)
    monkeypatch.setattr("app.api.panels.record_usage_cost", fake_record_usage_cost)

    response = await client.post(
        f"/api/panels/{panel.id}/lipsync/submit",
        json={"provider_key": "mock-lipsync", "payload": {"fps": 25}},
    )
    assert response.status_code == 200
    assert response.json()["data"]["provider"]["task_id"] == "provider-lipsync-task-1"
    assert captured["provider_key"] == "mock-lipsync"
    assert captured["payload"] == {
        "video_url": "/media/videos/panel.mp4",
        "audio_url": "/media/audio/panel.mp3",
        "panel_id": panel.id,
        "fps": 25,
    }

    await db_session.refresh(panel)
    assert panel.provider_task_id == "provider-lipsync-task-1"
    assert panel.status == "processing"


@pytest.mark.asyncio
async def test_get_panel_video_status_should_sync_panel_status_payload(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜视频状态测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜状态",
        visual_prompt="status prompt",
        status="processing",
    )
    panel.provider_task_id = "provider-video-task-status-1"
    db_session.add(panel)
    await db_session.commit()

    async def fake_query_provider_task_status(db, *, provider_key: str, task_id: str):  # noqa: ANN001
        assert provider_key == "mock-video"
        assert task_id == "provider-video-task-status-1"
        return {"status": "completed", "progress_percent": 100}

    monkeypatch.setattr("app.api.panels.query_provider_task_status", fake_query_provider_task_status)

    response = await client.get(f"/api/panels/{panel.id}/video/status", params={"provider_key": "mock-video"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider_status"]["status"] == "completed"
    assert data["panel"]["status"] == "completed"

    await db_session.refresh(panel)
    assert panel.status == "completed"


@pytest.mark.asyncio
async def test_apply_panel_lipsync_should_update_result_field(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜口型应用测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜口型应用",
        visual_prompt="portrait prompt",
        status="processing",
        video_url="/media/videos/original.mp4",
    )
    db_session.add(panel)
    await db_session.commit()

    response = await client.post(
        f"/api/panels/{panel.id}/lipsync/apply",
        json={"result_url": "https://example.com/lipsync-result.mp4"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["lipsync_video_url"] == "https://example.com/lipsync-result.mp4"
    assert data["status"] == "completed"

    await db_session.refresh(panel)
    assert panel.lipsync_video_url == "https://example.com/lipsync-result.mp4"
    assert panel.status == "completed"
