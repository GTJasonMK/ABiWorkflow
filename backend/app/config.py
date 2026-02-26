from __future__ import annotations

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings


_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def resolve_runtime_path(path_value: str | Path) -> Path:
    """将运行时路径解析为绝对路径，避免受当前工作目录影响。"""
    raw_path = Path(path_value).expanduser()
    if raw_path.is_absolute():
        return raw_path.resolve()
    return (_BACKEND_ROOT / raw_path).resolve()


def resolve_database_url(database_url: str) -> str:
    """将 sqlite 相对路径标准化为绝对路径，避免多进程 cwd 不一致。"""
    value = (database_url or "").strip()
    if not value:
        return value

    base, sep, query = value.partition("?")
    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if not base.startswith(prefix):
            continue

        raw_path = base[len(prefix):]
        path_like = Path(raw_path)
        is_memory_db = raw_path.startswith(":memory:") or raw_path.startswith("file:")
        is_absolute_db = raw_path.startswith("/") or path_like.is_absolute()
        if is_memory_db or is_absolute_db:
            return value

        resolved = resolve_runtime_path(raw_path).as_posix()
        # Windows 绝对路径 (E:/...) 不需要前导 /，Unix 绝对路径 (/...) 需要
        is_windows_drive = len(resolved) >= 2 and resolved[1] == ":"
        if not resolved.startswith("/") and not is_windows_drive:
            resolved = f"/{resolved}"
        rebuilt = f"{prefix}{resolved}"
        return f"{rebuilt}{sep}{query}" if sep else rebuilt

    return value


class Settings(BaseSettings):
    """应用配置，从环境变量和 .env 文件加载"""

    # 应用基础配置
    app_name: str = "AbiWorkflow"
    debug: bool = False

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./abi_workflow.db"

    # LLM 配置
    llm_provider: str = "openai"  # openai | anthropic | deepseek | ggk
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str | None = None
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"
    ggk_base_url: str = ""
    ggk_api_key: str = ""
    ggk_text_model: str = "grok-3"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # 视频生成
    video_provider: str = "mock"
    video_output_dir: str = "./outputs/videos"
    composition_output_dir: str = "./outputs/compositions"
    video_provider_max_duration_seconds: float = 6.0
    video_poll_interval_seconds: float = 1.0
    video_task_timeout_seconds: float = 300.0

    # 通用 HTTP 视频提供者（用于接入真实文生视频服务）
    video_http_base_url: str = ""
    video_http_api_key: str = ""
    video_http_generate_path: str = "/v1/video/generations"
    video_http_status_path: str = "/v1/video/generations/{task_id}"
    video_http_task_id_path: str = "task_id"
    video_http_status_value_path: str = "status"
    video_http_progress_path: str = "progress_percent"
    video_http_result_url_path: str = "result_url"
    video_http_error_path: str = "error_message"
    video_http_request_timeout_seconds: float = 60.0

    # GGK 视频提供者（当 VIDEO_PROVIDER=ggk 时使用）
    ggk_video_model: str = "grok-imagine-1.0-video"
    ggk_video_aspect_ratio: str = "16:9"
    ggk_video_resolution: str = "SD"
    ggk_video_preset: str = "normal"
    ggk_video_model_duration_profiles: str = ""
    ggk_request_timeout_seconds: float = 300.0

    # TTS
    tts_voice: str = "zh-CN-XiaoxiaoNeural"

    # 角色立绘生成（OpenAI 兼容 API，复用 ggk_base_url + ggk_api_key）
    portrait_image_model: str = "grok-imagine-1.0"
    portrait_output_dir: str = "./outputs/portraits"
    portrait_request_timeout_seconds: float = 120.0

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}

    @model_validator(mode="before")
    @classmethod
    def _empty_strings_to_defaults(cls, values: dict) -> dict:
        """空字符串回退为字段默认值。

        系统设置页面会将所有字段写入 .env，未填写的字段会变成空字符串，
        覆盖代码中有意义的默认值（如 video_output_dir='./outputs/videos'）。
        此验证器将空字符串还原为字段默认值，避免路径解析失败。
        """
        for field_name, field_info in cls.model_fields.items():
            if field_name in values and isinstance(values[field_name], str) and not values[field_name].strip():
                default = field_info.default
                if isinstance(default, str) and default:
                    values[field_name] = default
        return values


settings = Settings()


def reload_settings() -> None:
    """从 .env 文件重新加载配置到当前进程的 settings 单例。

    用于 Celery worker 等独立进程在任务执行前同步最新配置，
    避免 web 进程通过系统设置页面更新 .env 后 worker 仍使用旧值。
    """
    fresh = Settings()
    for field_name in Settings.model_fields:
        setattr(settings, field_name, getattr(fresh, field_name))
