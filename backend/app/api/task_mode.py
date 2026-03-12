from __future__ import annotations

from fastapi import HTTPException

from app.tasks.health import has_celery_worker


def resolve_async_mode(async_mode: bool, *, fallback_to_sync: bool = False) -> bool:
    """解析异步模式：请求异步时必须有可用 worker。"""
    if not async_mode:
        return False
    if not has_celery_worker():
        if fallback_to_sync:
            return False
        raise HTTPException(status_code=409, detail="当前没有可用的 Celery worker，无法异步执行")
    return True
