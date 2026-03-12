from __future__ import annotations

from app.tasks.celery_app import celery_app


def has_celery_worker() -> bool:
    """检测当前是否有可用 Celery worker。"""
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        ping_result = inspector.ping() if inspector is not None else None
        return bool(ping_result)
    except Exception:
        return False
