from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, TaskRecord
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
        "seconds": 6,
        "reference_image_url": None,
        "seed": 42,
    }

    await db_session.refresh(panel)
    assert panel.video_provider_task_id == "provider-video-task-1"
    assert panel.lipsync_provider_task_id is None
    assert panel.tts_provider_task_id is None
    assert panel.status == "processing"


@pytest.mark.asyncio
async def test_submit_panel_video_should_use_episode_provider_and_payload_defaults_when_request_omits_provider_key(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜视频默认 provider 测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(
        project.id,
        video_provider_key="mock-video",
        provider_payload_defaults={
            "video": {
                "seed": 7,
                "strength": 0.65,
                "prompt": "should-be-overridden",
                "seconds": 99,
                "reference_image_url": "https://example.com/ignored.png",
            },
        },
    )
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="默认 provider 分镜",
        visual_prompt="episode default prompt",
        duration_seconds=6.0,
        status="pending",
    )
    db_session.add(panel)
    await db_session.commit()

    captured: dict[str, object] = {}

    async def fake_submit_provider_task(db, *, provider_key: str, payload: dict):  # noqa: ANN001
        captured["provider_key"] = provider_key
        captured["payload"] = payload
        return {"task_id": "provider-video-task-default-1", "status": "submitted"}

    async def fake_record_usage_cost(*args, **kwargs):  # noqa: ANN001
        return None

    monkeypatch.setattr("app.api.panels.submit_provider_task", fake_submit_provider_task)
    monkeypatch.setattr("app.api.panels.record_usage_cost", fake_record_usage_cost)

    response = await client.post(
        f"/api/panels/{panel.id}/video/submit",
        json={"payload": {"seed": 42}},
    )
    assert response.status_code == 200
    assert response.json()["data"]["provider"]["task_id"] == "provider-video-task-default-1"
    assert captured["provider_key"] == "mock-video"
    assert captured["payload"] == {
        "seed": 42,
        "strength": 0.65,
        "prompt": "episode default prompt",
        "seconds": 6,
        "negative_prompt": None,
        "reference_image_url": None,
    }

    await db_session.refresh(panel)
    assert panel.video_provider_task_id == "provider-video-task-default-1"
    assert panel.video_status == "queued"
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
    assert panel.lipsync_provider_task_id == "provider-lipsync-task-1"
    assert panel.video_provider_task_id is None
    assert panel.tts_provider_task_id is None
    assert panel.lipsync_status == "queued"
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
    panel.video_provider_task_id = "provider-video-task-status-1"
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
async def test_get_panel_lipsync_status_should_return_provider_status_without_mutating_panel_status(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜口型状态测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜口型状态",
        visual_prompt="portrait status prompt",
        status="processing",
    )
    panel.lipsync_provider_task_id = "provider-lipsync-task-status-1"
    db_session.add(panel)
    await db_session.commit()

    async def fake_query_provider_task_status(db, *, provider_key: str, task_id: str):  # noqa: ANN001
        assert provider_key == "mock-lipsync"
        assert task_id == "provider-lipsync-task-status-1"
        return {"status": "running", "progress_percent": 60}

    monkeypatch.setattr("app.api.panels.query_provider_task_status", fake_query_provider_task_status)

    response = await client.get(f"/api/panels/{panel.id}/lipsync/status", params={"provider_key": "mock-lipsync"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "running"
    assert data["progress_percent"] == 60

    await db_session.refresh(panel)
    assert panel.status == "processing"


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
        status="completed",
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


@pytest.mark.asyncio
async def test_apply_panel_video_should_sync_running_task_record_to_completed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜任务应用同步测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜任务应用",
        visual_prompt="apply provider result",
        status="processing",
    )
    panel.video_provider_task_id = "provider-video-task-apply-1"
    db_session.add(panel)
    await db_session.flush()
    panel_id = panel.id

    task = TaskRecord(
        task_type="video",
        target_type="panel",
        target_id=panel.id,
        project_id=project.id,
        episode_id=episode.id,
        panel_id=panel.id,
        source_task_id="provider-video-task-apply-1",
        status="running",
        progress_percent=45.0,
        message="provider running",
        error_message="stale error",
    )
    db_session.add(task)
    await db_session.commit()
    task_id = task.id

    response = await client.post(
        f"/api/panels/{panel.id}/video/apply",
        json={"result_url": "https://example.com/video-result.mp4"},
    )
    assert response.status_code == 200

    db_session.expire_all()
    updated_panel = (await db_session.execute(
        select(type(panel)).where(type(panel).id == panel_id)
    )).scalar_one()
    updated_task = (await db_session.execute(
        select(TaskRecord).where(TaskRecord.id == task_id)
    )).scalar_one()

    assert updated_panel.video_url == "https://example.com/video-result.mp4"
    assert updated_panel.status == "completed"
    assert updated_task.status == "completed"
    assert updated_task.progress_percent == 100.0
    assert updated_task.error_message is None
    assert updated_task.finished_at is not None
    assert updated_task.result_json is not None
    assert "https://example.com/video-result.mp4" in updated_task.result_json


@pytest.mark.asyncio
async def test_analyze_panel_voice_should_use_tts_text_first(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜语音分析测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜语音",
        visual_prompt="voice prompt",
        status="pending",
    )
    panel.script_text = "这是剧本文本。"
    panel.tts_text = "第一句。第二句！"
    db_session.add(panel)
    await db_session.commit()

    response = await client.post(f"/api/panels/{panel.id}/voice/analyze")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["panel_id"] == panel.id
    assert data["has_text"] is True
    assert data["text_length"] == len("第一句。第二句！")
    assert data["sentence_count"] == 2


@pytest.mark.asyncio
async def test_generate_panel_voice_lines_should_use_resolved_effective_voice_payload(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜语音生成提交测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜语音生成",
        visual_prompt="voice prompt",
        status="pending",
    )
    panel.script_text = "原始剧本文本。"
    panel.voice_id = "panel-voice-fallback"
    db_session.add(panel)
    await db_session.commit()

    captured: dict[str, object] = {}

    async def fake_submit_provider_task(db, *, provider_key: str, payload: dict):  # noqa: ANN001
        captured["provider_key"] = provider_key
        captured["payload"] = payload
        return {"task_id": "provider-tts-task-1", "status": "submitted"}

    async def fake_record_usage_cost(*args, **kwargs):  # noqa: ANN001
        return None

    async def fake_get_panel_effective_binding(panel_id: str, db, *, auto_compile: bool = True):  # noqa: ANN001
        assert panel_id == panel.id
        return {
            "effective_tts_text": "优先使用的语音台词",
            "effective_voice": {
                "voice_id": "voice-effective-1",
                "provider": "edge-tts",
                "voice_code": "zh-CN-XiaoxiaoNeural",
                "entity_id": "speaker-1",
                "role_tag": "narrator",
                "strategy": {"mood": "calm", "speed": 1.1},
            },
        }

    monkeypatch.setattr("app.api.panels.submit_provider_task", fake_submit_provider_task)
    monkeypatch.setattr("app.api.panels.record_usage_cost", fake_record_usage_cost)
    monkeypatch.setattr("app.api.panels.get_panel_effective_binding", fake_get_panel_effective_binding)

    response = await client.post(
        f"/api/panels/{panel.id}/voice/generate-lines",
        json={"provider_key": "mock-tts", "payload": {"format": "mp3"}},
    )
    assert response.status_code == 200
    assert response.json()["data"]["provider"]["task_id"] == "provider-tts-task-1"
    assert captured["provider_key"] == "mock-tts"
    assert captured["payload"] == {
        "text": "优先使用的语音台词",
        "voice_id": "voice-effective-1",
        "binding": {"mood": "calm", "speed": 1.1},
        "voice_provider": "edge-tts",
        "voice_code": "zh-CN-XiaoxiaoNeural",
        "format": "mp3",
    }

    await db_session.refresh(panel)
    assert panel.tts_provider_task_id == "provider-tts-task-1"
    assert panel.status == "pending"


@pytest.mark.asyncio
async def test_get_panel_voice_status_should_use_episode_provider_when_query_omits_provider_key(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜语音状态默认 provider 测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id, tts_provider_key="mock-tts")
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜语音状态默认 provider",
        visual_prompt="voice status prompt",
        status="completed",
        video_url="/media/videos/panel.mp4",
    )
    panel.tts_provider_task_id = "provider-tts-task-status-default-1"
    db_session.add(panel)
    await db_session.commit()

    async def fake_query_provider_task_status(db, *, provider_key: str, task_id: str):  # noqa: ANN001
        assert provider_key == "mock-tts"
        assert task_id == "provider-tts-task-status-default-1"
        return {"status": "running", "progress_percent": 55}

    monkeypatch.setattr("app.api.panels.query_provider_task_status", fake_query_provider_task_status)

    response = await client.get(f"/api/panels/{panel.id}/voice/status")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider_key"] == "mock-tts"
    assert data["status"] == "running"
    assert data["progress_percent"] == 55

    await db_session.refresh(panel)
    assert panel.tts_status == "running"
    assert panel.status == "completed"


@pytest.mark.asyncio
async def test_get_panel_voice_status_should_return_provider_status_without_mutating_panel_status(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜语音状态测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜语音状态",
        visual_prompt="voice status prompt",
        status="completed",
        video_url="/media/videos/panel.mp4",
    )
    panel.tts_provider_task_id = "provider-tts-task-status-1"
    db_session.add(panel)
    await db_session.commit()

    async def fake_query_provider_task_status(db, *, provider_key: str, task_id: str):  # noqa: ANN001
        assert provider_key == "mock-tts"
        assert task_id == "provider-tts-task-status-1"
        return {"status": "running", "progress_percent": 55}

    monkeypatch.setattr("app.api.panels.query_provider_task_status", fake_query_provider_task_status)

    response = await client.get(f"/api/panels/{panel.id}/voice/status", params={"provider_key": "mock-tts"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "running"
    assert data["progress_percent"] == 55

    await db_session.refresh(panel)
    assert panel.status == "completed"


@pytest.mark.asyncio
async def test_apply_panel_voice_should_update_audio_field_without_mutating_panel_status(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜语音应用测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜语音应用",
        visual_prompt="voice apply prompt",
        status="completed",
        video_url="/media/videos/original.mp4",
    )
    panel.tts_provider_task_id = "provider-tts-task-apply-1"
    db_session.add(panel)
    await db_session.flush()
    panel_id = panel.id

    task = TaskRecord(
        task_type="tts",
        target_type="panel",
        target_id=panel.id,
        project_id=project.id,
        episode_id=episode.id,
        panel_id=panel.id,
        source_task_id="provider-tts-task-apply-1",
        status="running",
        progress_percent=35.0,
        message="tts provider running",
    )
    db_session.add(task)
    await db_session.commit()
    task_id = task.id

    response = await client.post(
        f"/api/panels/{panel.id}/voice/apply",
        json={"result_url": "https://example.com/voice-result.mp3"},
    )
    assert response.status_code == 200

    db_session.expire_all()
    updated_panel = (await db_session.execute(
        select(type(panel)).where(type(panel).id == panel_id)
    )).scalar_one()
    updated_task = (await db_session.execute(
        select(TaskRecord).where(TaskRecord.id == task_id)
    )).scalar_one()

    assert updated_panel.tts_audio_url == "https://example.com/voice-result.mp3"
    assert updated_panel.status == "completed"
    assert updated_task.status == "completed"
    assert updated_task.result_json is not None
    assert "https://example.com/voice-result.mp3" in updated_task.result_json


@pytest.mark.asyncio
async def test_submit_panel_lipsync_should_not_override_existing_video_provider_task_id(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜 provider 任务隔离测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜任务隔离",
        visual_prompt="task isolation",
        status="completed",
        video_url="/media/videos/panel.mp4",
    )
    panel.tts_audio_url = "/media/audio/panel.mp3"
    panel.video_provider_task_id = "existing-video-task"
    db_session.add(panel)
    await db_session.commit()

    async def fake_submit_provider_task(db, *, provider_key: str, payload: dict):  # noqa: ANN001
        return {"task_id": f"{provider_key}-task-1", "status": "submitted"}

    async def fake_record_usage_cost(*args, **kwargs):  # noqa: ANN001
        return None

    monkeypatch.setattr("app.api.panels.submit_provider_task", fake_submit_provider_task)
    monkeypatch.setattr("app.api.panels.record_usage_cost", fake_record_usage_cost)

    response = await client.post(
        f"/api/panels/{panel.id}/lipsync/submit",
        json={"provider_key": "mock-lipsync", "payload": {"fps": 25}},
    )
    assert response.status_code == 200

    await db_session.refresh(panel)
    assert panel.video_provider_task_id == "existing-video-task"
    assert panel.lipsync_provider_task_id == "mock-lipsync-task-1"
    assert panel.lipsync_status == "queued"
    assert panel.status == "processing"


@pytest.mark.asyncio
async def test_apply_panel_video_should_reject_blank_result_url(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜结果地址校验测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜结果地址校验",
        visual_prompt="result url check",
        status="processing",
    )
    db_session.add(panel)
    await db_session.commit()

    response = await client.post(
        f"/api/panels/{panel.id}/video/apply",
        json={"result_url": "   "},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "result_url 不能为空"


@pytest.mark.asyncio
async def test_panel_provider_status_endpoints_should_use_task_type_specific_task_ids(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜 provider 状态隔离测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜状态隔离",
        visual_prompt="status isolation",
        status="processing",
    )
    panel.video_provider_task_id = "video-task-001"
    panel.lipsync_provider_task_id = "lipsync-task-001"
    db_session.add(panel)
    await db_session.commit()

    calls: list[tuple[str, str]] = []

    async def fake_query_provider_task_status(db, *, provider_key: str, task_id: str):  # noqa: ANN001
        calls.append((provider_key, task_id))
        if provider_key == "mock-video":
            return {"status": "running", "progress_percent": 30}
        return {"status": "running", "progress_percent": 60}

    monkeypatch.setattr("app.api.panels.query_provider_task_status", fake_query_provider_task_status)

    video_resp = await client.get(
        f"/api/panels/{panel.id}/video/status",
        params={"provider_key": "mock-video"},
    )
    lipsync_resp = await client.get(
        f"/api/panels/{panel.id}/lipsync/status",
        params={"provider_key": "mock-lipsync"},
    )
    assert video_resp.status_code == 200
    assert lipsync_resp.status_code == 200
    assert calls == [
        ("mock-video", "video-task-001"),
        ("mock-lipsync", "lipsync-task-001"),
    ]


@pytest.mark.asyncio
async def test_submit_panel_video_should_clear_stale_outputs_before_resubmit(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜视频重提清理测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜视频重提",
        visual_prompt="retry prompt",
        status="completed",
        video_url="/media/videos/old-video.mp4",
    )
    panel.lipsync_video_url = "/media/videos/old-lipsync.mp4"
    panel.lipsync_provider_task_id = "old-lipsync-task"
    panel.video_provider_task_id = "old-video-task"
    panel.error_message = "old error"
    db_session.add(panel)
    await db_session.commit()

    async def fake_submit_provider_task(db, *, provider_key: str, payload: dict):  # noqa: ANN001
        return {"task_id": "provider-video-task-new", "status": "submitted"}

    async def fake_record_usage_cost(*args, **kwargs):  # noqa: ANN001
        return None

    monkeypatch.setattr("app.api.panels.submit_provider_task", fake_submit_provider_task)
    monkeypatch.setattr("app.api.panels.record_usage_cost", fake_record_usage_cost)

    response = await client.post(
        f"/api/panels/{panel.id}/video/submit",
        json={"provider_key": "mock-video", "payload": {"seed": 7}},
    )
    assert response.status_code == 200

    await db_session.refresh(panel)
    assert panel.video_provider_task_id == "provider-video-task-new"
    assert panel.video_url is None
    assert panel.lipsync_video_url is None
    assert panel.lipsync_provider_task_id is None
    assert panel.status == "processing"
    assert panel.error_message is None


@pytest.mark.asyncio
async def test_generate_panel_voice_lines_should_clear_stale_voice_outputs_before_resubmit(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    project = Project(name="分镜语音重提清理测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜语音重提",
        visual_prompt="voice retry prompt",
        status="completed",
        video_url="/media/videos/original.mp4",
    )
    panel.script_text = "需要重新生成语音的文案。"
    panel.tts_audio_url = "/media/audio/old-audio.mp3"
    panel.lipsync_video_url = "/media/videos/old-lipsync.mp4"
    panel.lipsync_provider_task_id = "old-lipsync-task"
    db_session.add(panel)
    await db_session.commit()

    async def fake_submit_provider_task(db, *, provider_key: str, payload: dict):  # noqa: ANN001
        return {"task_id": "provider-tts-task-new", "status": "submitted"}

    async def fake_record_usage_cost(*args, **kwargs):  # noqa: ANN001
        return None

    async def fake_get_panel_effective_binding(panel_id: str, db, *, auto_compile: bool = True):  # noqa: ANN001
        assert panel_id == panel.id
        return {
            "effective_tts_text": "新的语音文本",
            "effective_voice": {
                "voice_id": "voice-effective-1",
                "provider": "edge-tts",
                "voice_code": "zh-CN-XiaoxiaoNeural",
                "strategy": {"speed": 1.0},
            },
        }

    monkeypatch.setattr("app.api.panels.submit_provider_task", fake_submit_provider_task)
    monkeypatch.setattr("app.api.panels.record_usage_cost", fake_record_usage_cost)
    monkeypatch.setattr("app.api.panels.get_panel_effective_binding", fake_get_panel_effective_binding)

    response = await client.post(
        f"/api/panels/{panel.id}/voice/generate-lines",
        json={"provider_key": "mock-tts", "payload": {}},
    )
    assert response.status_code == 200

    await db_session.refresh(panel)
    assert panel.tts_provider_task_id == "provider-tts-task-new"
    assert panel.tts_audio_url is None
    assert panel.lipsync_video_url is None
    assert panel.lipsync_provider_task_id is None
    assert panel.status == "completed"
