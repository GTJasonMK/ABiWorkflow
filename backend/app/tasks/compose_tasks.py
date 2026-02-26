from __future__ import annotations

import logging

from app.services.progress import publish_progress
from app.tasks.celery_app import celery_app
from app.tasks.status_recovery import restore_project_status_after_task_failure, run_async_in_new_loop

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="compose_video")
def compose_video_task(self, project_id: str, options: dict | None = None, previous_status: str = "parsed"):
    """异步视频合成任务"""
    from app.config import reload_settings
    reload_settings()

    publish_progress(project_id, "compose_start", {"message": "开始合成视频"})

    try:
        result = run_async_in_new_loop(_run_compose(project_id, options, previous_status))

        return result

    except Exception as e:
        restore_project_status_after_task_failure(
            project_id,
            "composing",
            previous_status,
            task_name="合成任务",
            logger=logger,
        )
        logger.exception("视频合成任务失败: project=%s", project_id)
        publish_progress(project_id, "compose_failed", {"message": f"合成失败: {e}"})
        raise


async def _run_compose(project_id: str, options_dict: dict | None, previous_status: str) -> dict:
    """执行异步视频合成逻辑"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import resolve_database_url, settings
    from app.models import Project
    from app.services.composition_state import mark_completed_compositions_stale
    from app.services.video_editor import CompositionOptions, VideoEditorService

    # 将 dict 转换为 CompositionOptions
    composition_options = CompositionOptions(**(options_dict or {}))

    engine = create_async_engine(resolve_database_url(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as db:
            project = (await db.execute(
                select(Project).where(Project.id == project_id)
            )).scalar_one()

            project.status = "composing"
            await db.commit()

            try:
                editor = VideoEditorService()
                composition_id = await editor.compose(project_id, composition_options, db)
                await mark_completed_compositions_stale(db, project_id, exclude_composition_id=composition_id)

                project.status = "completed"
                await db.commit()

                return {"composition_id": composition_id}
            except ValueError:
                project.status = previous_status
                await db.commit()
                raise
            except Exception:
                project.status = "failed" if previous_status != "completed" else "completed"
                await db.commit()
                raise
    finally:
        await engine.dispose()
