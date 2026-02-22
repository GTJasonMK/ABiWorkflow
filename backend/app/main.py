from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.api.websocket import router as ws_router
from app.config import settings
from app.database import Base, engine
from app.models import *  # noqa: F401,F403 — 确保所有模型注册到 Base.metadata


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时创建数据库表"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=settings.app_name,
    description="剧本转视频自动化工作流",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
videos_dir = Path(settings.video_output_dir)
videos_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/videos", StaticFiles(directory=str(videos_dir)), name="videos")

compositions_dir = Path(settings.composition_output_dir)
compositions_dir.mkdir(parents=True, exist_ok=True)
app.mount("/media/compositions", StaticFiles(directory=str(compositions_dir)), name="compositions")
