from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import asset_hub as asset_hub_api
from app.models import Project


@pytest.mark.asyncio
async def test_delete_folder_should_clear_all_asset_folder_bindings(client: AsyncClient):
    folder_resp = await client.post("/api/asset-hub/folders", json={"name": "测试目录", "folder_type": "generic"})
    assert folder_resp.status_code == 200
    folder_id = folder_resp.json()["data"]["id"]

    voice_resp = await client.post("/api/asset-hub/voices", json={
        "name": "测试语音A",
        "provider": "edge-tts",
        "voice_code": "zh-CN-XiaoxiaoNeural",
        "folder_id": folder_id,
    })
    assert voice_resp.status_code == 200
    voice_id = voice_resp.json()["data"]["id"]

    character_resp = await client.post("/api/asset-hub/characters", json={
        "name": "测试角色A",
        "folder_id": folder_id,
        "default_voice_id": voice_id,
        "description": "用于目录绑定回收测试",
    })
    assert character_resp.status_code == 200
    character_id = character_resp.json()["data"]["id"]

    location_resp = await client.post("/api/asset-hub/locations", json={
        "name": "测试地点A",
        "folder_id": folder_id,
        "description": "用于目录绑定回收测试",
    })
    assert location_resp.status_code == 200
    location_id = location_resp.json()["data"]["id"]

    delete_resp = await client.delete(f"/api/asset-hub/folders/{folder_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True

    overview_resp = await client.get("/api/asset-hub/overview")
    assert overview_resp.status_code == 200
    overview = overview_resp.json()["data"]

    folder_ids = {item["id"] for item in overview["folders"]}
    assert folder_id not in folder_ids

    voice_map = {item["id"]: item for item in overview["voices"]}
    character_map = {item["id"]: item for item in overview["characters"]}
    location_map = {item["id"]: item for item in overview["locations"]}

    assert voice_map[voice_id]["folder_id"] is None
    assert character_map[character_id]["folder_id"] is None
    assert location_map[location_id]["folder_id"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "payload"),
    [
        (
            "/api/asset-hub/voices",
            {
                "name": "测试语音-非法目录",
                "provider": "edge-tts",
                "voice_code": "zh-CN-XiaoxiaoNeural",
                "folder_id": "not-exists-folder-id",
            },
        ),
        (
            "/api/asset-hub/characters",
            {
                "name": "测试角色-非法目录",
                "folder_id": "not-exists-folder-id",
            },
        ),
        (
            "/api/asset-hub/locations",
            {
                "name": "测试地点-非法目录",
                "folder_id": "not-exists-folder-id",
            },
        ),
    ],
)
async def test_create_asset_should_reject_unknown_folder_id(
    client: AsyncClient,
    endpoint: str,
    payload: dict[str, str],
):
    response = await client.post(endpoint, json=payload)
    assert response.status_code == 400
    assert response.json()["detail"] == "关联资产目录不存在"


@pytest.mark.asyncio
async def test_asset_hub_should_support_project_scoped_assets(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="资产作用域测试项目", status="draft")
    project_other = Project(name="资产作用域测试项目-其他", status="draft")
    db_session.add(project)
    db_session.add(project_other)
    await db_session.commit()

    create_resp = await client.post("/api/asset-hub/characters", json={
        "name": "项目角色A",
        "project_id": project.id,
        "description": "仅当前项目可见",
    })
    assert create_resp.status_code == 200
    character_id = create_resp.json()["data"]["id"]
    assert create_resp.json()["data"]["project_id"] == project.id

    other_project_resp = await client.post("/api/asset-hub/characters", json={
        "name": "项目角色B",
        "project_id": project_other.id,
        "description": "其他项目角色",
    })
    assert other_project_resp.status_code == 200
    other_character_id = other_project_resp.json()["data"]["id"]

    global_character_resp = await client.post("/api/asset-hub/characters", json={
        "name": "全局角色C",
        "description": "全局角色",
    })
    assert global_character_resp.status_code == 200
    global_character_id = global_character_resp.json()["data"]["id"]

    scoped_resp = await client.get(f"/api/asset-hub/overview?scope=project&project_id={project.id}")
    assert scoped_resp.status_code == 200
    scoped_characters = scoped_resp.json()["data"]["characters"]
    assert any(item["id"] == character_id for item in scoped_characters)

    global_resp = await client.get("/api/asset-hub/overview?scope=global")
    assert global_resp.status_code == 200
    global_characters = global_resp.json()["data"]["characters"]
    assert all(item["id"] != character_id for item in global_characters)

    mixed_resp = await client.get(f"/api/asset-hub/overview?scope=all&project_id={project.id}")
    assert mixed_resp.status_code == 200
    mixed_ids = {item["id"] for item in mixed_resp.json()["data"]["characters"]}
    assert character_id in mixed_ids
    assert global_character_id in mixed_ids
    assert other_character_id not in mixed_ids


@pytest.mark.asyncio
async def test_asset_hub_should_reject_unknown_project_id(client: AsyncClient):
    response = await client.post("/api/asset-hub/locations", json={
        "name": "非法项目地点",
        "project_id": "not-exists-project",
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "关联项目不存在"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_type", "required_field"),
    [
        ("character", "prompt_template"),
        ("location", "prompt_template"),
        ("voice", "style_prompt"),
    ],
)
async def test_generate_asset_draft_from_panel_should_return_required_prompt_fields(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    asset_type: str,
    required_field: str,
):
    monkeypatch.setattr(asset_hub_api.settings, "llm_api_key", "test-key")

    async def _fake_llm_generate(_body):
        if asset_type == "voice":
            return asset_hub_api._AssetDraftLlmResult(
                name="测试语音草案",
                description="语音资产描述",
                style_prompt="语速中等，情绪紧张，句尾下沉。",
            )
        return asset_hub_api._AssetDraftLlmResult(
            name="测试视觉资产草案",
            description="视觉资产描述",
            prompt_template="cinematic composition, dramatic lighting, high detail",
        )

    monkeypatch.setattr(asset_hub_api, "_generate_asset_draft_with_llm", _fake_llm_generate)

    response = await client.post("/api/asset-hub/drafts/from-panel", json={
        "asset_type": asset_type,
        "panel_title": "第1集-分镜01",
        "script_text": "主角在雨夜街头追逐目标，情绪紧张。",
        "visual_prompt": "rainy night city street, cinematic lighting, dynamic action",
        "tts_text": "快追上他，不要停！",
        "source_voice_name": "Xiaoxiao",
        "source_voice_provider": "edge-tts",
        "source_voice_code": "zh-CN-XiaoxiaoNeural",
    })
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"]
    assert data[required_field]
    assert data["generator"] == "llm"


@pytest.mark.asyncio
async def test_generate_asset_draft_from_panel_should_reject_when_llm_not_configured(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(asset_hub_api.settings, "llm_api_key", "")

    response = await client.post("/api/asset-hub/drafts/from-panel", json={
        "asset_type": "character",
        "panel_title": "第1集-分镜01",
        "script_text": "主角在雨夜街头追逐目标，情绪紧张。",
        "visual_prompt": "rainy night city street, cinematic lighting, dynamic action",
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "未配置 LLM_API_KEY，无法生成资产提示词草案"


@pytest.mark.asyncio
async def test_render_global_character_reference_should_update_reference_image(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    create_resp = await client.post("/api/asset-hub/characters", json={
        "name": "参考图角色",
        "prompt_template": "cinematic portrait, dramatic rim light",
    })
    assert create_resp.status_code == 200
    character_id = create_resp.json()["data"]["id"]

    async def fake_generate_image_from_prompt(asset_id: str, prompt: str, *, output_subdir: str):  # noqa: ANN001
        assert asset_id == character_id
        assert prompt == "cinematic portrait, dramatic rim light"
        assert output_subdir == "asset-hub/characters"
        return "/media/generated/character-ref.png"

    monkeypatch.setattr(
        "app.services.portrait_generator.generate_image_from_prompt",
        fake_generate_image_from_prompt,
    )

    response = await client.post(f"/api/asset-hub/characters/{character_id}/render-reference")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["id"] == character_id
    assert data["reference_image_url"] == "/media/generated/character-ref.png"
