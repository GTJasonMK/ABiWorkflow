from __future__ import annotations

import json
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None


def get_redis_sync() -> redis.Redis:
    """获取同步 Redis 客户端（Celery 任务中使用）"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url)
    return _redis_client


def publish_progress(project_id: str, event_type: str, data: dict) -> None:
    """通过 Redis pub/sub 发布进度消息（同步版本，在 Celery 任务中调用）"""
    client = get_redis_sync()
    message = {
        "type": event_type,
        "data": data,
    }
    client.publish(f"progress:{project_id}", json.dumps(message, ensure_ascii=False))
    logger.debug("已发布进度: project=%s, type=%s", project_id, event_type)
