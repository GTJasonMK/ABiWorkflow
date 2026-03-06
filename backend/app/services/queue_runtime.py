from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import redis

from app.config import resolve_runtime_path, settings
from app.services.progress import reset_redis_client

logger = logging.getLogger(__name__)

_QUEUE_MODE_REDIS = "redis"
_QUEUE_MODE_SQLITE = "sqlite"
_QUEUE_FALLBACK_DB = "./outputs/queue/celery-fallback.db"


@dataclass
class QueueRuntimeState:
    """任务队列运行态（用于系统摘要与降级判断）。"""

    mode: str = _QUEUE_MODE_REDIS
    redis_available: bool = True
    fallback_active: bool = False
    fallback_reason: str | None = None
    initialized: bool = False


_state_lock = threading.Lock()
_runtime_state = QueueRuntimeState()


def _build_sqlite_queue_urls() -> tuple[str, str]:
    queue_db = resolve_runtime_path(_QUEUE_FALLBACK_DB)
    queue_db.parent.mkdir(parents=True, exist_ok=True)
    db_path = queue_db.resolve().as_posix()
    broker_url = f"sqla+sqlite:///{db_path}"
    result_backend = f"db+sqlite:///{db_path}"
    return broker_url, result_backend


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


def _configure_celery_backend(broker_url: str, result_backend: str) -> None:
    try:
        from app.tasks.celery_app import configure_backend_urls

        configure_backend_urls(broker_url, result_backend)
    except Exception as exc:  # noqa: BLE001
        # 某些进程（如仅运行 API 的测试）未加载 Celery，不阻断主流程。
        logger.debug("Celery 配置热切换跳过: %s", exc)


def ensure_queue_backend_ready(*, force_refresh: bool = False, apply_celery_runtime: bool = True) -> QueueRuntimeState:
    """确保任务队列可用：Redis 不可达时自动降级为 SQLite broker/backend。"""
    with _state_lock:
        if _runtime_state.initialized and not force_refresh:
            return QueueRuntimeState(**_runtime_state.__dict__)

        redis_ok, redis_err = _probe_redis(settings.redis_url)
        if redis_ok:
            _runtime_state.mode = _QUEUE_MODE_REDIS
            _runtime_state.redis_available = True
            _runtime_state.fallback_active = False
            _runtime_state.fallback_reason = None
            _runtime_state.initialized = True
            return QueueRuntimeState(**_runtime_state.__dict__)

        broker_url, result_backend = _build_sqlite_queue_urls()
        settings.celery_broker_url = broker_url
        settings.celery_result_backend = result_backend
        reset_redis_client()
        if apply_celery_runtime:
            _configure_celery_backend(broker_url, result_backend)

        reason = redis_err or "Redis 不可用"
        _runtime_state.mode = _QUEUE_MODE_SQLITE
        _runtime_state.redis_available = False
        _runtime_state.fallback_active = True
        _runtime_state.fallback_reason = reason
        _runtime_state.initialized = True

        logger.warning(
            "Redis 不可用，任务队列自动降级为 SQLite。broker=%s, backend=%s, reason=%s",
            broker_url,
            result_backend,
            reason,
        )
        return QueueRuntimeState(**_runtime_state.__dict__)


def get_queue_runtime_state() -> QueueRuntimeState:
    """返回当前任务队列运行态。"""
    state = ensure_queue_backend_ready()
    return QueueRuntimeState(**state.__dict__)


def redis_progress_enabled() -> bool:
    """当前是否可用 Redis 进度推送。"""
    state = ensure_queue_backend_ready()
    return state.mode == _QUEUE_MODE_REDIS and state.redis_available
