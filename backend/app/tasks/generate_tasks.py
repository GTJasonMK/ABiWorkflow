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
from app.services.progress import publish_progress
from app.tasks.celery_app import celery_app
from app.tasks.status_recovery import (
    commit_project_status,
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
    """异步批量生成视频任务。"""
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
    from sqlalchemy import select

    from app.models import Project
    from app.panel_status import PANEL_READY_STATUSES, PANEL_REGENERATABLE_STATUSES
    from app.services.composition_state import mark_completed_compositions_stale
    from app.services.panel_generation import (
        count_panel_generation_result,
        list_project_panels_ordered,
        sync_panel_outputs_from_clips,
    )
    from app.services.script_asset_compiler import compile_project_effective_bindings
    from app.services.video_generator import VideoGeneratorService
    from app.tasks.db_session import task_session
    from app.video_providers.registry import get_provider

    async with task_session() as db:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        panels = await list_project_panels_ordered(project_id, db)
        if not panels:
            raise RuntimeError("当前项目没有可生成的分镜")

        await compile_project_effective_bindings(project_id, db)
        await sync_panel_outputs_from_clips(project_id, db)

        if force_regenerate:
            for panel in panels:
                if panel.status in PANEL_READY_STATUSES:
                    panel.status = "pending"
                    panel.video_url = None
                    panel.lipsync_video_url = None
                    panel.error_message = None
            await db.flush()

        panels_to_generate = [panel.id for panel in panels if panel.status in PANEL_REGENERATABLE_STATUSES]
        if panels_to_generate:
            await mark_completed_compositions_stale(db, project_id)

        await commit_project_status(db, project, PROJECT_STATUS_GENERATING)
        try:
            provider = get_provider()
            generator = VideoGeneratorService(provider)
            await generator.generate_all(project_id, db)

            await sync_panel_outputs_from_clips(project_id, db)
            refreshed_panels = await list_project_panels_ordered(project_id, db)
            completed, failed = count_panel_generation_result(refreshed_panels)
            all_done = all(panel.status in PANEL_READY_STATUSES for panel in refreshed_panels)

            await commit_project_status(
                db,
                project,
                resolve_generation_completion_status(
                    previous_status,
                    scoped_to_episode=False,
                    scope_all_done=all_done,
                ),
            )
            return {
                GEN_PAYLOAD_KEY_TOTAL_PANELS: len(refreshed_panels),
                GEN_PAYLOAD_KEY_COMPLETED: completed,
                GEN_PAYLOAD_KEY_FAILED: failed,
            }
        except Exception:
            await commit_project_status(
                db,
                project,
                resolve_generation_failure_status(previous_status, scoped_to_episode=False),
            )
            raise
