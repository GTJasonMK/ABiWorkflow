from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_compose_should_require_panels(client: AsyncClient):
    create_resp = await client.post("/api/projects", json={"name": "合成校验项目"})
    project_id = create_resp.json()["data"]["id"]

    response = await client.post(f"/api/projects/{project_id}/compose", json={})
    assert response.status_code == 400
    assert "没有可合成的分镜" in response.json()["detail"]
