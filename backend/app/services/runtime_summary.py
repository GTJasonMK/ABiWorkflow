from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

from app.config import settings
from app.services.json_codec import from_json_text
from app.services.queue_runtime import get_queue_runtime_state


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


def build_runtime_summary(*, celery_worker_online: bool) -> dict[str, object]:
    """组装前端系统设置页使用的运行时摘要。"""
    llm_key_configured = bool(settings.llm_api_key)
    queue_state = get_queue_runtime_state()

    return {
        "app": {
            "name": settings.app_name,
            "debug": settings.debug,
            "database_url": _mask_url_credentials(settings.database_url),
        },
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.llm_model,
            "base_url": settings.llm_base_url,
            "api_key_configured": llm_key_configured,
            "api_key_preview": _mask_key_preview(settings.llm_api_key),
        },
        "queue": {
            "redis_url": _mask_url_credentials(settings.redis_url),
            "celery_broker_url": _mask_url_credentials(settings.celery_broker_url),
            "celery_result_backend": _mask_url_credentials(settings.celery_result_backend),
            "celery_worker_online": celery_worker_online,
            "queue_mode": queue_state.mode,
            "redis_available": queue_state.redis_available,
        },
        "video": {
            "provider": settings.video_provider,
            "output_dir": settings.video_output_dir,
            "composition_output_dir": settings.composition_output_dir,
            "provider_max_duration_seconds": settings.video_provider_max_duration_seconds,
            "poll_interval_seconds": settings.video_poll_interval_seconds,
            "task_timeout_seconds": settings.video_task_timeout_seconds,
            "project_asset_publish_global_default": settings.project_asset_publish_global_default,
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
                "base_url": settings.ggk_base_url,
                "api_key_configured": bool(settings.ggk_api_key),
                "api_key_preview": _mask_key_preview(settings.ggk_api_key),
                "video_model": settings.ggk_video_model,
                "aspect_ratio": settings.ggk_video_aspect_ratio,
                "resolution": settings.ggk_video_resolution,
                "preset": settings.ggk_video_preset,
                "model_duration_profiles": settings.ggk_video_model_duration_profiles,
                "request_timeout_seconds": settings.ggk_request_timeout_seconds,
            },
            "portrait": {
                "api_base_url": settings.portrait_api_base_url,
                "api_key_configured": bool(settings.portrait_api_key),
                "api_key_preview": _mask_key_preview(settings.portrait_api_key),
                "image_model": settings.portrait_image_model,
            },
        },
        "models": {
            "default_bindings": from_json_text(settings.default_model_bindings, {}),
            "capability_profiles": from_json_text(settings.model_capability_profiles, {}),
        },
    }
