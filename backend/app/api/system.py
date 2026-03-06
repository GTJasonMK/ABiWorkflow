from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.common import ApiResponse
from app.services.runtime_settings import (
    RuntimeSettingsValidationError,
    apply_runtime_updates,
    validate_runtime_business_rules,
    validate_runtime_updates,
)
from app.services.runtime_summary import build_runtime_summary
from app.tasks.health import has_celery_worker

router = APIRouter(prefix="/system", tags=["系统设置"])


class RuntimeSettingsUpdate(BaseModel):
    """系统运行配置更新请求（键集合由 Settings 统一约束）。"""

    model_config = {"extra": "allow"}


@router.get("/runtime", response_model=ApiResponse[dict])
async def get_runtime_summary():
    """返回前端可展示的运行配置摘要（不包含密钥明文）。"""
    summary = build_runtime_summary(celery_worker_online=has_celery_worker())
    return ApiResponse(data=summary)


@router.put("/runtime", response_model=ApiResponse[dict])
async def update_runtime_settings(body: RuntimeSettingsUpdate):
    """更新后端运行配置（写入 .env，并同步当前进程内设置）。"""
    raw_updates = dict(body.model_extra or {})
    if not raw_updates:
        return await get_runtime_summary()
    try:
        updates = validate_runtime_updates(raw_updates)
        validate_runtime_business_rules(updates)
    except RuntimeSettingsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    apply_runtime_updates(updates)
    return await get_runtime_summary()
