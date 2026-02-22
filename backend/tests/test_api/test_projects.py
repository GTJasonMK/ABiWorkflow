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
