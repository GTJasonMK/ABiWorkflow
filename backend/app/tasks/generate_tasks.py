from __future__ import annotations

import logging

from app.generation_payload import (
    GEN_PAYLOAD_KEY_COMPLETED,
    GEN_PAYLOAD_KEY_FAILED,
    GEN_PAYLOAD_KEY_TOTAL_PANELS,
)
from app.progress_payload import PROGRESS_KEY_MESSAGE
from app.project_status import (
    PROJECT_STATUS_GENERATING,
    PROJECT_STATUS_PARSED,
    resolve_generation_completion_status,
    resolve_generation_failure_status,
)
from app.scene_status import (
    READY_SCENE_STATUSES,
    REGENERATABLE_SCENE_STATUSES,
    SCENE_STATUS_PENDING,
)
from app.services.progress import publish_progress
from app.tasks.celery_app import celery_app
from app.tasks.status_recovery import (
    mark_worker_task_completed,
    mark_worker_task_failed,
    mark_worker_task_started,
    restore_project_status_after_task_failure,
    run_async_in_new_loop,
)

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_videos")
def generate_videos_task(
    self,
    project_id: str,
    previous_status: str = PROJECT_STATUS_PARSED,
    force_regenerate: bool = False,
):
    """异步批量生成视频任务"""
    from app.config import reload_settings
    reload_settings()
    mark_worker_task_started(self.request.id, "生成任务开始执行")

    publish_progress(project_id, "generate_start", {PROGRESS_KEY_MESSAGE: "开始生成视频"})

    try:
        result = run_async_in_new_loop(_run_generate(project_id, previous_status, force_regenerate))
        mark_worker_task_completed(self.request.id, "生成任务完成", result)

        return result

    except Exception as e:
        mark_worker_task_failed(self.request.id, "生成任务失败", str(e))
        restore_project_status_after_task_failure(
            project_id,
            PROJECT_STATUS_GENERATING,
            previous_status,
            task_name="生成任务",
            logger=logger,
        )
        logger.exception("视频生成任务失败: project=%s", project_id)
        publish_progress(project_id, "generate_failed", {PROGRESS_KEY_MESSAGE: f"生成失败: {e}"})
        raise


async def _run_generate(project_id: str, previous_status: str, force_regenerate: bool = False) -> dict:
    """执行异步视频生成逻辑"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import resolve_database_url, settings
    from app.models import Panel, Project, Scene
    from app.services.composition_state import mark_completed_compositions_stale
    from app.services.script_asset_compiler import compile_project_effective_bindings
    from app.services.storyboard_bridge import rebuild_scenes_from_panels, sync_panel_outputs_from_scenes
    from app.services.video_generator import VideoGeneratorService
    from app.video_providers.registry import get_provider

    engine = create_async_engine(resolve_database_url(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as db:
            project = (await db.execute(
                select(Project).where(Project.id == project_id)
            )).scalar_one()
            panels = (await db.execute(
                select(Panel).where(Panel.project_id == project_id)
            )).scalars().all()
            if not panels:
                raise RuntimeError("当前项目没有可生成的分镜")

            await compile_project_effective_bindings(project_id, db)
            rebuilt_count = await rebuild_scenes_from_panels(project_id, db)
            if rebuilt_count == 0:
                raise RuntimeError("当前项目没有可生成的分镜")

            # force_regenerate 时将已完成场景重置为 pending（API 层已在同步模式下处理，
            # 异步模式由 worker 在此补充执行，确保跨进程一致性）。
            if force_regenerate:
                all_scenes = (await db.execute(
                    select(Scene).where(Scene.project_id == project_id)
                )).scalars().all()
                for s in all_scenes:
                    if s.status in READY_SCENE_STATUSES:
                        s.status = SCENE_STATUS_PENDING
                await db.flush()

            scenes_to_generate = (await db.execute(
                select(Scene.id).where(
                    Scene.project_id == project_id,
                    Scene.status.in_(list(REGENERATABLE_SCENE_STATUSES)),
                )
            )).scalars().all()

            if scenes_to_generate:
                await mark_completed_compositions_stale(db, project_id)

            project.status = PROJECT_STATUS_GENERATING
            await db.commit()

            try:
                provider = get_provider()
                generator = VideoGeneratorService(provider)
                await generator.generate_all(project_id, db)

                # 统计结果
                scenes = (await db.execute(
                    select(Scene).where(Scene.project_id == project_id)
                )).scalars().all()
                completed, failed = await sync_panel_outputs_from_scenes(project_id, db)
                all_done = completed == len(scenes)

                project.status = resolve_generation_completion_status(
                    previous_status,
                    scoped_to_episode=False,
                    scope_all_done=all_done,
                )
                await db.commit()

                return {
                    GEN_PAYLOAD_KEY_TOTAL_PANELS: len(panels),
                    GEN_PAYLOAD_KEY_COMPLETED: completed,
                    GEN_PAYLOAD_KEY_FAILED: failed,
                }
            except Exception:
                project.status = resolve_generation_failure_status(previous_status, scoped_to_episode=False)
                await db.commit()
                raise
    finally:
        await engine.dispose()
