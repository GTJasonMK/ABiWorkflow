from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_QUEUE_MODE_REDIS = "redis"


@dataclass
class QueueRuntimeState:
    """任务队列运行态。"""

    mode: str = _QUEUE_MODE_REDIS
    redis_available: bool = True
    initialized: bool = False


_state_lock = threading.Lock()
_runtime_state = QueueRuntimeState()


def _probe_redis(url: str) -> tuple[bool, str | None]:
    value = (url or "").strip()
    if not value:
        return False, "redis_url 为空"

    client = None
    try:
        client = redis.from_url(
            value,
            socket_connect_timeout=0.6,
            socket_timeout=0.6,
            health_check_interval=0,
        )
        client.ping()
        return True, None
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass


def ensure_queue_backend_ready(*, force_refresh: bool = False) -> QueueRuntimeState:
    """刷新并返回当前 Redis 队列可用性。"""
    with _state_lock:
        if _runtime_state.initialized and not force_refresh:
            return QueueRuntimeState(**_runtime_state.__dict__)

        redis_ok, redis_err = _probe_redis(settings.redis_url)
        _runtime_state.mode = _QUEUE_MODE_REDIS
        _runtime_state.redis_available = redis_ok
        _runtime_state.initialized = True

        if not redis_ok:
            logger.warning("Redis 不可用，异步任务与 Redis 进度推送当前不可用: %s", redis_err or "unknown")

        return QueueRuntimeState(**_runtime_state.__dict__)


def get_queue_runtime_state() -> QueueRuntimeState:
    """返回当前任务队列运行态。"""
    state = ensure_queue_backend_ready()
    return QueueRuntimeState(**state.__dict__)


def redis_progress_enabled() -> bool:
    """当前是否可用 Redis 进度推送。"""
    state = ensure_queue_backend_ready()
    return state.mode == _QUEUE_MODE_REDIS and state.redis_available
