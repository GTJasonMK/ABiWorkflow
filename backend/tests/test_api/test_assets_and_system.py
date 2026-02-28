from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.api.system as system_api
import app.services.runtime_settings as runtime_settings_service
from app.config import settings
from app.models import CompositionTask, Project, Scene, VideoClip


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
    assert payload["data"]["llm"]["provider"] in {"openai", "anthropic", "deepseek", "ggk"}
    assert isinstance(payload["data"]["llm"]["any_key_configured"], bool)
    assert "openai" in payload["data"]["llm"]
    assert "anthropic" in payload["data"]["llm"]
    assert "deepseek" in payload["data"]["llm"]
    assert "ggk" in payload["data"]["llm"]
    assert "queue" in payload["data"]
    assert isinstance(payload["data"]["queue"]["celery_worker_online"], bool)
    assert "video" in payload["data"]
    assert payload["data"]["video"]["provider"] == settings.video_provider
    assert "http_provider" in payload["data"]["video"]
    assert "ggk_provider" in payload["data"]["video"]
    assert "model_duration_profiles" in payload["data"]["video"]["ggk_provider"]


@pytest.mark.asyncio
async def test_system_runtime_endpoint_should_update_settings(
    client: AsyncClient,
    tmp_path,
    monkeypatch,
):
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=openai\nVIDEO_PROVIDER=mock\n", encoding="utf-8")
    monkeypatch.setattr(runtime_settings_service, "_resolve_env_file_path", lambda: env_file)

    response = await client.put("/api/system/runtime", json={
        "llm_provider": "deepseek",
        "deepseek_model": "deepseek-chat-v2",
        "video_provider": "http",
        "video_http_base_url": "https://example.com",
        "debug": True,
    })

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["llm"]["provider"] == "deepseek"
    assert data["llm"]["active_model"] == "deepseek-chat-v2"
    assert data["video"]["provider"] == "http"
    assert data["app"]["debug"] is True
    assert data["video"]["http_provider"]["base_url"] == "https://example.com"

    content = env_file.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=deepseek" in content
    assert "DEEPSEEK_MODEL=deepseek-chat-v2" in content
    assert "VIDEO_PROVIDER=http" in content


@pytest.mark.asyncio
async def test_system_runtime_endpoint_should_reject_invalid_duration_profiles_json(
    client: AsyncClient,
):
    response = await client.put("/api/system/runtime", json={
        "ggk_video_model_duration_profiles": "{invalid-json}",
    })

    assert response.status_code == 400
    assert "ggk_video_model_duration_profiles 配置非法" in response.json()["detail"]


def _build_fake_ggk_project(project_dir, *, api_key: str, internal_key: str) -> None:
    data_dir = project_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "data.db"

    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL UNIQUE,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at REAL,
                updated_at REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kv_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO api_keys (key, is_active, created_at, updated_at) VALUES (?, 1, 1, 1)",
            (api_key,),
        )
        conn.execute(
            """
            INSERT INTO kv_settings (key, value, updated_at)
            VALUES ('settings', ?, '2026-01-01 00:00:00')
            """,
            (json.dumps({"internal_api_key": internal_key}, ensure_ascii=False),),
        )
        conn.commit()

    (project_dir / "main.py").write_text("# fake ggk project\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_system_ggk_import_endpoint_should_import_from_local_project(
    client: AsyncClient,
    tmp_path,
    monkeypatch,
):
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_PROVIDER=openai\nVIDEO_PROVIDER=mock\n", encoding="utf-8")
    monkeypatch.setattr(runtime_settings_service, "_resolve_env_file_path", lambda: env_file)

    fake_ggk_dir = tmp_path / "GGK"
    _build_fake_ggk_project(
        fake_ggk_dir,
        api_key="sk-ggk-from-api-keys",
        internal_key="sk-ggk-internal",
    )

    snapshot = {
        "llm_provider": settings.llm_provider,
        "video_provider": settings.video_provider,
        "ggk_base_url": settings.ggk_base_url,
        "ggk_api_key": settings.ggk_api_key,
    }

    try:
        response = await client.post("/api/system/ggk/import", json={
            "project_path": str(fake_ggk_dir),
            "auto_switch_provider": True,
        })

        assert response.status_code == 200
        payload = response.json()["data"]
        assert payload["imported"] is True
        assert payload["source"]["api_key_source"] == "api_keys"
        assert payload["runtime"]["llm"]["provider"] == "ggk"
        assert payload["runtime"]["video"]["provider"] == "ggk"
        assert payload["runtime"]["llm"]["ggk"]["api_key_configured"] is True

        content = env_file.read_text(encoding="utf-8")
        assert "LLM_PROVIDER=ggk" in content
        assert "VIDEO_PROVIDER=ggk" in content
        assert "GGK_API_KEY=sk-ggk-from-api-keys" in content
        assert "GGK_BASE_URL=http://127.0.0.1:8000/v1" in content
    finally:
        for field_name, value in snapshot.items():
            setattr(settings, field_name, value)


@pytest.mark.asyncio
async def test_project_assets_endpoint_should_return_assets_payload(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="资产测试项目", status="completed")
    db_session.add(project)
    await db_session.flush()

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
    assert payload["summary"]["scene_count"] == 1
    assert payload["summary"]["clip_count"] == 1
    assert payload["summary"]["ready_clip_count"] == 1
    assert payload["summary"]["failed_clip_count"] == 0
    assert payload["summary"]["composition_count"] == 1

    assert len(payload["scenes"]) == 1
    assert payload["scenes"][0]["title"] == "开场"
    assert payload["scenes"][0]["clips"][0]["media_url"] == "/media/videos/demo-clip.mp4"
    assert payload["scenes"][0]["clips"][0]["provider_task_id"] == "provider-task-001"

    assert len(payload["compositions"]) == 1
    assert payload["compositions"][0]["media_url"] == "/media/compositions/demo-composition.mp4"
    assert payload["compositions"][0]["download_url"] == f"/api/compositions/{composition.id}/download"


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
