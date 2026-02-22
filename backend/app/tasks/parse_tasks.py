from __future__ import annotations

import asyncio
import logging

from app.services.progress import publish_progress
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="parse_script")
def parse_script_task(self, project_id: str):
    """异步剧本解析任务"""
    publish_progress(project_id, "parse_start", {"message": "开始解析剧本"})

    try:
        # 在 Celery worker 中运行异步代码
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(_run_parse(project_id))
        finally:
            loop.close()

        publish_progress(project_id, "parse_complete", {
            "message": "解析完成",
            "character_count": result["character_count"],
            "scene_count": result["scene_count"],
        })
        return result

    except Exception as e:
        publish_progress(project_id, "parse_failed", {"message": f"解析失败: {e}"})
        raise


async def _run_parse(project_id: str) -> dict:
    """执行异步解析逻辑"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import settings
    from app.llm.factory import create_llm_adapter
    from app.models import Project
    from app.services.script_parser import ScriptParserService

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as db:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()

        publish_progress(project_id, "parse_progress", {"message": "正在进行叙事分析...", "percent": 20})

        llm = create_llm_adapter()
        try:
            parser = ScriptParserService(llm)
            result = await parser.parse_script(project_id, project.script_text, db)
            await db.commit()
        except Exception:
            await db.rollback()
            project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
            project.status = "draft"
            await db.commit()
            raise
        finally:
            await llm.close()

    await engine.dispose()
    return {"character_count": result.character_count, "scene_count": result.scene_count}
