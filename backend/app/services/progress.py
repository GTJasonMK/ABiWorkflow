from __future__ import annotations

import json
import logging

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_redis_client: redis.Redis | None = None
_redis_unavailable = False
_redis_url_snapshot: str = ""


def reset_redis_client() -> None:
    """重置 Redis 客户端缓存，使下次调用 get_redis_sync 时重新连接。

    在配置热重载后调用，确保 redis_url 变更能生效。
    """
    global _redis_client, _redis_unavailable, _redis_url_snapshot
    if _redis_client is not None:
        try:
            _redis_client.close()
        except Exception:  # noqa: BLE001
            pass
    _redis_client = None
    _redis_unavailable = False
    _redis_url_snapshot = ""


def get_redis_sync() -> redis.Redis | None:
    """获取同步 Redis 客户端（Celery 任务中使用）"""
    global _redis_client, _redis_unavailable, _redis_url_snapshot
    current_url = settings.redis_url

    # redis_url 发生变更时，丢弃旧连接。
    if _redis_url_snapshot and _redis_url_snapshot != current_url:
        reset_redis_client()

    if _redis_unavailable:
        return None

    if _redis_client is None:
        try:
            _redis_client = redis.from_url(current_url)
            _redis_client.ping()
            _redis_url_snapshot = current_url
        except Exception as e:  # noqa: BLE001 - 进度通知不应影响主链路
            _redis_unavailable = True
            logger.warning("Redis 不可用，已降级为无进度推送模式: %s", e)
            return None
    return _redis_client


def publish_progress(project_id: str, event_type: str, data: dict) -> None:
    """通过 Redis pub/sub 发布进度消息（同步版本，在 Celery 任务中调用）"""
    client = get_redis_sync()
    if client is None:
        return

    message = {
        "type": event_type,
        "data": data,
    }
    try:
        client.publish(f"progress:{project_id}", json.dumps(message, ensure_ascii=False))
        logger.debug("已发布进度: project=%s, type=%s", project_id, event_type)
    except Exception as e:  # noqa: BLE001 - 进度通知不应影响主链路
        logger.warning("进度消息发布失败，已忽略: project=%s, type=%s, err=%s", project_id, event_type, e)
