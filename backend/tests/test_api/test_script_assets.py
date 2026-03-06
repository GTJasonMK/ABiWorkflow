from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_script_asset_entity_and_compile_flow(client: AsyncClient):
    create_project = await client.post("/api/projects", json={"name": "资产编译测试项目"})
    assert create_project.status_code == 200
    project_id = create_project.json()["data"]["id"]

    create_episode = await client.post(
        f"/api/projects/{project_id}/episodes",
        json={"title": "第1集", "script_text": "主角阿青来到古城广场并说话。"},
    )
    assert create_episode.status_code == 200
    episode_id = create_episode.json()["data"]["id"]

    create_panel = await client.post(
        f"/api/episodes/{episode_id}/panels",
        json={
            "title": "阿青登场",
            "script_text": "阿青来到古城广场并进行独白。",
            "visual_prompt": "cinematic wide shot",
            "duration_seconds": 5,
        },
    )
    assert create_panel.status_code == 200
    panel_id = create_panel.json()["data"]["id"]

    create_character_asset = await client.post(
        "/api/asset-hub/characters",
        json={
            "name": "阿青立绘",
            "project_id": project_id,
            "prompt_template": "female warrior, black hair, white robe, dramatic lighting",
            "reference_image_url": "https://example.com/aqing.png",
        },
    )
    assert create_character_asset.status_code == 200
    character_asset_id = create_character_asset.json()["data"]["id"]

    create_voice_asset = await client.post(
        "/api/asset-hub/voices",
        json={
            "name": "阿青声线",
            "project_id": project_id,
            "provider": "edge-tts",
            "voice_code": "zh-CN-XiaoxiaoNeural",
            "style_prompt": "清晰、沉稳、轻微情绪起伏",
        },
    )
    assert create_voice_asset.status_code == 200
    voice_asset_id = create_voice_asset.json()["data"]["id"]

    create_character_entity = await client.post(
        f"/api/projects/{project_id}/script-assets/entities",
        json={
            "entity_type": "character",
            "name": "阿青",
            "bindings": [
                {
                    "asset_type": "character",
                    "asset_id": character_asset_id,
                    "asset_name": "阿青立绘",
                    "is_primary": True,
                    "priority": 0,
                }
            ],
        },
    )
    assert create_character_entity.status_code == 200

    create_speaker_entity = await client.post(
        f"/api/projects/{project_id}/script-assets/entities",
        json={
            "entity_type": "speaker",
            "name": "阿青旁白",
            "bindings": [
                {
                    "asset_type": "voice",
                    "asset_id": voice_asset_id,
                    "asset_name": "阿青声线",
                    "is_primary": True,
                    "priority": 0,
                    "strategy": {"speed": 1.0, "emotion": "neutral"},
                }
            ],
        },
    )
    assert create_speaker_entity.status_code == 200

    compile_panel = await client.post(f"/api/panels/{panel_id}/compile-bindings")
    assert compile_panel.status_code == 200
    compiled = compile_panel.json()["data"]
    assert isinstance(compiled["characters"], list)
    assert isinstance(compiled["voices"], list)
    assert compiled["effective_visual_prompt"] is not None

    panel_detail = await client.get(f"/api/panels/{panel_id}")
    assert panel_detail.status_code == 200
    panel_payload = panel_detail.json()["data"]
    assert "effective_binding" in panel_payload
    assert isinstance(panel_payload["effective_binding"], dict)
    assert "trace" in panel_payload["effective_binding"]


@pytest.mark.asyncio
async def test_panel_override_can_switch_effective_voice(client: AsyncClient):
    project = await client.post("/api/projects", json={"name": "覆盖测试项目"})
    project_id = project.json()["data"]["id"]
    episode = await client.post(f"/api/projects/{project_id}/episodes", json={"title": "第1集"})
    episode_id = episode.json()["data"]["id"]
    panel = await client.post(
        f"/api/episodes/{episode_id}/panels",
        json={"title": "旁白镜头", "script_text": "旁白叙述开场", "duration_seconds": 4},
    )
    panel_id = panel.json()["data"]["id"]

    voice_a = await client.post(
        "/api/asset-hub/voices",
        json={
            "name": "旁白A",
            "project_id": project_id,
            "provider": "edge-tts",
            "voice_code": "zh-CN-YunxiNeural",
        },
    )
    voice_b = await client.post(
        "/api/asset-hub/voices",
        json={
            "name": "旁白B",
            "project_id": project_id,
            "provider": "edge-tts",
            "voice_code": "zh-CN-YunjianNeural",
        },
    )
    voice_a_id = voice_a.json()["data"]["id"]
    voice_b_id = voice_b.json()["data"]["id"]

    speaker = await client.post(
        f"/api/projects/{project_id}/script-assets/entities",
        json={
            "entity_type": "speaker",
            "name": "旁白",
            "bindings": [
                {"asset_type": "voice", "asset_id": voice_a_id, "asset_name": "旁白A", "is_primary": True}
            ],
        },
    )
    speaker_entity_id = speaker.json()["data"]["id"]

    compile_before = await client.post(f"/api/panels/{panel_id}/compile-bindings")
    assert compile_before.status_code == 200
    assert compile_before.json()["data"]["effective_voice"]["voice_id"] == voice_a_id

    replace_override = await client.put(
        f"/api/panels/{panel_id}/asset-overrides",
        json={
            "overrides": [
                {
                    "entity_id": speaker_entity_id,
                    "asset_type": "voice",
                    "asset_id": voice_b_id,
                    "asset_name": "旁白B",
                    "is_primary": True,
                    "priority": 0,
                }
            ]
        },
    )
    assert replace_override.status_code == 200

    effective = await client.get(f"/api/panels/{panel_id}/effective-bindings")
    assert effective.status_code == 200
    assert effective.json()["data"]["effective_voice"]["voice_id"] == voice_b_id


@pytest.mark.asyncio
async def test_episode_scoped_script_entity_binding_should_apply_only_to_target_episode(client: AsyncClient):
    create_project = await client.post('/api/projects', json={'name': '分集绑定作用域测试'})
    assert create_project.status_code == 200
    project_id = create_project.json()['data']['id']

    episode_1 = await client.post(
        f'/api/projects/{project_id}/episodes',
        json={'title': '第1集', 'script_text': '镜头展示夜晚古城。'},
    )
    episode_2 = await client.post(
        f'/api/projects/{project_id}/episodes',
        json={'title': '第2集', 'script_text': '镜头展示白天街道。'},
    )
    assert episode_1.status_code == 200 and episode_2.status_code == 200
    episode_1_id = episode_1.json()['data']['id']
    episode_2_id = episode_2.json()['data']['id']

    panel_1 = await client.post(
        f'/api/episodes/{episode_1_id}/panels',
        json={'title': '夜景镜头', 'script_text': '城市夜景空镜。', 'duration_seconds': 4},
    )
    panel_2 = await client.post(
        f'/api/episodes/{episode_2_id}/panels',
        json={'title': '白天镜头', 'script_text': '城市白天空镜。', 'duration_seconds': 4},
    )
    assert panel_1.status_code == 200 and panel_2.status_code == 200
    panel_1_id = panel_1.json()['data']['id']
    panel_2_id = panel_2.json()['data']['id']

    location_global = await client.post(
        '/api/asset-hub/locations',
        json={
            'name': '默认城市场景',
            'project_id': project_id,
            'prompt_template': 'day city street',
        },
    )
    location_episode = await client.post(
        '/api/asset-hub/locations',
        json={
            'name': '夜晚古城场景',
            'project_id': project_id,
            'prompt_template': 'ancient city at night',
            'reference_image_url': 'https://example.com/night-city.png',
        },
    )
    assert location_global.status_code == 200 and location_episode.status_code == 200
    global_location_id = location_global.json()['data']['id']
    episode_location_id = location_episode.json()['data']['id']

    entity_resp = await client.post(
        f'/api/projects/{project_id}/script-assets/entities',
        json={
            'entity_type': 'location',
            'name': '背景地点',
            'bindings': [
                {
                    'asset_type': 'location',
                    'asset_id': global_location_id,
                    'asset_name': '默认城市场景',
                    'is_primary': True,
                    'priority': 0,
                },
                {
                    'asset_type': 'location',
                    'asset_id': episode_location_id,
                    'asset_name': '夜晚古城场景',
                    'is_primary': True,
                    'priority': 0,
                    'strategy': {'episode_id': episode_1_id, 'source': 'asset_binding_page'},
                },
            ],
        },
    )
    assert entity_resp.status_code == 200

    effective_1 = await client.get(f'/api/panels/{panel_1_id}/effective-bindings')
    effective_2 = await client.get(f'/api/panels/{panel_2_id}/effective-bindings')
    assert effective_1.status_code == 200 and effective_2.status_code == 200

    payload_1 = effective_1.json()['data']
    payload_2 = effective_2.json()['data']

    assert payload_1['locations']
    assert payload_1['locations'][0]['asset_id'] == episode_location_id
    assert payload_1['locations'][0]['source_layer'] == 'script_episode'
    assert payload_1['effective_reference_image_url'] == 'https://example.com/night-city.png'

    assert payload_2['locations'] == []
    assert payload_2['effective_reference_image_url'] is None
