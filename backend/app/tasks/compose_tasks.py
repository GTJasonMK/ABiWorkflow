from __future__ import annotations

import asyncio
import logging

from app.services.progress import publish_progress
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="compose_video")
def compose_video_task(self, project_id: str, options: dict | None = None):
    """异步视频合成任务"""
    publish_progress(project_id, "compose_start", {"message": "开始合成视频"})

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_run_compose(project_id, options))
        finally:
            loop.close()

        publish_progress(project_id, "compose_complete", {
            "message": "视频合成完成",
            "composition_id": result["composition_id"],
        })
        return result

    except Exception as e:
        logger.exception("视频合成任务失败: project=%s", project_id)
        publish_progress(project_id, "compose_failed", {"message": f"合成失败: {e}"})
        raise


async def _run_compose(project_id: str, options_dict: dict | None) -> dict:
    """执行异步视频合成逻辑"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.models import Project
    from app.services.video_editor import CompositionOptions, VideoEditorService

    # 将 dict 转换为 CompositionOptions
    composition_options = CompositionOptions(**(options_dict or {}))

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        project = (await db.execute(
            select(Project).where(Project.id == project_id)
        )).scalar_one()

        project.status = "composing"
        await db.commit()

        try:
            editor = VideoEditorService()
            composition_id = await editor.compose(project_id, composition_options, db)

            project.status = "completed"
            await db.commit()

            result = {"composition_id": composition_id}
        except ValueError:
            project.status = "parsed"
            await db.commit()
            raise
        except Exception:
            project.status = "failed"
            await db.commit()
            raise

    await engine.dispose()
    return result
