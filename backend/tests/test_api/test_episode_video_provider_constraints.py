from __future__ import annotations

import json

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProviderConfig


async def _seed_video_provider(db_session: AsyncSession, *, provider_key: str = "video.ggk") -> None:
    db_session.add(ProviderConfig(
        provider_key=provider_key,
        provider_type="video",
        name="测试视频 Provider",
        base_url="https://example.com/v1",
        submit_path="/chat/completions",
        status_path="/chat/completions",
        result_path="",
        auth_scheme="bearer",
        api_key="sk-test",
        api_key_header="Authorization",
        extra_headers_json=json.dumps({}),
        request_template_json=json.dumps({
            "model": "grok-video",
            "stream": True,
            "_allowed_video_lengths": [6, 10, 15],
            "video_config": {"aspect_ratio": "16:9"},
        }),
        response_mapping_json=json.dumps({"task_id_path": "id"}),
        status_mapping_json=json.dumps({}),
        timeout_seconds=30.0,
        enabled=True,
    ))
    await db_session.commit()


@pytest.mark.asyncio
async def test_create_panel_should_default_duration_to_allowed_lengths_first_value(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _seed_video_provider(db_session)

    project = await client.post("/api/projects", json={"name": "时长约束项目"})
    project_id = project.json()["data"]["id"]

    episode = await client.post(
        f"/api/projects/{project_id}/episodes",
        json={"title": "第1集", "script_text": "测试剧本", "video_provider_key": "video.ggk"},
    )
    assert episode.status_code == 200
    episode_id = episode.json()["data"]["id"]

    panel = await client.post(f"/api/episodes/{episode_id}/panels", json={"title": "分镜一"})
    assert panel.status_code == 200
    assert panel.json()["data"]["duration_seconds"] == 6.0


@pytest.mark.asyncio
async def test_create_panel_should_reject_invalid_duration_seconds_when_episode_has_provider(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _seed_video_provider(db_session)

    project = await client.post("/api/projects", json={"name": "时长约束项目"})
    project_id = project.json()["data"]["id"]

    episode = await client.post(
        f"/api/projects/{project_id}/episodes",
        json={"title": "第1集", "script_text": "测试剧本", "video_provider_key": "video.ggk"},
    )
    episode_id = episode.json()["data"]["id"]

    panel = await client.post(
        f"/api/episodes/{episode_id}/panels",
        json={"title": "分镜一", "duration_seconds": 5},
    )
    assert panel.status_code == 400
    assert "分镜时长必须为" in panel.json()["detail"]


@pytest.mark.asyncio
async def test_update_panel_should_reject_invalid_duration_seconds_when_episode_has_provider(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _seed_video_provider(db_session)

    project = await client.post("/api/projects", json={"name": "时长约束项目"})
    project_id = project.json()["data"]["id"]

    episode = await client.post(
        f"/api/projects/{project_id}/episodes",
        json={"title": "第1集", "script_text": "测试剧本", "video_provider_key": "video.ggk"},
    )
    episode_id = episode.json()["data"]["id"]

    panel = await client.post(
        f"/api/episodes/{episode_id}/panels",
        json={"title": "分镜一", "duration_seconds": 6},
    )
    panel_id = panel.json()["data"]["id"]

    ok = await client.put(f"/api/panels/{panel_id}", json={"duration_seconds": 10})
    assert ok.status_code == 200
    assert ok.json()["data"]["duration_seconds"] == 10.0

    bad = await client.put(f"/api/panels/{panel_id}", json={"duration_seconds": 5})
    assert bad.status_code == 400
    assert "分镜时长必须为" in bad.json()["detail"]


@pytest.mark.asyncio
async def test_generate_panels_should_require_episode_video_provider_key(
    client: AsyncClient,
):
    project = await client.post("/api/projects", json={"name": "分集生成测试"})
    project_id = project.json()["data"]["id"]

    episode = await client.post(
        f"/api/projects/{project_id}/episodes",
        json={"title": "第1集", "script_text": "测试剧本"},
    )
    episode_id = episode.json()["data"]["id"]

    resp = await client.post(f"/api/episodes/{episode_id}/panels/generate", json={"overwrite": True})
    assert resp.status_code == 400
    assert "未配置视频 Provider" in resp.json()["detail"]

