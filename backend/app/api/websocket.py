from __future__ import annotations

import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.config import settings
from app.services.queue_runtime import redis_progress_enabled

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

    redis_client = None
    pubsub = None
    redis_ready = False
    channel = f"progress:{project_id}"

    try:
        if redis_progress_enabled():
            redis_client = aioredis.from_url(settings.redis_url)
            try:
                await redis_client.ping()
                pubsub = redis_client.pubsub()
                await pubsub.subscribe(channel)
                redis_ready = True
            except Exception as e:  # noqa: BLE001
                logger.warning("Redis 不可用，WebSocket 进度降级: %s", e)
                await websocket.send_json({
                    "type": "progress_unavailable",
                    "data": {"message": "实时进度暂不可用（Redis 未连接）"},
                })
        else:
            await websocket.send_json({
                "type": "progress_unavailable",
                "data": {"message": "实时进度暂不可用（Redis 未连接）"},
            })

        while True:
            if redis_ready and pubsub is not None:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message.get("type") == "message":
                    data = json.loads(message["data"])
                    await websocket.send_json(data)

            # 检查 WebSocket 是否有消息（心跳等）
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=0.2 if redis_ready else 1.0)
            except asyncio.TimeoutError:
                pass

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("WebSocket 错误: %s", e)
    finally:
        manager.disconnect(project_id, websocket)
        if pubsub is not None:
            try:
                await pubsub.unsubscribe(channel)
            except Exception:  # noqa: BLE001
                pass
            try:
                await pubsub.close()
            except Exception:  # noqa: BLE001
                pass
        if redis_client is not None:
            try:
                await redis_client.close()
            except Exception:  # noqa: BLE001
                pass
