from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Episode, Panel, Scene


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
    """项目统计只使用 Panel，不再回退 Scene。"""
    create_resp = await client.post("/api/projects", json={"name": "仅场景项目"})
    project_id = create_resp.json()["data"]["id"]

    db_session.add(Scene(
        project_id=project_id,
        sequence_order=0,
        title="历史场景",
        video_prompt="legacy prompt",
        duration_seconds=5.0,
        status="generated",
    ))
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
