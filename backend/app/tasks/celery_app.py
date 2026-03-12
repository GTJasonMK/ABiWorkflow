from celery import Celery

from app.config import settings

celery_app = Celery(
    "abi_workflow",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
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

from app.tasks import compose_tasks as _compose_tasks  # noqa: E402,F401
from app.tasks import generate_tasks as _generate_tasks  # noqa: E402,F401
from app.tasks import import_tasks as _import_tasks  # noqa: E402,F401
from app.tasks import parse_tasks as _parse_tasks  # noqa: E402,F401
