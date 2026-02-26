from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import Settings, settings
from app.schemas.common import ApiResponse
from app.services.ggk_autoconfig import discover_ggk_runtime_config
from app.tasks.health import has_celery_worker

router = APIRouter(prefix="/system", tags=["系统设置"])
_ggk_auto_import_attempted = False


class RuntimeSettingsUpdate(BaseModel):
    """系统运行配置更新请求（仅包含允许在线更新的字段）。"""

    app_name: str | None = None
    debug: bool | None = None
    database_url: str | None = None

    llm_provider: str | None = Field(default=None, description="openai | anthropic | deepseek | ggk")
    openai_api_key: str | None = None
    openai_model: str | None = None
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str | None = None
    deepseek_api_key: str | None = None
    deepseek_base_url: str | None = None
    deepseek_model: str | None = None
    ggk_base_url: str | None = None
    ggk_api_key: str | None = None
    ggk_text_model: str | None = None

    redis_url: str | None = None
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    video_provider: str | None = None
    video_output_dir: str | None = None
    composition_output_dir: str | None = None
    video_provider_max_duration_seconds: float | None = None
    video_poll_interval_seconds: float | None = None
    video_task_timeout_seconds: float | None = None

    video_http_base_url: str | None = None
    video_http_api_key: str | None = None
    video_http_generate_path: str | None = None
    video_http_status_path: str | None = None
    video_http_task_id_path: str | None = None
    video_http_status_value_path: str | None = None
    video_http_progress_path: str | None = None
    video_http_result_url_path: str | None = None
    video_http_error_path: str | None = None
    video_http_request_timeout_seconds: float | None = None
    ggk_video_model: str | None = None
    ggk_video_aspect_ratio: str | None = None
    ggk_video_resolution: str | None = None
    ggk_video_preset: str | None = None
    ggk_video_model_duration_profiles: str | None = None
    ggk_request_timeout_seconds: float | None = None

    tts_voice: str | None = None


class GgkImportRequest(BaseModel):
    """从本地 GGK 项目导入配置请求。"""

    project_path: str | None = None
    base_url: str | None = None
    prefer_internal_key: bool = False
    auto_switch_provider: bool = True


def _active_llm_model() -> str:
    if settings.llm_provider == "openai":
        return settings.openai_model
    if settings.llm_provider == "anthropic":
        return settings.anthropic_model
    if settings.llm_provider == "deepseek":
        return settings.deepseek_model
    if settings.llm_provider == "ggk":
        return settings.ggk_text_model
    return "unknown"


def _mask_key_preview(secret: str) -> str | None:
    """返回密钥掩码预览，避免泄漏明文。"""
    value = secret.strip()
    if not value:
        return None
    tail = value[-4:] if len(value) >= 4 else value
    return f"***{tail}"


def _mask_url_credentials(url: str) -> str:
    """脱敏连接 URL 中的用户名密码，仅保留主机与路径。"""
    value = url.strip()
    if not value:
        return value
    parsed = urlsplit(value)
    if not parsed.netloc or "@" not in parsed.netloc:
        return value

    _, host_part = parsed.netloc.rsplit("@", 1)
    return urlunsplit((parsed.scheme, f"***:***@{host_part}", parsed.path, parsed.query, parsed.fragment))


def _serialize_env_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _resolve_env_file_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".env"


def _merge_env_updates(env_file: Path, updates: dict[str, object]) -> None:
    """增量写入 .env：保留注释与现有顺序，仅覆盖/追加目标键。"""
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    key_to_index: dict[str, int] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key:
            key_to_index[key] = index

    for env_key, value in updates.items():
        rendered = f"{env_key}={_serialize_env_value(value)}"
        if env_key in key_to_index:
            lines[key_to_index[env_key]] = rendered
        else:
            lines.append(rendered)

    env_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _apply_runtime_updates(updates: dict[str, object]) -> None:
    env_updates: dict[str, object] = {}
    for field_name, value in updates.items():
        # 跳过空字符串覆盖有非空默认值的字段，
        # 防止前端表单空值通过 .env 清除代码默认值
        if isinstance(value, str) and not value.strip():
            field_info = Settings.model_fields.get(field_name)
            if field_info is not None:
                default = field_info.default
                if isinstance(default, str) and default.strip():
                    continue

        env_key = field_name.upper()
        env_updates[env_key] = value
        setattr(settings, field_name, value)

    _merge_env_updates(_resolve_env_file_path(), env_updates)


async def _auto_import_ggk_if_needed() -> None:
    """当 GGK 关键配置缺失时，尝试从同级 GGK 项目自动导入。"""
    global _ggk_auto_import_attempted
    if _ggk_auto_import_attempted:
        return
    _ggk_auto_import_attempted = True

    if os.getenv("ABI_DISABLE_GGK_AUTO_IMPORT", "").strip().lower() in {"1", "true", "yes"}:
        return

    has_ggk_base = bool(str(settings.ggk_base_url).strip())
    has_ggk_key = bool(str(settings.ggk_api_key).strip())
    if has_ggk_base and has_ggk_key:
        return

    try:
        discovery = await discover_ggk_runtime_config()
    except Exception:  # noqa: BLE001
        return

    if not discovery.get("found") or not str(discovery.get("api_key") or "").strip():
        return
    if not str(discovery.get("base_url") or "").strip():
        return

    updates: dict[str, object] = {}
    if not has_ggk_base:
        updates["ggk_base_url"] = str(discovery["base_url"])
    if not has_ggk_key:
        updates["ggk_api_key"] = str(discovery["api_key"])

    text_model = str(discovery.get("ggk_text_model") or "").strip()
    if text_model:
        updates["ggk_text_model"] = text_model

    video_model = str(discovery.get("ggk_video_model") or "").strip()
    if video_model:
        updates["ggk_video_model"] = video_model
    aspect_ratio = str(discovery.get("ggk_video_aspect_ratio") or "").strip()
    if aspect_ratio:
        updates["ggk_video_aspect_ratio"] = aspect_ratio
    resolution = str(discovery.get("ggk_video_resolution") or "").strip()
    if resolution:
        updates["ggk_video_resolution"] = resolution
    preset = str(discovery.get("ggk_video_preset") or "").strip()
    if preset:
        updates["ggk_video_preset"] = preset

    duration_profiles = str(discovery.get("ggk_video_model_duration_profiles") or "").strip()
    if duration_profiles:
        updates["ggk_video_model_duration_profiles"] = duration_profiles

    if settings.llm_provider == "openai" and not str(settings.openai_api_key).strip():
        updates["llm_provider"] = "ggk"
    if settings.video_provider == "mock":
        updates["video_provider"] = "ggk"

    if updates:
        _apply_runtime_updates(updates)


@router.get("/runtime", response_model=ApiResponse[dict])
async def get_runtime_summary():
    """返回前端可展示的运行配置摘要（不包含密钥明文）。"""
    await _auto_import_ggk_if_needed()

    openai_key_configured = bool(settings.openai_api_key)
    anthropic_key_configured = bool(settings.anthropic_api_key)
    deepseek_key_configured = bool(settings.deepseek_api_key)
    ggk_key_configured = bool(settings.ggk_api_key)

    celery_online = has_celery_worker()
    active_model = _active_llm_model()
    llm_key_configured = bool(
        openai_key_configured or anthropic_key_configured or deepseek_key_configured or ggk_key_configured
    )

    return ApiResponse(data={
        "app": {
            "name": settings.app_name,
            "debug": settings.debug,
            "database_url": _mask_url_credentials(settings.database_url),
        },
        "llm": {
            "provider": settings.llm_provider,
            "active_model": active_model,
            "any_key_configured": llm_key_configured,
            "openai": {
                "model": settings.openai_model,
                "base_url": settings.openai_base_url,
                "api_key_configured": openai_key_configured,
                "api_key_preview": _mask_key_preview(settings.openai_api_key),
            },
            "anthropic": {
                "model": settings.anthropic_model,
                "api_key_configured": anthropic_key_configured,
                "api_key_preview": _mask_key_preview(settings.anthropic_api_key),
            },
            "deepseek": {
                "model": settings.deepseek_model,
                "base_url": settings.deepseek_base_url,
                "api_key_configured": deepseek_key_configured,
                "api_key_preview": _mask_key_preview(settings.deepseek_api_key),
            },
            "ggk": {
                "base_url": settings.ggk_base_url,
                "text_model": settings.ggk_text_model,
                "api_key_configured": ggk_key_configured,
                "api_key_preview": _mask_key_preview(settings.ggk_api_key),
            },
        },
        "queue": {
            "redis_url": _mask_url_credentials(settings.redis_url),
            "celery_broker_url": _mask_url_credentials(settings.celery_broker_url),
            "celery_result_backend": _mask_url_credentials(settings.celery_result_backend),
            "celery_worker_online": celery_online,
        },
        "video": {
            "provider": settings.video_provider,
            "output_dir": settings.video_output_dir,
            "composition_output_dir": settings.composition_output_dir,
            "provider_max_duration_seconds": settings.video_provider_max_duration_seconds,
            "poll_interval_seconds": settings.video_poll_interval_seconds,
            "task_timeout_seconds": settings.video_task_timeout_seconds,
            "tts_voice": settings.tts_voice,
            "http_provider": {
                "base_url": settings.video_http_base_url,
                "api_key_configured": bool(settings.video_http_api_key),
                "api_key_preview": _mask_key_preview(settings.video_http_api_key),
                "generate_path": settings.video_http_generate_path,
                "status_path": settings.video_http_status_path,
                "task_id_path": settings.video_http_task_id_path,
                "status_value_path": settings.video_http_status_value_path,
                "progress_path": settings.video_http_progress_path,
                "result_url_path": settings.video_http_result_url_path,
                "error_path": settings.video_http_error_path,
                "request_timeout_seconds": settings.video_http_request_timeout_seconds,
            },
            "ggk_provider": {
                "video_model": settings.ggk_video_model,
                "aspect_ratio": settings.ggk_video_aspect_ratio,
                "resolution": settings.ggk_video_resolution,
                "preset": settings.ggk_video_preset,
                "model_duration_profiles": settings.ggk_video_model_duration_profiles,
                "request_timeout_seconds": settings.ggk_request_timeout_seconds,
            },
        },
        # 兼容旧前端字段
        "app_name": settings.app_name,
        "debug": settings.debug,
        "llm_provider": settings.llm_provider,
        "llm_model": active_model,
        "llm_key_configured": llm_key_configured,
        "video_provider": settings.video_provider,
        "redis_url": _mask_url_credentials(settings.redis_url),
        "celery_worker_online": celery_online,
        "video_output_dir": settings.video_output_dir,
        "composition_output_dir": settings.composition_output_dir,
    })


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

    updates: dict[str, object] = {
        "ggk_base_url": base_url,
        "ggk_api_key": api_key,
    }

    text_model = str(discovery.get("ggk_text_model") or "").strip()
    if text_model:
        updates["ggk_text_model"] = text_model

    video_model = str(discovery.get("ggk_video_model") or "").strip()
    if video_model:
        updates["ggk_video_model"] = video_model
    aspect_ratio = str(discovery.get("ggk_video_aspect_ratio") or "").strip()
    if aspect_ratio:
        updates["ggk_video_aspect_ratio"] = aspect_ratio
    resolution = str(discovery.get("ggk_video_resolution") or "").strip()
    if resolution:
        updates["ggk_video_resolution"] = resolution
    preset = str(discovery.get("ggk_video_preset") or "").strip()
    if preset:
        updates["ggk_video_preset"] = preset
    duration_profiles = str(discovery.get("ggk_video_model_duration_profiles") or "").strip()
    if duration_profiles:
        updates["ggk_video_model_duration_profiles"] = duration_profiles

    if body.auto_switch_provider:
        updates["llm_provider"] = "ggk"
        updates["video_provider"] = "ggk"

    _apply_runtime_updates(updates)
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
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        return await get_runtime_summary()

    if "llm_provider" in updates and updates["llm_provider"] not in {"openai", "anthropic", "deepseek", "ggk"}:
        raise HTTPException(status_code=400, detail="llm_provider 必须是 openai / anthropic / deepseek / ggk")

    if "video_provider" in updates and not str(updates["video_provider"]).strip():
        raise HTTPException(status_code=400, detail="video_provider 不能为空")

    def _effective(name: str) -> object:
        if name in updates:
            return updates[name]
        return getattr(settings, name)

    if _effective("llm_provider") == "ggk":
        if not str(_effective("ggk_base_url") or "").strip():
            raise HTTPException(status_code=400, detail="llm_provider=ggk 时必须配置 GGK_BASE_URL")
        if not str(_effective("ggk_api_key") or "").strip():
            raise HTTPException(status_code=400, detail="llm_provider=ggk 时必须配置 GGK_API_KEY")

    if _effective("video_provider") == "ggk":
        if not str(_effective("ggk_base_url") or "").strip():
            raise HTTPException(status_code=400, detail="video_provider=ggk 时必须配置 GGK_BASE_URL")
        if not str(_effective("ggk_api_key") or "").strip():
            raise HTTPException(status_code=400, detail="video_provider=ggk 时必须配置 GGK_API_KEY")

    if "ggk_video_model_duration_profiles" in updates:
        try:
            from app.video_providers.ggk_provider import parse_model_duration_profiles

            parse_model_duration_profiles(str(updates["ggk_video_model_duration_profiles"] or ""))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"ggk_video_model_duration_profiles 配置非法: {exc}") from exc

    _apply_runtime_updates(updates)
    return await get_runtime_summary()
