from __future__ import annotations

from app.services.queue_runtime import ensure_queue_backend_ready
from app.tasks.celery_app import celery_app


def has_celery_worker() -> bool:
    """检测当前是否有可用 Celery worker。"""
    ensure_queue_backend_ready()
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        ping_result = inspector.ping() if inspector is not None else None
        return bool(ping_result)
    except Exception:
        return False
