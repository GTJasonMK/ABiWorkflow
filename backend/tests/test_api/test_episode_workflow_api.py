from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Episode, Panel, Project, ProviderConfig


async def _seed_provider_configs(db_session: AsyncSession) -> None:
    db_session.add_all([
        ProviderConfig(
            provider_key="mock-video",
            provider_type="video",
            name="Mock Video",
            base_url="https://video.example.test",
            request_template_json='{"_allowed_video_lengths":[6,10,15]}',
        ),
        ProviderConfig(
            provider_key="mock-tts",
            provider_type="tts",
            name="Mock TTS",
            base_url="https://tts.example.test",
        ),
        ProviderConfig(
            provider_key="mock-lipsync",
            provider_type="lipsync",
            name="Mock Lipsync",
            base_url="https://lipsync.example.test",
        ),
    ])
    await db_session.commit()


@pytest.mark.asyncio
async def test_get_episode_should_include_provider_fields_and_workflow_summary(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分集工作流摘要测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(
        project_id=project.id,
        episode_order=0,
        title="第1集",
        script_text="这一集的正文已经写好。",
        video_provider_key="mock-video",
        tts_provider_key="mock-tts",
        lipsync_provider_key="mock-lipsync",
    )
    db_session.add(episode)
    await db_session.flush()

    panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="分镜 1",
        visual_prompt="cinematic frame",
        duration_seconds=5.0,
        status="completed",
        video_url="/media/videos/panel-1.mp4",
        tts_audio_url="/media/audio/panel-1.mp3",
        video_status="succeeded",
        tts_status="succeeded",
        lipsync_status="idle",
    )
    db_session.add(panel)
    await db_session.commit()

    response = await client.get(f"/api/episodes/{episode.id}")
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["video_provider_key"] == "mock-video"
    assert data["tts_provider_key"] == "mock-tts"
    assert data["lipsync_provider_key"] == "mock-lipsync"
    assert data["provider_payload_defaults"] == {
        "video": {},
        "tts": {},
        "lipsync": {},
    }
    assert data["workflow_summary"]["current_step"] == "assets"
    assert data["workflow_summary"]["checks"]["script_ready"] is True
    assert data["workflow_summary"]["checks"]["providers_ready"] is True
    assert data["workflow_summary"]["checks"]["panels_ready"] is True
    assert data["workflow_summary"]["checks"]["video_ready"] is True
    assert data["workflow_summary"]["counts"]["panel_total"] == 1
    assert data["workflow_summary"]["counts"]["panel_video_done"] == 1


@pytest.mark.asyncio
async def test_list_episodes_should_build_workflow_summaries_in_batch(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="批量分集摘要测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    first_episode = Episode(
        project_id=project.id,
        episode_order=0,
        title="第1集",
        script_text="第一集正文已经准备完毕。",
        video_provider_key="mock-video",
    )
    second_episode = Episode(
        project_id=project.id,
        episode_order=1,
        title="第2集",
        script_text=None,
        video_provider_key=None,
    )
    db_session.add_all([first_episode, second_episode])
    await db_session.flush()

    db_session.add(Panel(
        project_id=project.id,
        episode_id=first_episode.id,
        panel_order=0,
        title="分镜 1",
        status="completed",
        video_url="/media/videos/panel-1.mp4",
        tts_audio_url="/media/audio/panel-1.mp3",
        video_status="succeeded",
        tts_status="succeeded",
    ))
    await db_session.commit()

    response = await client.get(f"/api/projects/{project.id}/episodes")
    assert response.status_code == 200

    rows = response.json()["data"]
    assert len(rows) == 2

    first_payload = next(item for item in rows if item["id"] == first_episode.id)
    second_payload = next(item for item in rows if item["id"] == second_episode.id)

    assert first_payload["workflow_summary"]["current_step"] == "assets"
    assert first_payload["workflow_summary"]["counts"]["panel_total"] == 1
    assert "缺少角色绑定" in first_payload["workflow_summary"]["blockers"]
    assert "缺少地点绑定" in first_payload["workflow_summary"]["blockers"]

    assert second_payload["workflow_summary"]["current_step"] == "script"
    assert second_payload["workflow_summary"]["checks"]["script_ready"] is False
    assert second_payload["workflow_summary"]["checks"]["providers_ready"] is False


@pytest.mark.asyncio
async def test_create_episode_should_inherit_project_workflow_defaults(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _seed_provider_configs(db_session)

    project_resp = await client.post(
        "/api/projects",
        json={
            "name": "分集默认配置继承测试",
            "workflow_defaults": {
                "video_provider_key": "mock-video",
                "tts_provider_key": "mock-tts",
                "lipsync_provider_key": "mock-lipsync",
                "provider_payload_defaults": {
                    "video": {"seed": 7},
                    "tts": {"voice": "narrator"},
                },
            },
        },
    )
    project_id = project_resp.json()["data"]["id"]

    response = await client.post(
        f"/api/projects/{project_id}/episodes",
        json={
            "title": "第1集",
            "script_text": "这是正文",
            "provider_payload_defaults": {
                "video": {"seed": 42},
                "lipsync": {"fps": 25},
            },
            "skipped_checks": ["voice_ready", "voice_ready", "", "video_ready"],
        },
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["video_provider_key"] == "mock-video"
    assert data["tts_provider_key"] == "mock-tts"
    assert data["lipsync_provider_key"] == "mock-lipsync"
    assert data["provider_payload_defaults"] == {
        "video": {"seed": 42},
        "tts": {"voice": "narrator"},
        "lipsync": {"fps": 25},
    }
    assert data["skipped_checks"] == ["voice_ready", "video_ready"]


@pytest.mark.asyncio
async def test_update_episode_should_apply_explicit_workflow_config_changes(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _seed_provider_configs(db_session)

    project = Project(name="分集更新配置测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(
        project_id=project.id,
        episode_order=0,
        title="第1集",
        script_text="旧正文",
        video_provider_key="mock-video",
        provider_payload_defaults_json='{"video":{"seed":1},"tts":{},"lipsync":{}}',
        skipped_checks_json='["script_ready"]',
    )
    db_session.add(episode)
    await db_session.commit()

    response = await client.put(
        f"/api/episodes/{episode.id}",
        json={
            "tts_provider_key": "mock-tts",
            "lipsync_provider_key": None,
            "provider_payload_defaults": {
                "tts": {"voice": "host"},
            },
            "skipped_checks": ["panels_ready", "panels_ready", "video_ready"],
        },
    )
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["video_provider_key"] == "mock-video"
    assert data["tts_provider_key"] == "mock-tts"
    assert data["lipsync_provider_key"] is None
    assert data["provider_payload_defaults"] == {
        "video": {},
        "tts": {"voice": "host"},
        "lipsync": {},
    }
    assert data["skipped_checks"] == ["panels_ready", "video_ready"]
