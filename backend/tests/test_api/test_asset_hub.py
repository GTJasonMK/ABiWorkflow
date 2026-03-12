from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import asset_hub as asset_hub_api
from app.models import PanelAssetOverride, Project, ScriptEntityAssetBinding


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
async def test_generate_asset_draft_from_panel_should_fail_with_clear_message_when_llm_is_rate_limited(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(asset_hub_api.settings, "llm_api_key", "test-key")

    async def _failing_llm_generate(_body):
        raise RuntimeError("Error code: 502 - {'error': {'message': 'AppChatReverse: Chat failed, 429'}}")

    monkeypatch.setattr(asset_hub_api, "_generate_asset_draft_with_llm", _failing_llm_generate)

    response = await client.post("/api/asset-hub/drafts/from-panel", json={
        "asset_type": "character",
        "panel_title": "第一幕",
        "script_text": "画面：主角特写，正面。发型油光锃亮，领带系得很紧，眼神充满自信。公司楼下。",
        "visual_prompt": "",
        "tts_text": "我叫赵铁柱，我准备好了。",
        "source_voice_name": "Xiaoxiao",
        "source_voice_provider": "edge-tts",
        "source_voice_code": "zh-CN-XiaoxiaoNeural",
    })
    assert response.status_code == 503
    assert response.json()["detail"] == "当前配置的 LLM provider 上游限流，请稍后重试或切换 provider"


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


@pytest.mark.asyncio
async def test_update_global_voice_should_reject_blank_voice_code_without_persisting(
    client: AsyncClient,
):
    create_resp = await client.post("/api/asset-hub/voices", json={
        "name": "测试语音更新",
        "provider": "edge-tts",
        "voice_code": "zh-CN-XiaoxiaoNeural",
    })
    assert create_resp.status_code == 200
    voice_id = create_resp.json()["data"]["id"]

    update_resp = await client.put(
        f"/api/asset-hub/voices/{voice_id}",
        json={"voice_code": "   "},
    )
    assert update_resp.status_code == 400
    assert update_resp.json()["detail"] == "voice_code 不能为空"

    list_resp = await client.get("/api/asset-hub/voices")
    assert list_resp.status_code == 200
    voice_map = {item["id"]: item for item in list_resp.json()["data"]}
    assert voice_map[voice_id]["voice_code"] == "zh-CN-XiaoxiaoNeural"


@pytest.mark.asyncio
async def test_update_global_voice_should_default_blank_provider_to_edge_tts(client: AsyncClient):
    create_resp = await client.post("/api/asset-hub/voices", json={
        "name": "测试语音提供方更新",
        "provider": "custom-provider",
        "voice_code": "zh-CN-XiaoxiaoNeural",
    })
    assert create_resp.status_code == 200
    voice_id = create_resp.json()["data"]["id"]

    update_resp = await client.put(
        f"/api/asset-hub/voices/{voice_id}",
        json={"provider": "   "},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["provider"] == "edge-tts"

    list_resp = await client.get("/api/asset-hub/voices")
    assert list_resp.status_code == 200
    voice_map = {item["id"]: item for item in list_resp.json()["data"]}
    assert voice_map[voice_id]["provider"] == "edge-tts"


@pytest.mark.asyncio
async def test_update_asset_folder_should_reject_blank_name_without_persisting(client: AsyncClient):
    create_resp = await client.post("/api/asset-hub/folders", json={"name": "原目录", "folder_type": "generic"})
    assert create_resp.status_code == 200
    folder_id = create_resp.json()["data"]["id"]

    update_resp = await client.put(
        f"/api/asset-hub/folders/{folder_id}",
        json={"name": "   "},
    )
    assert update_resp.status_code == 400
    assert update_resp.json()["detail"] == "资产目录名称不能为空"

    list_resp = await client.get("/api/asset-hub/folders")
    assert list_resp.status_code == 200
    folder_map = {item["id"]: item for item in list_resp.json()["data"]}
    assert folder_map[folder_id]["name"] == "原目录"


@pytest.mark.asyncio
async def test_create_asset_folder_should_reject_blank_name(client: AsyncClient):
    response = await client.post("/api/asset-hub/folders", json={"name": "   ", "folder_type": "generic"})
    assert response.status_code == 400
    assert response.json()["detail"] == "资产目录名称不能为空"


@pytest.mark.asyncio
async def test_create_global_voice_should_reject_blank_voice_code(client: AsyncClient):
    response = await client.post("/api/asset-hub/voices", json={
        "name": "测试语音",
        "provider": "edge-tts",
        "voice_code": "   ",
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "voice_code 不能为空"


@pytest.mark.asyncio
async def test_create_global_character_should_reject_unknown_default_voice_id(client: AsyncClient):
    response = await client.post("/api/asset-hub/characters", json={
        "name": "非法默认语音角色",
        "default_voice_id": "not-exists-voice",
    })
    assert response.status_code == 400
    assert response.json()["detail"] == "默认语音不存在"


@pytest.mark.asyncio
async def test_update_global_character_should_reject_unknown_default_voice_id_without_persisting(client: AsyncClient):
    create_resp = await client.post("/api/asset-hub/characters", json={
        "name": "默认语音角色",
    })
    assert create_resp.status_code == 200
    character_id = create_resp.json()["data"]["id"]

    update_resp = await client.put(
        f"/api/asset-hub/characters/{character_id}",
        json={"default_voice_id": "not-exists-voice"},
    )
    assert update_resp.status_code == 400
    assert update_resp.json()["detail"] == "默认语音不存在"

    list_resp = await client.get("/api/asset-hub/characters")
    assert list_resp.status_code == 200
    character_map = {item["id"]: item for item in list_resp.json()["data"]}
    assert character_map[character_id]["default_voice_id"] is None


@pytest.mark.asyncio
async def test_delete_global_voice_should_clear_references_and_recompile_bindings(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="语音删除清理测试项目", status="draft")
    db_session.add(project)
    await db_session.commit()

    create_episode = await client.post(
        f"/api/projects/{project.id}/episodes",
        json={"title": "第1集", "script_text": "角色进行旁白。"},
    )
    assert create_episode.status_code == 200
    episode_id = create_episode.json()["data"]["id"]

    create_panel = await client.post(
        f"/api/episodes/{episode_id}/panels",
        json={"title": "旁白分镜", "script_text": "角色旁白。", "duration_seconds": 4},
    )
    assert create_panel.status_code == 200
    panel_id = create_panel.json()["data"]["id"]

    create_voice = await client.post(
        "/api/asset-hub/voices",
        json={
            "name": "测试声线",
            "project_id": project.id,
            "provider": "edge-tts",
            "voice_code": "zh-CN-XiaoxiaoNeural",
        },
    )
    assert create_voice.status_code == 200
    voice_id = create_voice.json()["data"]["id"]

    create_character = await client.post(
        "/api/asset-hub/characters",
        json={
            "name": "绑定默认语音的角色",
            "project_id": project.id,
            "default_voice_id": voice_id,
        },
    )
    assert create_character.status_code == 200
    character_id = create_character.json()["data"]["id"]

    speaker_entity = await client.post(
        f"/api/projects/{project.id}/script-assets/entities",
        json={
            "entity_type": "speaker",
            "name": "旁白",
            "bindings": [
                {
                    "asset_type": "voice",
                    "asset_id": voice_id,
                    "asset_name": "测试声线",
                    "is_primary": True,
                    "priority": 0,
                }
            ],
        },
    )
    assert speaker_entity.status_code == 200
    speaker_entity_id = speaker_entity.json()["data"]["id"]

    bind_voice = await client.put(
        f"/api/panels/{panel_id}/voice/binding",
        json={"voice_id": voice_id, "entity_id": speaker_entity_id},
    )
    assert bind_voice.status_code == 200
    assert bind_voice.json()["data"]["voice_id"] == voice_id

    effective_before = await client.get(f"/api/panels/{panel_id}/effective-bindings")
    assert effective_before.status_code == 200
    assert effective_before.json()["data"]["effective_voice"]["voice_id"] == voice_id

    delete_resp = await client.delete(f"/api/asset-hub/voices/{voice_id}")
    assert delete_resp.status_code == 200

    list_characters = await client.get(
        "/api/asset-hub/characters",
        params={"project_id": project.id, "scope": "project"},
    )
    assert list_characters.status_code == 200
    character_map = {item["id"]: item for item in list_characters.json()["data"]}
    assert character_map[character_id]["default_voice_id"] is None

    panel_detail = await client.get(f"/api/panels/{panel_id}")
    assert panel_detail.status_code == 200
    assert panel_detail.json()["data"]["voice_id"] is None

    effective_after = await client.get(f"/api/panels/{panel_id}/effective-bindings")
    assert effective_after.status_code == 200
    assert effective_after.json()["data"]["effective_voice"] is None
    assert effective_after.json()["data"]["voices"] == []

    remaining_panel_overrides = (await db_session.execute(
        select(PanelAssetOverride).where(
            PanelAssetOverride.asset_type == "voice",
            PanelAssetOverride.asset_id == voice_id,
        )
    )).scalars().all()
    remaining_script_bindings = (await db_session.execute(
        select(ScriptEntityAssetBinding).where(
            ScriptEntityAssetBinding.asset_type == "voice",
            ScriptEntityAssetBinding.asset_id == voice_id,
        )
    )).scalars().all()
    assert remaining_panel_overrides == []
    assert remaining_script_bindings == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_type", "entity_type", "asset_endpoint", "entity_name", "effective_key"),
    [
        ("character", "character", "/api/asset-hub/characters", "阿青", "characters"),
        ("location", "location", "/api/asset-hub/locations", "古城广场", "locations"),
    ],
)
async def test_delete_visual_asset_should_clear_bindings_and_recompile_effective_binding(
    client: AsyncClient,
    db_session: AsyncSession,
    asset_type: str,
    entity_type: str,
    asset_endpoint: str,
    entity_name: str,
    effective_key: str,
):
    project = Project(name=f"{asset_type} 删除清理测试项目", status="draft")
    db_session.add(project)
    await db_session.commit()

    create_episode = await client.post(
        f"/api/projects/{project.id}/episodes",
        json={"title": "第1集", "script_text": f"{entity_name} 出现在画面中。"},
    )
    assert create_episode.status_code == 200
    episode_id = create_episode.json()["data"]["id"]

    create_panel = await client.post(
        f"/api/episodes/{episode_id}/panels",
        json={"title": f"{entity_name} 分镜", "script_text": f"{entity_name} 出现在画面中。", "duration_seconds": 4},
    )
    assert create_panel.status_code == 200
    panel_id = create_panel.json()["data"]["id"]

    create_asset = await client.post(
        asset_endpoint,
        json={
            "name": f"{entity_name} 资产",
            "project_id": project.id,
            "prompt_template": f"{entity_name} detailed prompt",
            "reference_image_url": f"https://example.com/{asset_type}.png",
        },
    )
    assert create_asset.status_code == 200
    asset_id = create_asset.json()["data"]["id"]

    create_entity = await client.post(
        f"/api/projects/{project.id}/script-assets/entities",
        json={
            "entity_type": entity_type,
            "name": entity_name,
            "bindings": [
                {
                    "asset_type": asset_type,
                    "asset_id": asset_id,
                    "asset_name": f"{entity_name} 资产",
                    "is_primary": True,
                    "priority": 0,
                }
            ],
        },
    )
    assert create_entity.status_code == 200
    entity_id = create_entity.json()["data"]["id"]

    panel_override = await client.put(
        f"/api/panels/{panel_id}/asset-overrides",
        json={
            "overrides": [
                {
                    "entity_id": entity_id,
                    "asset_type": asset_type,
                    "asset_id": asset_id,
                    "asset_name": f"{entity_name} 资产",
                    "is_primary": True,
                    "priority": 0,
                }
            ]
        },
    )
    assert panel_override.status_code == 200

    effective_before = await client.get(f"/api/panels/{panel_id}/effective-bindings")
    assert effective_before.status_code == 200
    assert effective_before.json()["data"][effective_key][0]["asset_id"] == asset_id
    assert effective_before.json()["data"]["effective_reference_image_url"] == f"https://example.com/{asset_type}.png"

    delete_resp = await client.delete(f"{asset_endpoint}/{asset_id}")
    assert delete_resp.status_code == 200

    effective_after = await client.get(f"/api/panels/{panel_id}/effective-bindings")
    assert effective_after.status_code == 200
    assert effective_after.json()["data"][effective_key] == []
    assert effective_after.json()["data"]["effective_reference_image_url"] is None

    remaining_panel_overrides = (await db_session.execute(
        select(PanelAssetOverride).where(
            PanelAssetOverride.asset_type == asset_type,
            PanelAssetOverride.asset_id == asset_id,
        )
    )).scalars().all()
    remaining_script_bindings = (await db_session.execute(
        select(ScriptEntityAssetBinding).where(
            ScriptEntityAssetBinding.asset_type == asset_type,
            ScriptEntityAssetBinding.asset_id == asset_id,
        )
    )).scalars().all()
    assert remaining_panel_overrides == []
    assert remaining_script_bindings == []


@pytest.mark.asyncio
async def test_create_global_character_should_reject_default_voice_from_other_project(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project_a = Project(name="角色语音作用域项目A", status="draft")
    project_b = Project(name="角色语音作用域项目B", status="draft")
    db_session.add_all([project_a, project_b])
    await db_session.commit()

    create_voice = await client.post(
        "/api/asset-hub/voices",
        json={
            "name": "项目B语音",
            "project_id": project_b.id,
            "provider": "edge-tts",
            "voice_code": "zh-CN-XiaoxiaoNeural",
        },
    )
    assert create_voice.status_code == 200
    voice_id = create_voice.json()["data"]["id"]

    create_character = await client.post(
        "/api/asset-hub/characters",
        json={
            "name": "项目A角色",
            "project_id": project_a.id,
            "default_voice_id": voice_id,
        },
    )
    assert create_character.status_code == 400
    assert create_character.json()["detail"] == "默认语音必须是全局语音或与角色归属同项目"


@pytest.mark.asyncio
async def test_update_global_character_should_reject_cross_project_default_voice_without_persisting(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project_a = Project(name="角色更新作用域项目A", status="draft")
    project_b = Project(name="角色更新作用域项目B", status="draft")
    db_session.add_all([project_a, project_b])
    await db_session.commit()

    create_character = await client.post(
        "/api/asset-hub/characters",
        json={
            "name": "项目A角色",
            "project_id": project_a.id,
        },
    )
    assert create_character.status_code == 200
    character_id = create_character.json()["data"]["id"]

    create_voice = await client.post(
        "/api/asset-hub/voices",
        json={
            "name": "项目B语音",
            "project_id": project_b.id,
            "provider": "edge-tts",
            "voice_code": "zh-CN-XiaoxiaoNeural",
        },
    )
    assert create_voice.status_code == 200
    voice_id = create_voice.json()["data"]["id"]

    update_character = await client.put(
        f"/api/asset-hub/characters/{character_id}",
        json={"default_voice_id": voice_id},
    )
    assert update_character.status_code == 400
    assert update_character.json()["detail"] == "默认语音必须是全局语音或与角色归属同项目"

    list_resp = await client.get(
        "/api/asset-hub/characters",
        params={"project_id": project_a.id, "scope": "project"},
    )
    assert list_resp.status_code == 200
    character_map = {item["id"]: item for item in list_resp.json()["data"]}
    assert character_map[character_id]["default_voice_id"] is None
