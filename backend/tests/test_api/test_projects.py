from __future__ import annotations

import pytest
from httpx import AsyncClient


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
    data = response.json()["data"]
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
