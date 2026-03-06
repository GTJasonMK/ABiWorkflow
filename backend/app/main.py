from __future__ import annotations

import logging
import shutil
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.api.websocket import router as ws_router
from app.config import resolve_runtime_path, settings
from app.database import Base, engine
from app.models import *  # noqa: F401,F403 — 确保所有模型注册到 Base.metadata
from app.services.queue_runtime import ensure_queue_backend_ready, get_queue_runtime_state
from app.services.schema_cleanup import cleanup_deprecated_single_track_schema

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

# 声明式模式迁移：已有表中可能缺失的新增列。
# 格式：(表名, 列名, DDL 类型定义)
_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("characters", "portrait_url", "VARCHAR(500)"),
    ("video_clips", "candidate_index", "INTEGER DEFAULT 0"),
    ("video_clips", "is_selected", "BOOLEAN DEFAULT 1"),
    ("global_characters", "folder_id", "VARCHAR(36)"),
    ("global_characters", "project_id", "VARCHAR(36)"),
    ("global_locations", "folder_id", "VARCHAR(36)"),
    ("global_locations", "project_id", "VARCHAR(36)"),
    ("global_voices", "folder_id", "VARCHAR(36)"),
    ("global_voices", "project_id", "VARCHAR(36)"),
    ("composition_tasks", "episode_id", "VARCHAR(36)"),
]


def _apply_column_migrations(connection) -> None:
    """检查已有表是否缺少新增列，缺少则自动 ALTER TABLE 补齐。"""
    insp = inspect(connection)
    for table_name, column_name, column_type in _COLUMN_MIGRATIONS:
        if not insp.has_table(table_name):
            continue
        existing = {col["name"] for col in insp.get_columns(table_name)}
        if column_name not in existing:
            connection.execute(text(
                f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            ))
            logger.info("自动迁移：表 %s 新增列 %s", table_name, column_name)


async def _migrate_legacy_scenes_to_panels() -> None:
    """一次性迁移：将历史 Scene-only 项目转换为 Panel 单轨数据。"""
    from app.database import async_session_factory
    from app.services.storyboard_bridge import migrate_legacy_scenes_to_panels

    marker_file = resolve_runtime_path("./outputs/.migrated_panels_single_track")
    if marker_file.exists():
        return

    migrated_projects = 0
    migrated_panels = 0
    async with async_session_factory() as db:
        migrated_projects, migrated_panels = await migrate_legacy_scenes_to_panels(db)
        await db.commit()

    marker_file.parent.mkdir(parents=True, exist_ok=True)
    marker_file.write_text(
        f"migrated_projects={migrated_projects},migrated_panels={migrated_panels}",
        encoding="utf-8",
    )
    logger.info(
        "分镜单轨迁移完成：迁移项目 %d 个，创建分镜 %d 条",
        migrated_projects,
        migrated_panels,
    )


async def _migrate_assets_to_project_dirs() -> None:
    """一次性迁移：将散落的资产文件归整到按项目隔离的子目录。

    历史问题：旧版本生成的视频和合成输出直接存放在 backend 根目录或 outputs 根目录，
    而非 outputs/videos/{project_id}/ 和 outputs/compositions/{project_id}/。
    此迁移会：
    1. 将数据库中有记录的文件移动到正确的项目子目录，并更新 file_path/output_path
    2. 清理 backend 根目录下的孤立 mp4、moviepy 临时文件、tts 临时目录
    3. 清理测试数据库文件

    使用标记文件避免重复执行。
    """
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models import CompositionTask, Scene, VideoClip

    marker_file = resolve_runtime_path("./outputs/.migrated_project_dirs")
    if marker_file.exists():
        return

    backend_root = Path(__file__).resolve().parents[1]
    video_root = resolve_runtime_path(settings.video_output_dir)
    composition_root = resolve_runtime_path(settings.composition_output_dir)
    video_root.mkdir(parents=True, exist_ok=True)
    composition_root.mkdir(parents=True, exist_ok=True)
    moved_count = 0

    async with async_session_factory() as db:
        # ── 迁移视频片段 ──
        clips = (await db.execute(
            select(VideoClip, Scene.project_id)
            .join(Scene, VideoClip.scene_id == Scene.id)
            .where(VideoClip.file_path.isnot(None))
        )).all()

        for clip, project_id in clips:
            old_path = _resolve_file_path(clip.file_path)
            if old_path is None or not old_path.exists():
                continue

            target_dir = video_root / project_id
            # 已在正确的项目子目录中，跳过
            if old_path.parent == target_dir:
                continue

            target_dir.mkdir(parents=True, exist_ok=True)
            new_path = target_dir / old_path.name
            try:
                shutil.move(str(old_path), str(new_path))
                clip.file_path = str(new_path)
                moved_count += 1
            except OSError as e:
                logger.warning("迁移视频片段失败 %s → %s: %s", old_path, new_path, e)

        # ── 迁移合成输出 ──
        compositions = (await db.execute(
            select(CompositionTask).where(CompositionTask.output_path.isnot(None))
        )).scalars().all()

        for comp in compositions:
            old_path = _resolve_file_path(comp.output_path)
            if old_path is None or not old_path.exists():
                continue

            target_dir = composition_root / comp.project_id
            if old_path.parent == target_dir:
                continue

            target_dir.mkdir(parents=True, exist_ok=True)
            new_path = target_dir / old_path.name
            try:
                shutil.move(str(old_path), str(new_path))
                comp.output_path = str(new_path)
                moved_count += 1
            except OSError as e:
                logger.warning("迁移合成输出失败 %s → %s: %s", old_path, new_path, e)

        await db.commit()

    # ── 清理 backend 根目录下的垃圾文件 ──
    cleanup_count = 0
    for item in backend_root.iterdir():
        name = item.name
        # moviepy 临时文件
        if name.endswith(".mp4") and "TEMP_MPY" in name:
            item.unlink(missing_ok=True)
            cleanup_count += 1
        # 孤立的 mp4（非数据库引用、散落在根目录的历史产物）
        elif item.is_file() and name.endswith(".mp4"):
            item.unlink(missing_ok=True)
            cleanup_count += 1
        # 散落的 tts 临时目录
        elif item.is_dir() and name.endswith("_tts"):
            shutil.rmtree(item, ignore_errors=True)
            cleanup_count += 1
        # 测试产生的数据库文件
        elif item.is_file() and name.endswith(".db") and name != "abi_workflow.db":
            item.unlink(missing_ok=True)
            cleanup_count += 1

    # 写入标记文件
    marker_file.parent.mkdir(parents=True, exist_ok=True)
    marker_file.write_text("done", encoding="utf-8")
    logger.info(
        "资产目录迁移完成：移动 %d 个文件到项目子目录，清理 %d 个垃圾文件",
        moved_count, cleanup_count,
    )


async def _migrate_composition_episode_scope() -> None:
    """一次性迁移：通过任务记录回填 composition_tasks.episode_id。"""
    from sqlalchemy import select

    from app.database import async_session_factory
    from app.models import CompositionTask, TaskRecord
    from app.services.json_codec import from_json_text

    marker_file = resolve_runtime_path("./outputs/.migrated_composition_episode_scope")
    if marker_file.exists():
        return

    backfilled_count = 0
    async with async_session_factory() as db:
        rows = (await db.execute(
            select(TaskRecord).where(
                TaskRecord.task_type == "compose",
                TaskRecord.episode_id.isnot(None),
                TaskRecord.result_json.isnot(None),
            ).order_by(TaskRecord.updated_at.desc(), TaskRecord.created_at.desc())
        )).scalars().all()

        composition_episode_map: dict[str, str] = {}
        for task in rows:
            if not task.episode_id:
                continue
            result = from_json_text(task.result_json, {})
            if not isinstance(result, dict):
                continue
            raw_composition_id = result.get("composition_id")
            if not isinstance(raw_composition_id, str):
                continue
            composition_id = raw_composition_id.strip()
            if not composition_id or composition_id in composition_episode_map:
                continue
            composition_episode_map[composition_id] = task.episode_id

        if composition_episode_map:
            targets = (await db.execute(
                select(CompositionTask).where(
                    CompositionTask.id.in_(tuple(composition_episode_map.keys())),
                    CompositionTask.episode_id.is_(None),
                )
            )).scalars().all()
            for task in targets:
                episode_id = composition_episode_map.get(task.id)
                if not episode_id:
                    continue
                task.episode_id = episode_id
                backfilled_count += 1
        await db.commit()

    marker_file.parent.mkdir(parents=True, exist_ok=True)
    marker_file.write_text(f"backfilled={backfilled_count}", encoding="utf-8")
    logger.info("成片分集作用域回填完成：回填记录 %d 条", backfilled_count)


def _resolve_file_path(path_value: str | None) -> Path | None:
    """将数据库中的路径解析为绝对路径。"""
    if not path_value:
        return None
    raw = Path(path_value)
    if raw.is_absolute():
        return raw.resolve()
    runtime_based = resolve_runtime_path(raw)
    cwd_based = (Path.cwd() / raw).resolve()
    if runtime_based.exists():
        return runtime_based
    if cwd_based.exists():
        return cwd_based
    return runtime_based


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时创建数据库表、补齐新增列、执行一次性迁移任务"""
    ensure_queue_backend_ready(force_refresh=True)
    queue_state = get_queue_runtime_state()
    logger.info(
        "任务队列运行模式: mode=%s, redis_available=%s, fallback_active=%s",
        queue_state.mode,
        queue_state.redis_available,
        queue_state.fallback_active,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_column_migrations)
        cleanup_result = await conn.run_sync(cleanup_deprecated_single_track_schema)
        if cleanup_result.get("skipped_by_marker"):
            logger.info("单轨清理：检测到 marker，跳过 schema 清理")
        else:
            logger.info(
                "单轨清理：完成 schema 清理 dropped_table=%s dropped_column=%s",
                cleanup_result.get("dropped_table"),
                cleanup_result.get("dropped_column"),
            )
    await _migrate_composition_episode_scope()
    await _migrate_legacy_scenes_to_panels()
    await _migrate_assets_to_project_dirs()
    yield


app = FastAPI(
    title=settings.app_name,
    description="剧本转视频自动化工作流",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    # 兼容 Vite 本地开发端口波动（localhost / 127.0.0.1）以及 Electron(file://) 场景
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
