from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.system as system_api
import app.services.runtime_settings as runtime_settings_service
from app.config import settings
from app.models import CompositionTask, Episode, Panel, Project, Scene, VideoClip


@pytest.mark.asyncio
async def test_system_runtime_endpoint_should_return_runtime_summary(client: AsyncClient):
    response = await client.get("/api/system/runtime")

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert isinstance(payload["data"], dict)
    assert payload["data"]["app"]["name"] == "AbiWorkflow"
    assert isinstance(payload["data"]["app"]["debug"], bool)
    assert "database_url" in payload["data"]["app"]
    assert payload["data"]["llm"]["model"] == settings.llm_model
    assert isinstance(payload["data"]["llm"]["api_key_configured"], bool)
    assert "queue" in payload["data"]
    assert isinstance(payload["data"]["queue"]["celery_worker_online"], bool)
    assert payload["data"]["queue"]["queue_mode"] in {"redis", "sqlite"}
    assert isinstance(payload["data"]["queue"]["fallback_active"], bool)
    assert "video" in payload["data"]
    assert payload["data"]["video"]["provider"] == settings.video_provider
    assert isinstance(payload["data"]["video"]["project_asset_publish_global_default"], bool)
    assert "http_provider" in payload["data"]["video"]
    assert "ggk_provider" in payload["data"]["video"]
    assert "model_duration_profiles" in payload["data"]["video"]["ggk_provider"]
    assert "models" in payload["data"]
    assert isinstance(payload["data"]["models"]["default_bindings"], dict)
    assert isinstance(payload["data"]["models"]["capability_profiles"], dict)


@pytest.mark.asyncio
async def test_system_runtime_endpoint_should_update_settings(
    client: AsyncClient,
    tmp_path,
    monkeypatch,
):
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_MODEL=gpt-4o\nVIDEO_PROVIDER=mock\n", encoding="utf-8")
    monkeypatch.setattr(runtime_settings_service, "_resolve_env_file_path", lambda: env_file)

    response = await client.put("/api/system/runtime", json={
        "llm_model": "gpt-4o-mini",
        "video_provider": "http",
        "video_http_base_url": "https://example.com",
        "debug": True,
        "project_asset_publish_global_default": True,
    })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["llm"]["model"] == "gpt-4o-mini"
    assert data["video"]["provider"] == "http"
    assert data["app"]["debug"] is True
    assert data["video"]["http_provider"]["base_url"] == "https://example.com"
    assert data["video"]["project_asset_publish_global_default"] is True

    content = env_file.read_text(encoding="utf-8")
    assert "LLM_MODEL=gpt-4o-mini" in content
    assert "VIDEO_PROVIDER=http" in content
    assert "PROJECT_ASSET_PUBLISH_GLOBAL_DEFAULT=true" in content


@pytest.mark.asyncio
async def test_system_runtime_endpoint_should_reject_invalid_duration_profiles_json(
    client: AsyncClient,
):
    response = await client.put("/api/system/runtime", json={
        "ggk_video_model_duration_profiles": "{invalid-json}",
    })

    assert response.status_code == 400
    assert "ggk_video_model_duration_profiles 配置非法" in response.json()["detail"]


@pytest.mark.asyncio
async def test_project_assets_endpoint_should_return_assets_payload(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="资产测试项目", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(project_id=project.id, episode_order=0, title="第1集", status="draft")
    db_session.add(episode)
    await db_session.flush()

    panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="开场",
        status="completed",
        duration_seconds=5.0,
    )
    db_session.add(panel)

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="开场",
        status="completed",
        duration_seconds=5.0,
    )
    db_session.add(scene)
    await db_session.flush()

    clip = VideoClip(
        scene_id=scene.id,
        clip_order=0,
        status="completed",
        duration_seconds=5.0,
        provider_task_id="provider-task-001",
        file_path="./outputs/videos/demo-clip.mp4",
    )
    db_session.add(clip)

    composition = CompositionTask(
        project_id=project.id,
        status="completed",
        duration_seconds=5.0,
        output_path="./outputs/compositions/demo-composition.mp4",
        transition_type="cut",
        include_subtitles=False,
        include_tts=True,
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.get(f"/api/projects/{project.id}/assets")
    assert response.status_code == 200

    payload = response.json()["data"]
    assert payload["project_id"] == project.id
    assert payload["project_name"] == "资产测试项目"
    assert payload["summary"]["panel_count"] == 1
    assert payload["summary"]["clip_count"] == 1
    assert payload["summary"]["ready_clip_count"] == 1
    assert payload["summary"]["failed_clip_count"] == 0
    assert payload["summary"]["composition_count"] == 1

    assert len(payload["panels"]) == 1
    assert payload["panels"][0]["title"] == "开场"
    assert payload["panels"][0]["clips"][0]["media_url"] == "/media/videos/demo-clip.mp4"
    assert payload["panels"][0]["clips"][0]["provider_task_id"] == "provider-task-001"

    assert len(payload["compositions"]) == 1
    assert payload["compositions"][0]["media_url"] == "/media/compositions/demo-composition.mp4"
    assert payload["compositions"][0]["download_url"] == f"/api/compositions/{composition.id}/download"


@pytest.mark.asyncio
async def test_project_assets_should_not_attach_scene_clips_when_mapping_count_mismatched(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="资产错绑保护测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(project_id=project.id, episode_order=0, title="第1集", status="draft")
    db_session.add(episode)
    await db_session.flush()

    panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="唯一分镜",
        status="completed",
        duration_seconds=5.0,
    )
    db_session.add(panel)
    await db_session.flush()

    stray_scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="历史残留场景",
        status="completed",
        duration_seconds=5.0,
    )
    mapped_scene = Scene(
        project_id=project.id,
        sequence_order=1,
        title="真实分镜场景",
        status="completed",
        duration_seconds=5.0,
    )
    db_session.add_all([stray_scene, mapped_scene])
    await db_session.flush()

    db_session.add_all([
        VideoClip(
            scene_id=stray_scene.id,
            clip_order=0,
            status="completed",
            duration_seconds=5.0,
            provider_task_id="stray-clip",
            file_path="./outputs/videos/stray.mp4",
        ),
        VideoClip(
            scene_id=mapped_scene.id,
            clip_order=0,
            status="completed",
            duration_seconds=5.0,
            provider_task_id="real-clip",
            file_path="./outputs/videos/real.mp4",
        ),
    ])
    await db_session.commit()

    response = await client.get(f"/api/projects/{project.id}/assets")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["summary"]["clip_count"] == 0
    assert payload["summary"]["ready_clip_count"] == 0
    assert payload["panels"][0]["clips"] == []


@pytest.mark.asyncio
async def test_project_assets_endpoint_should_return_404_when_project_not_found(client: AsyncClient):
    response = await client.get("/api/projects/non-existent-project/assets")

    assert response.status_code == 404
    assert response.json()["detail"] == "项目不存在"


@pytest.mark.asyncio
async def test_project_assets_summary_should_only_count_completed_compositions(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="资产计数测试项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="测试场景",
        status="generated",
        duration_seconds=5.0,
    )
    db_session.add(scene)
    await db_session.flush()

    db_session.add_all([
        CompositionTask(
            project_id=project.id,
            status="completed",
            duration_seconds=5.0,
            output_path="./outputs/compositions/current.mp4",
            transition_type="cut",
            include_subtitles=False,
            include_tts=False,
        ),
        CompositionTask(
            project_id=project.id,
            status="stale",
            duration_seconds=5.0,
            output_path="./outputs/compositions/old.mp4",
            transition_type="cut",
            include_subtitles=False,
            include_tts=False,
        ),
    ])
    await db_session.commit()

    response = await client.get(f"/api/projects/{project.id}/assets")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["summary"]["composition_count"] == 1
    assert len(payload["compositions"]) == 2


@pytest.mark.asyncio
async def test_download_composition_should_resolve_relative_path_with_stable_base_dir(
    client: AsyncClient,
    db_session: AsyncSession,
    tmp_path,
    monkeypatch,
):
    # 模拟“进程 cwd 与 backend 根目录不一致”的运行场景。
    project = Project(name="下载路径解析测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    relative_name = f"{uuid.uuid4()}.mp4"
    relative_output = f"./outputs/compositions/{relative_name}"
    task = CompositionTask(
        project_id=project.id,
        status="completed",
        duration_seconds=5.0,
        output_path=relative_output,
        transition_type="cut",
        include_subtitles=False,
        include_tts=False,
    )
    db_session.add(task)
    await db_session.commit()

    backend_root = Path(system_api.__file__).resolve().parents[2]
    actual_file = backend_root / "outputs" / "compositions" / relative_name
    actual_file.parent.mkdir(parents=True, exist_ok=True)
    actual_file.write_bytes(b"fake-composition-bytes")

    try:
        monkeypatch.chdir(tmp_path)

        response = await client.get(f"/api/compositions/{task.id}/download")
        assert response.status_code == 200
        assert response.headers.get("content-type") == "video/mp4"
    finally:
        if actual_file.exists():
            actual_file.unlink()
