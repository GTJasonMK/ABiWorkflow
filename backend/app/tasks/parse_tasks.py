from __future__ import annotations

from app.services.progress import publish_progress
from app.tasks.celery_app import celery_app
from app.tasks.status_recovery import restore_project_status_after_task_failure, run_async_in_new_loop


@celery_app.task(bind=True, name="parse_script")
def parse_script_task(self, project_id: str, previous_status: str = "draft", script_text: str | None = None):
    """异步剧本解析任务"""
    from app.config import reload_settings
    reload_settings()

    publish_progress(project_id, "parse_start", {"message": "开始解析剧本", "percent": 2})

    try:
        result = run_async_in_new_loop(_run_parse(project_id, previous_status, script_text))

        publish_progress(project_id, "parse_complete", {
            "message": "解析完成",
            "percent": 100,
            "character_count": result["character_count"],
            "scene_count": result["scene_count"],
        })
        return result

    except Exception as e:
        restore_project_status_after_task_failure(
            project_id,
            "parsing",
            previous_status,
            task_name="解析任务",
        )
        publish_progress(project_id, "parse_failed", {"message": f"解析失败: {e}", "percent": 100})
        raise


async def _run_parse(project_id: str, previous_status: str, script_text: str | None = None) -> dict:
    """执行异步解析逻辑"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import resolve_database_url, settings
    from app.llm.factory import create_llm_adapter
    from app.models import Project
    from app.services.script_parser import ScriptParserService

    engine = create_async_engine(resolve_database_url(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as db:
            llm = None
            try:
                project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()

                publish_progress(project_id, "parse_progress", {"message": "正在初始化解析器...", "percent": 8})
                llm = create_llm_adapter()

                parse_input = script_text if script_text is not None else project.script_text
                if not parse_input or not parse_input.strip():
                    raise RuntimeError("剧本内容为空，无法解析")

                parser = ScriptParserService(llm)
                result = await parser.parse_script(project_id, parse_input, db)
                await db.commit()
            except Exception:
                await db.rollback()
                project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
                project.status = previous_status
                await db.commit()
                raise
            finally:
                if llm is not None:
                    await llm.close()

            return {"character_count": result.character_count, "scene_count": result.scene_count}
    finally:
        await engine.dispose()
