from __future__ import annotations

from celery.result import AsyncResult
from fastapi import APIRouter

from app.schemas.common import ApiResponse
from app.tasks.celery_app import celery_app

router = APIRouter(prefix="/tasks", tags=["任务状态"])


@router.get("/{task_id}", response_model=ApiResponse[dict])
async def get_task_status(task_id: str):
    """查询后台任务状态（Celery AsyncResult）。"""
    result = AsyncResult(task_id, app=celery_app)

    payload: dict = {
        "task_id": task_id,
        "state": result.state.lower(),
        "ready": result.ready(),
        "successful": result.successful() if result.ready() else False,
    }

    if result.ready():
        if result.successful():
            task_result = result.result
            payload["result"] = task_result if isinstance(task_result, dict) else {"value": str(task_result)}
        else:
            payload["error"] = str(result.result)

    return ApiResponse(data=payload)

