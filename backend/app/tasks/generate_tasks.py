from __future__ import annotations

import asyncio
import logging

from app.services.progress import publish_progress
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="generate_videos")
def generate_videos_task(self, project_id: str):
    """异步批量生成视频任务"""
    publish_progress(project_id, "generate_start", {"message": "开始生成视频"})

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_run_generate(project_id))
        finally:
            loop.close()

        publish_progress(project_id, "generate_complete", {
            "message": "视频生成完成",
            "total_scenes": result["total_scenes"],
            "completed": result["completed"],
            "failed": result["failed"],
        })
        return result

    except Exception as e:
        logger.exception("视频生成任务失败: project=%s", project_id)
        publish_progress(project_id, "generate_failed", {"message": f"生成失败: {e}"})
        raise


async def _run_generate(project_id: str) -> dict:
    """执行异步视频生成逻辑"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.models import Project, Scene
    from app.services.video_generator import VideoGeneratorService
    from app.video_providers.registry import get_provider

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        project = (await db.execute(
            select(Project).where(Project.id == project_id)
        )).scalar_one()

        project.status = "generating"
        await db.commit()

        try:
            provider = get_provider()
            generator = VideoGeneratorService(provider)
            await generator.generate_all(project_id, db)

            # 统计结果
            scenes = (await db.execute(
                select(Scene).where(Scene.project_id == project_id)
            )).scalars().all()
            completed = sum(1 for s in scenes if s.status == "generated")
            failed = sum(1 for s in scenes if s.status == "failed")
            all_done = completed == len(scenes)

            project.status = "parsed" if all_done else "failed"
            await db.commit()

            result = {
                "total_scenes": len(scenes),
                "completed": completed,
                "failed": failed,
            }
        except Exception:
            project.status = "failed"
            await db.commit()
            raise

    await engine.dispose()
    return result
