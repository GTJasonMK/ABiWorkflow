from __future__ import annotations

from app.progress_payload import (
    PROGRESS_KEY_CHARACTER_COUNT,
    PROGRESS_KEY_EPISODE_COUNT,
    PROGRESS_KEY_MESSAGE,
    PROGRESS_KEY_PANEL_COUNT,
    PROGRESS_KEY_PERCENT,
)
from app.project_status import PROJECT_STATUS_DRAFT, PROJECT_STATUS_PARSING
from app.services.progress import publish_progress
from app.tasks.celery_app import celery_app
from app.tasks.status_recovery import (
    mark_worker_task_completed,
    mark_worker_task_failed,
    mark_worker_task_started,
    restore_project_status_after_task_failure,
    run_async_in_new_loop,
)


@celery_app.task(bind=True, name="parse_script")
def parse_script_task(
    self,
    project_id: str,
    previous_status: str = PROJECT_STATUS_DRAFT,
    script_text: str | None = None,
):
    """异步剧本解析任务"""
    from app.config import reload_settings
    reload_settings()
    mark_worker_task_started(self.request.id, "解析任务开始执行")

    publish_progress(project_id, "parse_start", {PROGRESS_KEY_MESSAGE: "开始解析剧本", PROGRESS_KEY_PERCENT: 2})

    try:
        result = run_async_in_new_loop(_run_parse(project_id, previous_status, script_text))
        mark_worker_task_completed(self.request.id, "解析任务完成", result)

        publish_progress(project_id, "parse_complete", {
            PROGRESS_KEY_MESSAGE: "解析完成",
            PROGRESS_KEY_PERCENT: 100,
            PROGRESS_KEY_CHARACTER_COUNT: result["character_count"],
            PROGRESS_KEY_PANEL_COUNT: result.get("panel_count", 0),
            PROGRESS_KEY_EPISODE_COUNT: result.get("episode_count", 0),
        })
        return result

    except Exception as e:
        mark_worker_task_failed(self.request.id, "解析任务失败", str(e))
        restore_project_status_after_task_failure(
            project_id,
            PROJECT_STATUS_PARSING,
            previous_status,
            task_name="解析任务",
        )
        publish_progress(project_id, "parse_failed", {
            PROGRESS_KEY_MESSAGE: f"解析失败: {e}",
            PROGRESS_KEY_PERCENT: 100,
        })
        raise


async def _run_parse(project_id: str, previous_status: str, script_text: str | None = None) -> dict:
    """执行异步解析逻辑"""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.config import resolve_database_url, settings
    from app.llm.factory import create_llm_adapter
    from app.models import Project
    from app.services.episode_parse_pipeline import parse_project_from_episodes

    engine = create_async_engine(resolve_database_url(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with session_factory() as db:
            llm = None
            try:
                project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()

                publish_progress(project_id, "parse_progress", {
                    PROGRESS_KEY_MESSAGE: "正在初始化解析器...",
                    PROGRESS_KEY_PERCENT: 8,
                })
                llm = create_llm_adapter()

                parse_input = script_text if script_text is not None else project.script_text
                if not parse_input or not parse_input.strip():
                    raise RuntimeError("剧本内容为空，无法解析")

                result = await parse_project_from_episodes(project_id, parse_input, llm, db)
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

            return {
                "character_count": result.character_count,
                "panel_count": result.panel_count,
                "episode_count": result.episode_count,
            }
    finally:
        await engine.dispose()
