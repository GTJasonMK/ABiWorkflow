from __future__ import annotations

import logging

from app.generation_payload import (
    GEN_PAYLOAD_KEY_COMPLETED,
    GEN_PAYLOAD_KEY_FAILED,
    GEN_PAYLOAD_KEY_TOTAL_SCENES,
)
from app.project_status import (
    PROJECT_STATUS_COMPLETED,
    PROJECT_STATUS_FAILED,
    PROJECT_STATUS_GENERATING,
    PROJECT_STATUS_PARSED,
)
from app.scene_status import (
    READY_SCENE_STATUSES,
    REGENERATABLE_SCENE_STATUSES,
    SCENE_STATUS_FAILED,
    SCENE_STATUS_PENDING,
)
from app.services.progress import publish_progress
from app.tasks.celery_app import celery_app
from app.tasks.task_record_sync import sync_task_record_status
from app.tasks.status_recovery import restore_project_status_after_task_failure, run_async_in_new_loop
from app.task_record_status import TASK_RECORD_STATUS_COMPLETED, TASK_RECORD_STATUS_FAILED, TASK_RECORD_STATUS_RUNNING

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_videos")
def generate_videos_task(self, project_id: str, previous_status: str = PROJECT_STATUS_PARSED, force_regenerate: bool = False):
    """异步批量生成视频任务"""
    from app.config import reload_settings
    reload_settings()
    run_async_in_new_loop(sync_task_record_status(
        source_task_id=self.request.id,
        status=TASK_RECORD_STATUS_RUNNING,
        progress_percent=2.0,
        message="生成任务开始执行",
        event_type="worker_started",
    ))

    publish_progress(project_id, "generate_start", {"message": "开始生成视频"})

    try:
        result = run_async_in_new_loop(_run_generate(project_id, previous_status, force_regenerate))
        run_async_in_new_loop(sync_task_record_status(
            source_task_id=self.request.id,
            status=TASK_RECORD_STATUS_COMPLETED,
            progress_percent=100.0,
            message="生成任务完成",
            result=result,
            event_type="worker_completed",
        ))

        return result

    except Exception as e:
        run_async_in_new_loop(sync_task_record_status(
            source_task_id=self.request.id,
            status=TASK_RECORD_STATUS_FAILED,
            progress_percent=100.0,
            message="生成任务失败",
            error_message=str(e),
            event_type="worker_failed",
        ))
        restore_project_status_after_task_failure(
            project_id,
            PROJECT_STATUS_GENERATING,
            previous_status,
            task_name="生成任务",
            logger=logger,
        )
        logger.exception("视频生成任务失败: project=%s", project_id)
        publish_progress(project_id, "generate_failed", {"message": f"生成失败: {e}"})
        raise


async def _run_generate(project_id: str, previous_status: str, force_regenerate: bool = False) -> dict:
    """执行异步视频生成逻辑"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import resolve_database_url, settings
    from app.models import Project, Scene
    from app.services.composition_state import mark_completed_compositions_stale
    from app.services.video_generator import VideoGeneratorService
    from app.video_providers.registry import get_provider

    engine = create_async_engine(resolve_database_url(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as db:
            project = (await db.execute(
                select(Project).where(Project.id == project_id)
            )).scalar_one()

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
                completed = sum(1 for s in scenes if s.status in READY_SCENE_STATUSES)
                failed = sum(1 for s in scenes if s.status == SCENE_STATUS_FAILED)
                all_done = completed == len(scenes)

                if all_done:
                    project.status = PROJECT_STATUS_COMPLETED if previous_status == PROJECT_STATUS_COMPLETED else PROJECT_STATUS_PARSED
                else:
                    project.status = PROJECT_STATUS_FAILED
                await db.commit()

                return {
                    GEN_PAYLOAD_KEY_TOTAL_SCENES: len(scenes),
                    GEN_PAYLOAD_KEY_COMPLETED: completed,
                    GEN_PAYLOAD_KEY_FAILED: failed,
                }
            except Exception:
                project.status = PROJECT_STATUS_FAILED if previous_status != PROJECT_STATUS_COMPLETED else PROJECT_STATUS_COMPLETED
                await db.commit()
                raise
    finally:
        await engine.dispose()
