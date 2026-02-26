from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """管理 WebSocket 连接，按 project_id 分组"""

    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {}

    async def connect(self, project_id: str, websocket: WebSocket):
        await websocket.accept()
        if project_id not in self.active_connections:
            self.active_connections[project_id] = []
        self.active_connections[project_id].append(websocket)
        logger.info("WebSocket 连接建立: project=%s", project_id)

    def disconnect(self, project_id: str, websocket: WebSocket):
        if project_id in self.active_connections:
            connections = self.active_connections[project_id]
            if websocket in connections:
                connections.remove(websocket)
            if not connections:
                del self.active_connections[project_id]
        logger.info("WebSocket 连接断开: project=%s", project_id)


manager = ConnectionManager()


@router.websocket("/ws/progress/{project_id}")
async def websocket_progress(websocket: WebSocket, project_id: str):
    """WebSocket 进度推送端点：订阅 Redis 频道，转发消息到客户端"""
    await manager.connect(project_id, websocket)

    redis_client = aioredis.from_url(settings.redis_url)
    pubsub = redis_client.pubsub()

    try:
        await pubsub.subscribe(f"progress:{project_id}")

        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                data = json.loads(message["data"])
                await websocket.send_json(data)

            # 检查 WebSocket 是否有消息（心跳等）
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.01)
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket 错误: %s", e)
    finally:
        manager.disconnect(project_id, websocket)
        await pubsub.unsubscribe(f"progress:{project_id}")
        await pubsub.close()
        await redis_client.close()
