from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.schemas.common import ApiResponse
from app.services.ggk_autoconfig import discover_ggk_runtime_config
from app.services.runtime_settings import (
    RuntimeSettingsValidationError,
    apply_runtime_updates,
    auto_import_ggk_if_needed,
    collect_ggk_updates_from_discovery,
    validate_runtime_business_rules,
    validate_runtime_updates,
)
from app.services.runtime_summary import build_runtime_summary
from app.tasks.health import has_celery_worker

router = APIRouter(prefix="/system", tags=["系统设置"])


class RuntimeSettingsUpdate(BaseModel):
    """系统运行配置更新请求（键集合由 Settings 统一约束）。"""

    model_config = {"extra": "allow"}


class GgkImportRequest(BaseModel):
    """从本地 GGK 项目导入配置请求。"""

    project_path: str | None = None
    base_url: str | None = None
    prefer_internal_key: bool = False
    auto_switch_provider: bool = True


@router.get("/runtime", response_model=ApiResponse[dict])
async def get_runtime_summary():
    """返回前端可展示的运行配置摘要（不包含密钥明文）。"""
    await auto_import_ggk_if_needed()
    summary = build_runtime_summary(celery_worker_online=has_celery_worker())
    return ApiResponse(data=summary)


@router.post("/ggk/import", response_model=ApiResponse[dict])
async def import_settings_from_ggk(body: GgkImportRequest):
    """从本地 GGK 项目导入连接配置，并可自动切换 provider。"""
    discovery = await discover_ggk_runtime_config(
        explicit_project_path=body.project_path,
        explicit_base_url=body.base_url,
        prefer_internal_key=body.prefer_internal_key,
    )

    if not discovery.get("found"):
        reason = str(discovery.get("reason") or "未找到 GGK 项目")
        raise HTTPException(status_code=404, detail=reason)

    base_url = str(discovery.get("base_url") or "").strip()
    api_key = str(discovery.get("api_key") or "").strip()
    if not base_url:
        raise HTTPException(status_code=400, detail="未能解析 GGK Base URL，请手动指定 base_url")
    if not api_key:
        raise HTTPException(status_code=400, detail="未能从 GGK 数据库读取可用 API Key")

    updates = collect_ggk_updates_from_discovery(discovery)

    if body.auto_switch_provider:
        updates["llm_provider"] = "ggk"
        updates["video_provider"] = "ggk"

    try:
        updates = validate_runtime_updates(updates)
    except RuntimeSettingsValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    apply_runtime_updates(updates)
    runtime = (await get_runtime_summary()).data

    return ApiResponse(data={
        "imported": True,
        "source": {
            "project_path": discovery.get("project_path"),
            "env_path": discovery.get("env_path"),
            "db_path": discovery.get("db_path"),
            "api_key_source": discovery.get("api_key_source"),
            "base_url_reachable": discovery.get("base_url_reachable"),
        },
        "runtime": runtime,
    })


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
