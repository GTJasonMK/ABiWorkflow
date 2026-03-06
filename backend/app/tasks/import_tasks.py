from __future__ import annotations

from app.services.episode_import import split_with_llm
from app.tasks.celery_app import celery_app
from app.tasks.status_recovery import (
    mark_worker_task_completed,
    mark_worker_task_failed,
    mark_worker_task_started,
    run_async_in_new_loop,
)


@celery_app.task(bind=True, name="split_episodes_llm")
def split_episodes_llm_task(self, project_id: str, content: str):
    """异步执行 AI 分集（失败自动回退到规则切分）。"""
    from app.config import reload_settings

    reload_settings()
    mark_worker_task_started(self.request.id, "AI 分集任务开始执行", progress_percent=5.0)

    try:
        result = run_async_in_new_loop(_run_split(content))
        mark_worker_task_completed(self.request.id, f"AI 分集完成，共 {len(result.get('episodes') or [])} 集", result)
        return {"project_id": project_id, **result}
    except Exception as exc:  # noqa: BLE001
        mark_worker_task_failed(self.request.id, "AI 分集任务失败", str(exc))
        raise


async def _run_split(content: str) -> dict:
    result = await split_with_llm(content)
    return {
        "method": result.get("method"),
        "confidence": result.get("confidence"),
        "episodes": result.get("episodes") or [],
    }
