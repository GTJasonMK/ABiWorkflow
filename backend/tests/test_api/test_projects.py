from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Character,
    CompositionTask,
    Episode,
    GlobalVoice,
    Panel,
    Project,
    ProviderConfig,
    ScriptEntity,
    ScriptEntityAssetBinding,
    VideoClip,
)


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
async def test_health_check(client: AsyncClient):
    """健康检查端点"""
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient):
    """创建项目"""
    response = await client.post("/api/projects", json={"name": "测试项目", "description": "这是一个测试项目"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["data"]["name"] == "测试项目"
    assert data["data"]["status"] == "draft"
    assert data["data"]["workflow_defaults"] == {
        "video_provider_key": None,
        "tts_provider_key": None,
        "lipsync_provider_key": None,
        "provider_payload_defaults": {
            "video": {},
            "tts": {},
            "lipsync": {},
        },
    }


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient):
    """项目列表（分页）"""
    # 创建3个项目
    for i in range(3):
        await client.post("/api/projects", json={"name": f"项目{i}"})

    response = await client.get("/api/projects", params={"page": 1, "page_size": 2})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_list_projects_returns_stats(client: AsyncClient):
    """项目列表响应包含全局状态统计"""
    await client.post("/api/projects", json={"name": "草稿项目A"})
    await client.post("/api/projects", json={"name": "草稿项目B"})

    response = await client.get("/api/projects")
    assert response.status_code == 200
    data = response.json()["data"]
    assert "stats" in data
    assert data["stats"]["draft"] == 2


@pytest.mark.asyncio
async def test_list_projects_keyword_search(client: AsyncClient):
    """按关键词搜索项目名称"""
    await client.post("/api/projects", json={"name": "阿里巴巴"})
    await client.post("/api/projects", json={"name": "腾讯视频"})
    await client.post("/api/projects", json={"name": "阿里云"})

    response = await client.get("/api/projects", params={"keyword": "阿里"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    names = [item["name"] for item in data["items"]]
    assert "阿里巴巴" in names
    assert "阿里云" in names
    assert "腾讯视频" not in names


@pytest.mark.asyncio
async def test_list_projects_status_filter(client: AsyncClient):
    """按状态筛选项目"""
    await client.post("/api/projects", json={"name": "草稿A"})
    await client.post("/api/projects", json={"name": "草稿B"})

    # 所有新建项目都是 draft，用 status=draft 过滤应全部返回
    response = await client.get("/api/projects", params={"status": "draft"})
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2

    # 用不存在的状态过滤，应返回空
    response = await client.get("/api/projects", params={"status": "completed"})
    data = response.json()["data"]
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_projects_sort_by_name(client: AsyncClient):
    """按名称排序"""
    await client.post("/api/projects", json={"name": "Charlie"})
    await client.post("/api/projects", json={"name": "Alice"})
    await client.post("/api/projects", json={"name": "Bob"})

    response = await client.get("/api/projects", params={"sort_by": "name", "sort_order": "asc"})
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    names = [item["name"] for item in items]
    assert names == ["Alice", "Bob", "Charlie"]


@pytest.mark.asyncio
async def test_list_projects_character_count(client: AsyncClient):
    """项目列表返回角色数量"""
    response = await client.post("/api/projects", json={"name": "测试角色数"})
    assert response.status_code == 200
    # 新建项目无角色
    resp = await client.get("/api/projects")
    items = resp.json()["data"]["items"]
    assert items[0]["character_count"] == 0


@pytest.mark.asyncio
async def test_list_projects_stats_not_affected_by_filter(client: AsyncClient):
    """stats 反映全库数据，不受搜索/筛选影响"""
    await client.post("/api/projects", json={"name": "Alpha"})
    await client.post("/api/projects", json={"name": "Beta"})

    # 用关键词搜索只匹配1个项目
    response = await client.get("/api/projects", params={"keyword": "Alpha"})
    data = response.json()["data"]
    assert data["total"] == 1
    # stats 仍反映全部项目
    assert data["stats"]["draft"] == 2


@pytest.mark.asyncio
async def test_project_counts_should_not_fallback_to_scene_data(
    client: AsyncClient,
    db_session: AsyncSession,
):
    """项目统计只使用 Panel，不再回退历史中间模型。"""
    create_resp = await client.post("/api/projects", json={"name": "仅场景项目"})
    project_id = create_resp.json()["data"]["id"]
    await db_session.commit()

    list_resp = await client.get("/api/projects")
    assert list_resp.status_code == 200
    item = next(v for v in list_resp.json()["data"]["items"] if v["id"] == project_id)
    assert item["panel_count"] == 0
    assert item["generated_panel_count"] == 0

    detail_resp = await client.get(f"/api/projects/{project_id}")
    assert detail_resp.status_code == 200
    payload = detail_resp.json()["data"]
    assert payload["panel_count"] == 0
    assert payload["generated_panel_count"] == 0


@pytest.mark.asyncio
async def test_duplicate_project(client: AsyncClient):
    """复制项目"""
    # 创建源项目
    create_resp = await client.post("/api/projects", json={"name": "原始项目", "description": "原始描述"})
    source_id = create_resp.json()["data"]["id"]

    # 写入剧本
    await client.put(f"/api/projects/{source_id}", json={"script_text": "一段剧本文本"})

    # 复制
    dup_resp = await client.post(f"/api/projects/{source_id}/duplicate")
    assert dup_resp.status_code == 200
    dup_data = dup_resp.json()["data"]
    assert dup_data["name"] == "原始项目 (副本)"
    assert dup_data["description"] == "原始描述"
    assert dup_data["script_text"] == "一段剧本文本"
    assert dup_data["status"] == "draft"
    assert dup_data["id"] != source_id


@pytest.mark.asyncio
async def test_duplicate_project_should_copy_episode_and_panel_structure(
    client: AsyncClient,
    db_session: AsyncSession,
):
    create_resp = await client.post("/api/projects", json={"name": "结构复制项目", "description": "结构描述"})
    source_id = create_resp.json()["data"]["id"]

    episode_1 = Episode(project_id=source_id, episode_order=0, title="第1集", summary="摘要1", script_text="内容1")
    episode_2 = Episode(project_id=source_id, episode_order=1, title="第2集", summary="摘要2", script_text="内容2")
    db_session.add_all([episode_1, episode_2])
    await db_session.flush()

    db_session.add_all([
        Panel(
            project_id=source_id,
            episode_id=episode_1.id,
            panel_order=0,
            title="第一集分镜一",
            script_text="分镜内容1",
            visual_prompt="提示词1",
            duration_seconds=4.0,
            status="completed",
            video_url="/media/videos/source-1.mp4",
        ),
        Panel(
            project_id=source_id,
            episode_id=episode_2.id,
            panel_order=0,
            title="第二集分镜一",
            script_text="分镜内容2",
            visual_prompt="提示词2",
            duration_seconds=5.0,
            status="failed",
            error_message="历史错误",
        ),
    ])
    await db_session.commit()

    dup_resp = await client.post(f"/api/projects/{source_id}/duplicate")
    assert dup_resp.status_code == 200
    dup_data = dup_resp.json()["data"]
    dup_id = dup_data["id"]
    assert dup_data["episode_count"] == 2
    assert dup_data["panel_count"] == 2
    assert dup_data["generated_panel_count"] == 0

    dup_episodes = (await db_session.execute(
        select(Episode).where(Episode.project_id == dup_id).order_by(Episode.episode_order)
    )).scalars().all()
    assert [episode.title for episode in dup_episodes] == ["第1集", "第2集"]
    assert [episode.summary for episode in dup_episodes] == ["摘要1", "摘要2"]

    dup_panels = (await db_session.execute(
        select(Panel)
        .where(Panel.project_id == dup_id)
        .order_by(Panel.panel_order, Panel.created_at)
    )).scalars().all()
    assert [panel.title for panel in dup_panels] == ["第一集分镜一", "第二集分镜一"]
    assert all(panel.status == "pending" for panel in dup_panels)
    assert all(panel.video_url is None for panel in dup_panels)
    assert all(panel.error_message is None for panel in dup_panels)
    assert {panel.episode_id for panel in dup_panels} == {episode.id for episode in dup_episodes}


@pytest.mark.asyncio
async def test_duplicate_nonexistent_project(client: AsyncClient):
    """复制不存在的项目应返回 404"""
    response = await client.post("/api/projects/nonexistent-id/duplicate")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_project(client: AsyncClient):
    """获取项目详情"""
    create_resp = await client.post("/api/projects", json={"name": "详情测试"})
    project_id = create_resp.json()["data"]["id"]

    response = await client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "详情测试"


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient):
    """更新项目"""
    create_resp = await client.post("/api/projects", json={"name": "原始名称"})
    project_id = create_resp.json()["data"]["id"]

    response = await client.put(f"/api/projects/{project_id}", json={
        "name": "新名称",
        "script_text": "这是一段测试剧本"
    })
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "新名称"
    assert data["script_text"] == "这是一段测试剧本"


@pytest.mark.asyncio
async def test_update_project_should_persist_workflow_defaults(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _seed_provider_configs(db_session)
    create_resp = await client.post("/api/projects", json={"name": "带默认配置的项目"})
    project_id = create_resp.json()["data"]["id"]

    response = await client.put(
        f"/api/projects/{project_id}",
        json={
            "workflow_defaults": {
                "video_provider_key": "mock-video",
                "tts_provider_key": "mock-tts",
                "lipsync_provider_key": "mock-lipsync",
                "provider_payload_defaults": {
                    "video": {"seed": 7},
                    "tts": {"format": "mp3"},
                    "lipsync": {"fps": 25},
                },
            },
        },
    )

    assert response.status_code == 200
    defaults = response.json()["data"]["workflow_defaults"]
    assert defaults["video_provider_key"] == "mock-video"
    assert defaults["tts_provider_key"] == "mock-tts"
    assert defaults["lipsync_provider_key"] == "mock-lipsync"
    assert defaults["provider_payload_defaults"] == {
        "video": {"seed": 7},
        "tts": {"format": "mp3"},
        "lipsync": {"fps": 25},
    }


@pytest.mark.asyncio
async def test_update_project_should_merge_and_clear_workflow_defaults(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _seed_provider_configs(db_session)
    create_resp = await client.post("/api/projects", json={
        "name": "默认配置合并项目",
        "workflow_defaults": {
            "video_provider_key": "mock-video",
            "tts_provider_key": "mock-tts",
            "lipsync_provider_key": "mock-lipsync",
            "provider_payload_defaults": {
                "video": {"seed": 11},
                "tts": {"format": "mp3"},
                "lipsync": {"fps": 24},
            },
        },
    })
    project_id = create_resp.json()["data"]["id"]

    merge_resp = await client.put(
        f"/api/projects/{project_id}",
        json={
            "workflow_defaults": {
                "provider_payload_defaults": {
                    "tts": {"format": "wav"},
                },
            },
        },
    )
    assert merge_resp.status_code == 200
    merged_defaults = merge_resp.json()["data"]["workflow_defaults"]
    assert merged_defaults["video_provider_key"] == "mock-video"
    assert merged_defaults["tts_provider_key"] == "mock-tts"
    assert merged_defaults["lipsync_provider_key"] == "mock-lipsync"
    assert merged_defaults["provider_payload_defaults"] == {
        "video": {"seed": 11},
        "tts": {"format": "wav"},
        "lipsync": {"fps": 24},
    }

    clear_resp = await client.put(
        f"/api/projects/{project_id}",
        json={"workflow_defaults": None},
    )
    assert clear_resp.status_code == 200
    cleared_defaults = clear_resp.json()["data"]["workflow_defaults"]
    assert cleared_defaults == {
        "video_provider_key": None,
        "tts_provider_key": None,
        "lipsync_provider_key": None,
        "provider_payload_defaults": {
            "video": {},
            "tts": {},
            "lipsync": {},
        },
    }


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient):
    """删除项目"""
    create_resp = await client.post("/api/projects", json={"name": "待删除"})
    project_id = create_resp.json()["data"]["id"]

    response = await client.delete(f"/api/projects/{project_id}")
    assert response.status_code == 200

    # 确认已删除
    get_resp = await client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_get_nonexistent_project(client: AsyncClient):
    """查询不存在的项目"""
    response = await client.get("/api/projects/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_project_should_copy_character_structure(
    client: AsyncClient,
    db_session: AsyncSession,
):
    create_resp = await client.post("/api/projects", json={"name": "角色复制项目", "description": "角色结构描述"})
    source_id = create_resp.json()["data"]["id"]

    db_session.add_all([
        Character(
            project_id=source_id,
            name="角色A",
            appearance="短发，黑色风衣",
            personality="冷静果断",
            costume="黑色风衣",
        ),
        Character(
            project_id=source_id,
            name="角色B",
            appearance="白色长裙",
            personality="敏锐机警",
            costume="白色长裙",
        ),
    ])
    await db_session.commit()

    dup_resp = await client.post(f"/api/projects/{source_id}/duplicate")
    assert dup_resp.status_code == 200
    dup_id = dup_resp.json()["data"]["id"]
    assert dup_resp.json()["data"]["character_count"] == 2

    dup_characters = (await db_session.execute(
        select(Character).where(Character.project_id == dup_id).order_by(Character.name)
    )).scalars().all()
    assert [item.name for item in dup_characters] == ["角色A", "角色B"]
    assert [item.appearance for item in dup_characters] == ["短发，黑色风衣", "白色长裙"]
    assert [item.personality for item in dup_characters] == ["冷静果断", "敏锐机警"]


@pytest.mark.asyncio
async def test_duplicate_project_should_copy_workflow_defaults(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _seed_provider_configs(db_session)

    create_resp = await client.post("/api/projects", json={
        "name": "默认配置复制源",
        "workflow_defaults": {
            "video_provider_key": "mock-video",
            "tts_provider_key": "mock-tts",
            "lipsync_provider_key": "mock-lipsync",
            "provider_payload_defaults": {
                "video": {"seed": 99},
                "tts": {"format": "wav"},
                "lipsync": {"fps": 30},
            },
        },
    })
    source_id = create_resp.json()["data"]["id"]

    dup_resp = await client.post(f"/api/projects/{source_id}/duplicate")

    assert dup_resp.status_code == 200
    defaults = dup_resp.json()["data"]["workflow_defaults"]
    assert defaults["video_provider_key"] == "mock-video"
    assert defaults["tts_provider_key"] == "mock-tts"
    assert defaults["lipsync_provider_key"] == "mock-lipsync"
    assert defaults["provider_payload_defaults"] == {
        "video": {"seed": 99},
        "tts": {"format": "wav"},
        "lipsync": {"fps": 30},
    }


@pytest.mark.asyncio
async def test_get_project_workspace_should_return_aggregated_summary(
    client: AsyncClient,
    db_session: AsyncSession,
):
    create_resp = await client.post("/api/projects", json={"name": "工作台聚合项目"})
    project_id = create_resp.json()["data"]["id"]

    episode = Episode(
        project_id=project_id,
        episode_order=0,
        title="第1集",
        summary="第一集摘要",
        script_text="第一集正文",
        video_provider_key="mock-video",
    )
    character_entity = ScriptEntity(project_id=project_id, entity_type="character", name="主角")
    location_entity = ScriptEntity(project_id=project_id, entity_type="location", name="办公室")
    db_session.add_all([episode, character_entity, location_entity])
    await db_session.flush()

    panel = Panel(
        project_id=project_id,
        episode_id=episode.id,
        panel_order=0,
        title="分镜一",
        script_text="镜头内容",
        status="completed",
        video_url="/media/panel-1.mp4",
    )
    db_session.add(panel)
    await db_session.flush()

    db_session.add_all([
        ScriptEntityAssetBinding(
            project_id=project_id,
            entity_id=character_entity.id,
            asset_type="character",
            asset_id="character-asset-1",
            asset_name="主角立绘",
            is_primary=True,
        ),
        GlobalVoice(
            project_id=project_id,
            name="项目旁白",
            provider="mock-tts",
            voice_code="voice-001",
        ),
        VideoClip(
            panel_id=panel.id,
            clip_order=0,
            candidate_index=0,
            status="completed",
            is_selected=True,
        ),
        VideoClip(
            panel_id=panel.id,
            clip_order=0,
            candidate_index=1,
            status="failed",
            is_selected=False,
        ),
        CompositionTask(
            project_id=project_id,
            episode_id=episode.id,
            status="completed",
            duration_seconds=12.5,
        ),
    ])
    await db_session.commit()

    response = await client.get(f"/api/projects/{project_id}/workspace")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["project"]["id"] == project_id
    assert payload["project"]["workflow_defaults"]["video_provider_key"] is None
    assert payload["recommended_step"] == "assets"
    assert payload["recommended_episode_id"] == episode.id
    assert len(payload["episodes"]) == 1
    assert payload["episodes"][0]["id"] == episode.id
    assert payload["episodes"][0]["panel_count"] == 1
    assert payload["episodes"][0]["script_text"] == "第一集正文"
    assert payload["episodes"][0]["provider_payload_defaults"] == {
        "video": {},
        "tts": {},
        "lipsync": {},
    }
    assert payload["episodes"][0]["skipped_checks"] == []
    assert payload["resource_summary"] == {
        "character_entity_count": 1,
        "bound_character_entity_count": 1,
        "location_entity_count": 1,
        "bound_location_entity_count": 0,
        "voice_asset_count": 1,
        "panel_count": 1,
        "clip_count": 2,
        "ready_clip_count": 1,
        "failed_clip_count": 1,
        "composition_count": 1,
    }
    assert payload["latest_preview"]["duration_seconds"] == 12.5


@pytest.mark.asyncio
async def test_update_project_script_workspace_should_sync_project_and_episodes(
    client: AsyncClient,
    db_session: AsyncSession,
):
    await _seed_provider_configs(db_session)

    create_resp = await client.post("/api/projects", json={"name": "剧本分集工作台保存项目"})
    project_id = create_resp.json()["data"]["id"]

    existing_episode = Episode(
        project_id=project_id,
        episode_order=0,
        title="旧第1集",
        summary="旧摘要",
        script_text="旧正文",
        video_provider_key="mock-video",
    )
    stale_episode = Episode(
        project_id=project_id,
        episode_order=1,
        title="待删除分集",
        summary="待删除摘要",
        script_text="待删除正文",
    )
    db_session.add_all([existing_episode, stale_episode])
    await db_session.commit()
    existing_episode_id = existing_episode.id
    stale_episode_id = stale_episode.id

    response = await client.put(
        f"/api/projects/{project_id}/script-workspace",
        json={
            "script_text": "第1集 新标题\n第一集新正文\n\n第2集 第二标题\n第二集正文",
            "workflow_defaults": {
                "video_provider_key": "mock-video",
                "tts_provider_key": "mock-tts",
                "lipsync_provider_key": "mock-lipsync",
                "provider_payload_defaults": {
                    "video": {"seed": 7},
                    "tts": {"voice": "host"},
                    "lipsync": {"fps": 24},
                },
            },
            "episodes": [
                {
                    "id": existing_episode.id,
                    "title": "新第1集",
                    "summary": "第一集新摘要",
                    "script_text": "第一集新正文",
                    "video_provider_key": "mock-video",
                    "tts_provider_key": "mock-tts",
                    "lipsync_provider_key": None,
                    "provider_payload_defaults": {
                        "video": {"seed": 42},
                        "tts": {"voice": "lead"},
                    },
                    "skipped_checks": ["voice_ready", "voice_ready", "video_ready"],
                },
                {
                    "title": "新第2集",
                    "summary": "第二集新摘要",
                    "script_text": "第二集正文",
                    "video_provider_key": None,
                    "tts_provider_key": "mock-tts",
                    "lipsync_provider_key": "mock-lipsync",
                    "provider_payload_defaults": {
                        "lipsync": {"fps": 30},
                    },
                    "skipped_checks": ["asset_binding_ready"],
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["project"]["workflow_defaults"] == {
        "video_provider_key": "mock-video",
        "tts_provider_key": "mock-tts",
        "lipsync_provider_key": "mock-lipsync",
        "provider_payload_defaults": {
            "video": {"seed": 7},
            "tts": {"voice": "host"},
            "lipsync": {"fps": 24},
        },
    }
    assert [item["title"] for item in payload["episodes"]] == ["新第1集", "新第2集"]
    assert payload["episodes"][0]["id"] == existing_episode_id
    assert payload["episodes"][0]["provider_payload_defaults"] == {
        "video": {"seed": 42},
        "tts": {"voice": "lead"},
        "lipsync": {},
    }
    assert payload["episodes"][0]["skipped_checks"] == ["voice_ready", "video_ready"]
    assert payload["episodes"][1]["provider_payload_defaults"] == {
        "video": {},
        "tts": {},
        "lipsync": {"fps": 30},
    }

    db_session.expire_all()
    refreshed_project = (await db_session.execute(select(Project).where(Project.id == project_id))).scalar_one()
    assert refreshed_project.script_text == "第1集 新标题\n第一集新正文\n\n第2集 第二标题\n第二集正文"
    episode_rows = (await db_session.execute(
        select(Episode).where(Episode.project_id == project_id).order_by(Episode.episode_order)
    )).scalars().all()
    assert len(episode_rows) == 2
    assert [item.title for item in episode_rows] == ["新第1集", "新第2集"]
    assert stale_episode_id not in {item.id for item in episode_rows}


@pytest.mark.asyncio
async def test_update_project_script_workspace_should_reject_when_panels_exist(
    client: AsyncClient,
    db_session: AsyncSession,
):
    create_resp = await client.post("/api/projects", json={"name": "已有分镜阻断项目"})
    project_id = create_resp.json()["data"]["id"]

    episode = Episode(project_id=project_id, episode_order=0, title="第1集", script_text="旧正文")
    db_session.add(episode)
    await db_session.flush()
    episode_id = episode.id
    db_session.add(Panel(
        project_id=project_id,
        episode_id=episode_id,
        panel_order=0,
        title="已存在分镜",
        script_text="镜头内容",
    ))
    await db_session.commit()

    response = await client.put(
        f"/api/projects/{project_id}/script-workspace",
        json={
            "script_text": "第1集 新正文",
            "workflow_defaults": {
                "video_provider_key": None,
                "tts_provider_key": None,
                "lipsync_provider_key": None,
                "provider_payload_defaults": {
                    "video": {},
                    "tts": {},
                    "lipsync": {},
                },
            },
            "episodes": [
                {
                    "id": episode_id,
                    "title": "第1集",
                    "summary": None,
                    "script_text": "新正文",
                    "video_provider_key": None,
                    "tts_provider_key": None,
                    "lipsync_provider_key": None,
                    "provider_payload_defaults": {
                        "video": {},
                        "tts": {},
                        "lipsync": {},
                    },
                    "skipped_checks": [],
                },
            ],
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "当前项目已存在分镜，禁止从剧本分集页覆盖分集结构"

    db_session.expire_all()
    refreshed_project = (await db_session.execute(select(Project).where(Project.id == project_id))).scalar_one()
    refreshed_episode = (await db_session.execute(select(Episode).where(Episode.id == episode_id))).scalar_one()
    assert refreshed_project.script_text is None
    assert refreshed_episode.script_text == "旧正文"
