from __future__ import annotations

from app.tasks.health import has_celery_worker


def resolve_async_mode(async_mode: bool) -> bool:
    """解析是否启用异步模式：仅在显式请求且 worker 在线时返回 True。"""
    return bool(async_mode and has_celery_worker())
