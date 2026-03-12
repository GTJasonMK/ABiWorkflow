from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.api.websocket import router as ws_router
from app.config import resolve_runtime_path, settings
from app.database import Base, async_session_factory, engine
from app.models import *  # noqa: F401,F403 — 确保所有模型注册到 Base.metadata
from app.services.queue_runtime import ensure_queue_backend_ready, get_queue_runtime_state
from app.services.sqlite_schema_guard import validate_sqlite_schema

# ── 日志配置 ──────────────────────────────────────────────
_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_LEVEL = logging.DEBUG if settings.debug else logging.INFO

logging.basicConfig(
    level=_LOG_LEVEL,
    format=_LOG_FORMAT,
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
    force=True,
)
# 第三方库日志降噪
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING if not settings.debug else logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时创建数据库表并初始化运行环境。"""
    ensure_queue_backend_ready(force_refresh=True)
    queue_state = get_queue_runtime_state()
    logger.info(
        "任务队列运行模式: mode=%s, redis_available=%s",
        queue_state.mode,
        queue_state.redis_available,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await validate_sqlite_schema(conn)

    # 默认 Provider 初始化：缺失则创建；若检测到内置默认配置不一致，则进行纠正。
    try:
        from app.services.provider_bootstrap import ensure_default_provider_configs

        async with async_session_factory() as db:
            await ensure_default_provider_configs(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("默认 Provider 配置初始化失败: %s", exc)
    yield


app = FastAPI(
    title=settings.app_name,
    description="剧本转视频自动化工作流",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # 支持 Vite 本地开发端口波动（localhost / 127.0.0.1）以及 Electron(file://) 场景
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "null",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """健康检查端点"""
    return {"status": "ok", "app": settings.app_name}


app.include_router(api_router)
app.include_router(ws_router)

# 挂载静态文件目录（视频和合成输出）
videos_dir = resolve_runtime_path(settings.video_output_dir)
videos_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/videos", StaticFiles(directory=str(videos_dir)), name="videos")

compositions_dir = resolve_runtime_path(settings.composition_output_dir)
compositions_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/compositions", StaticFiles(directory=str(compositions_dir)), name="compositions")

portraits_dir = resolve_runtime_path(settings.portrait_output_dir)
portraits_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/portraits", StaticFiles(directory=str(portraits_dir)), name="portraits")
