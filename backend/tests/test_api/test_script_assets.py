from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PanelEffectiveBinding


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


@pytest.mark.asyncio
async def test_create_script_entity_should_reject_foreign_project_asset_binding(client: AsyncClient):
    create_project_a = await client.post('/api/projects', json={'name': '剧本绑定项目A'})
    create_project_b = await client.post('/api/projects', json={'name': '剧本绑定项目B'})
    assert create_project_a.status_code == 200 and create_project_b.status_code == 200
    project_a_id = create_project_a.json()['data']['id']
    project_b_id = create_project_b.json()['data']['id']

    create_character_asset = await client.post(
        '/api/asset-hub/characters',
        json={
            'name': '项目B角色资产',
            'project_id': project_b_id,
            'prompt_template': 'project b character prompt',
        },
    )
    assert create_character_asset.status_code == 200
    character_asset_id = create_character_asset.json()['data']['id']

    create_entity = await client.post(
        f'/api/projects/{project_a_id}/script-assets/entities',
        json={
            'entity_type': 'character',
            'name': '项目A角色实体',
            'bindings': [
                {
                    'asset_type': 'character',
                    'asset_id': character_asset_id,
                    'asset_name': '项目B角色资产',
                    'is_primary': True,
                }
            ],
        },
    )
    assert create_entity.status_code == 400
    assert create_entity.json()['detail'] == f'包含不属于当前项目的角色资产ID: {character_asset_id}'


@pytest.mark.asyncio
async def test_replace_panel_asset_overrides_should_reject_missing_asset_id(client: AsyncClient):
    create_project = await client.post('/api/projects', json={'name': '分镜覆盖资产校验测试'})
    assert create_project.status_code == 200
    project_id = create_project.json()['data']['id']

    create_episode = await client.post(
        f'/api/projects/{project_id}/episodes',
        json={'title': '第1集', 'script_text': '测试分镜覆盖。'},
    )
    assert create_episode.status_code == 200
    episode_id = create_episode.json()['data']['id']

    create_panel = await client.post(
        f'/api/episodes/{episode_id}/panels',
        json={'title': '分镜一', 'script_text': '测试分镜', 'duration_seconds': 4},
    )
    assert create_panel.status_code == 200
    panel_id = create_panel.json()['data']['id']

    create_entity = await client.post(
        f'/api/projects/{project_id}/script-assets/entities',
        json={
            'entity_type': 'speaker',
            'name': '旁白实体',
        },
    )
    assert create_entity.status_code == 200
    entity_id = create_entity.json()['data']['id']

    replace_override = await client.put(
        f'/api/panels/{panel_id}/asset-overrides',
        json={
            'overrides': [
                {
                    'entity_id': entity_id,
                    'asset_type': 'voice',
                    'asset_id': 'not-exists-voice',
                    'asset_name': '不存在的语音',
                    'is_primary': True,
                }
            ]
        },
    )
    assert replace_override.status_code == 400
    assert replace_override.json()['detail'] == '包含不存在的语音资产ID: not-exists-voice'


async def _create_character_default_voice_context(client: AsyncClient) -> dict[str, str]:
    create_project = await client.post('/api/projects', json={'name': '角色默认语音生效测试'})
    assert create_project.status_code == 200
    project_id = create_project.json()['data']['id']

    create_episode = await client.post(
        f'/api/projects/{project_id}/episodes',
        json={'title': '第1集', 'script_text': '阿青在古城中开口说话。'},
    )
    assert create_episode.status_code == 200
    episode_id = create_episode.json()['data']['id']

    create_panel = await client.post(
        f'/api/episodes/{episode_id}/panels',
        json={
            'title': '阿青对白',
            'script_text': '阿青在古城中开口说话。',
            'visual_prompt': 'ancient city dialogue',
            'duration_seconds': 5,
        },
    )
    assert create_panel.status_code == 200
    panel_id = create_panel.json()['data']['id']

    voice_resp = await client.post(
        '/api/asset-hub/voices',
        json={
            'name': '阿青默认声线',
            'project_id': project_id,
            'provider': 'edge-tts',
            'voice_code': 'zh-CN-XiaoxiaoNeural',
        },
    )
    assert voice_resp.status_code == 200
    voice_id = voice_resp.json()['data']['id']

    character_resp = await client.post(
        '/api/asset-hub/characters',
        json={
            'name': '阿青立绘',
            'project_id': project_id,
            'prompt_template': 'young swordswoman, white robe',
            'default_voice_id': voice_id,
        },
    )
    assert character_resp.status_code == 200
    character_asset_id = character_resp.json()['data']['id']

    entity_resp = await client.post(
        f'/api/projects/{project_id}/script-assets/entities',
        json={
            'entity_type': 'character',
            'name': '阿青',
            'bindings': [
                {
                    'asset_type': 'character',
                    'asset_id': character_asset_id,
                    'asset_name': '阿青立绘',
                    'is_primary': True,
                    'priority': 0,
                }
            ],
        },
    )
    assert entity_resp.status_code == 200

    return {
        'project_id': project_id,
        'episode_id': episode_id,
        'panel_id': panel_id,
        'voice_id': voice_id,
        'character_asset_id': character_asset_id,
    }


@pytest.mark.asyncio
async def test_character_default_voice_should_become_effective_voice(client: AsyncClient):
    context = await _create_character_default_voice_context(client)

    effective = await client.get(f"/api/panels/{context['panel_id']}/effective-bindings")
    assert effective.status_code == 200
    data = effective.json()['data']
    assert data['effective_voice']['voice_id'] == context['voice_id']
    assert data['effective_voice']['source_layer'] == 'character_default'
    assert data['effective_voice']['entity_id'] is None
    assert data['effective_voice']['entity_name'] == '阿青'


@pytest.mark.asyncio
async def test_explicit_speaker_voice_binding_should_override_character_default_voice(client: AsyncClient):
    context = await _create_character_default_voice_context(client)

    override_voice_resp = await client.post(
        '/api/asset-hub/voices',
        json={
            'name': '阿青旁白声线',
            'project_id': context['project_id'],
            'provider': 'edge-tts',
            'voice_code': 'zh-CN-YunxiNeural',
        },
    )
    assert override_voice_resp.status_code == 200
    override_voice_id = override_voice_resp.json()['data']['id']

    speaker_resp = await client.post(
        f"/api/projects/{context['project_id']}/script-assets/entities",
        json={
            'entity_type': 'speaker',
            'name': '阿青',
            'bindings': [
                {
                    'asset_type': 'voice',
                    'asset_id': override_voice_id,
                    'asset_name': '阿青旁白声线',
                    'is_primary': True,
                    'priority': 0,
                }
            ],
        },
    )
    assert speaker_resp.status_code == 200
    speaker_id = speaker_resp.json()['data']['id']

    effective = await client.get(f"/api/panels/{context['panel_id']}/effective-bindings")
    assert effective.status_code == 200
    data = effective.json()['data']
    assert data['effective_voice']['voice_id'] == override_voice_id
    assert data['effective_voice']['source_layer'] == 'script'
    assert data['effective_voice']['entity_id'] == speaker_id


@pytest.mark.asyncio
async def test_update_character_default_voice_should_refresh_effective_binding_snapshot(client: AsyncClient):
    context = await _create_character_default_voice_context(client)

    effective_before = await client.get(f"/api/panels/{context['panel_id']}/effective-bindings")
    assert effective_before.status_code == 200
    assert effective_before.json()['data']['effective_voice']['voice_id'] == context['voice_id']

    voice_resp = await client.post(
        '/api/asset-hub/voices',
        json={
            'name': '阿青新默认声线',
            'project_id': context['project_id'],
            'provider': 'edge-tts',
            'voice_code': 'zh-CN-YunjianNeural',
        },
    )
    assert voice_resp.status_code == 200
    next_voice_id = voice_resp.json()['data']['id']

    update_character = await client.put(
        f"/api/asset-hub/characters/{context['character_asset_id']}",
        json={'default_voice_id': next_voice_id},
    )
    assert update_character.status_code == 200

    effective_after = await client.get(f"/api/panels/{context['panel_id']}/effective-bindings")
    assert effective_after.status_code == 200
    assert effective_after.json()['data']['effective_voice']['voice_id'] == next_voice_id
    assert effective_after.json()['data']['effective_voice']['source_layer'] == 'character_default'


@pytest.mark.asyncio
async def test_delete_character_default_voice_should_clear_effective_voice(client: AsyncClient):
    context = await _create_character_default_voice_context(client)

    effective_before = await client.get(f"/api/panels/{context['panel_id']}/effective-bindings")
    assert effective_before.status_code == 200
    assert effective_before.json()['data']['effective_voice']['voice_id'] == context['voice_id']

    delete_voice = await client.delete(f"/api/asset-hub/voices/{context['voice_id']}")
    assert delete_voice.status_code == 200

    characters_resp = await client.get(
        '/api/asset-hub/characters',
        params={'project_id': context['project_id'], 'scope': 'project'},
    )
    assert characters_resp.status_code == 200
    character_map = {item['id']: item for item in characters_resp.json()['data']}
    assert character_map[context['character_asset_id']]['default_voice_id'] is None

    effective_after = await client.get(f"/api/panels/{context['panel_id']}/effective-bindings")
    assert effective_after.status_code == 200
    assert effective_after.json()['data']['effective_voice'] is None


@pytest.mark.asyncio
async def test_get_panel_should_refresh_stale_effective_binding_snapshot(
    client: AsyncClient,
    db_session: AsyncSession,
):
    context = await _create_character_default_voice_context(client)

    compiled = await client.get(f"/api/panels/{context['panel_id']}/effective-bindings")
    assert compiled.status_code == 200

    row = await db_session.get(PanelEffectiveBinding, context['panel_id'])
    assert row is not None
    row.compiler_version = 'stale-version'
    await db_session.commit()

    detail = await client.get(f"/api/panels/{context['panel_id']}")
    assert detail.status_code == 200
    assert detail.json()['data']['effective_binding']['effective_voice']['voice_id'] == context['voice_id']

    db_session.expire_all()
    refreshed = await db_session.get(PanelEffectiveBinding, context['panel_id'])
    assert refreshed is not None
    assert refreshed.compiler_version == 'v2'
