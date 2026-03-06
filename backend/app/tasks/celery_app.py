from celery import Celery

from app.config import settings
from app.services.queue_runtime import ensure_queue_backend_ready

# worker/web API 进程导入 Celery 配置时先探测 Redis，可用性不足则落到 SQLite。
ensure_queue_backend_ready(force_refresh=True, apply_celery_runtime=False)

celery_app = Celery(
    "abi_workflow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)


def configure_backend_urls(broker_url: str, result_backend: str) -> None:
    """运行时热切换 Celery broker/result backend。"""
    celery_app.conf.update(
        broker_url=broker_url,
        result_backend=result_backend,
    )


celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_time_limit=600,
    task_soft_time_limit=540,
)

# 导入任务模块，确保 worker 能注册任务。
from app.tasks import compose_tasks as _compose_tasks  # noqa: F401,E402
from app.tasks import generate_tasks as _generate_tasks  # noqa: F401,E402
from app.tasks import import_tasks as _import_tasks  # noqa: F401,E402
from app.tasks import parse_tasks as _parse_tasks  # noqa: F401,E402
