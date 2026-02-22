from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置，从环境变量和 .env 文件加载"""

    # 应用基础配置
    app_name: str = "AbiWorkflow"
    debug: bool = False

    # 数据库
    database_url: str = "sqlite+aiosqlite:///./abi_workflow.db"

    # LLM 配置
    llm_provider: str = "openai"  # openai | anthropic
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str | None = None
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # 视频生成
    video_provider: str = "mock"
    video_output_dir: str = "./outputs/videos"
    composition_output_dir: str = "./outputs/compositions"
    video_provider_max_duration_seconds: float = 10.0
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

    # TTS
    tts_voice: str = "zh-CN-XiaoxiaoNeural"

    model_config = {"env_file": "../.env", "env_file_encoding": "utf-8"}


settings = Settings()
