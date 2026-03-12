from __future__ import annotations

import logging

from app.progress_payload import PROGRESS_KEY_MESSAGE
from app.project_status import (
    PROJECT_STATUS_COMPOSING,
    PROJECT_STATUS_PARSED,
    resolve_composition_failure_status,
    resolve_post_composition_status,
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


@celery_app.task(bind=True, name="compose_video")
def compose_video_task(
    self,
    project_id: str,
    options: dict | None = None,
    previous_status: str = PROJECT_STATUS_PARSED,
    episode_id: str | None = None,
):
    """异步视频合成任务"""
    from app.config import reload_settings
    reload_settings()
    mark_worker_task_started(self.request.id, "合成任务开始执行")

    publish_progress(project_id, "compose_start", {PROGRESS_KEY_MESSAGE: "开始合成视频"})

    try:
        result = run_async_in_new_loop(_run_compose(project_id, options, previous_status, episode_id))
        mark_worker_task_completed(self.request.id, "合成任务完成", result)

        return result

    except Exception as e:
        mark_worker_task_failed(self.request.id, "合成任务失败", str(e))
        restore_project_status_after_task_failure(
            project_id,
            PROJECT_STATUS_COMPOSING,
            previous_status,
            task_name="合成任务",
            logger=logger,
        )
        logger.exception("视频合成任务失败: project=%s", project_id)
        publish_progress(project_id, "compose_failed", {PROGRESS_KEY_MESSAGE: f"合成失败: {e}"})
        raise


async def _run_compose(
    project_id: str,
    options_dict: dict | None,
    previous_status: str,
    episode_id: str | None = None,
) -> dict:
    """执行异步视频合成逻辑"""
    from sqlalchemy import select

    from app.models import Project
    from app.services.composition_state import mark_completed_compositions_stale
    from app.services.video_editor import CompositionOptions, VideoEditorService
    from app.tasks.db_session import task_session

    # 将 dict 转换为 CompositionOptions
    composition_options = CompositionOptions(**(options_dict or {}))

    async with task_session() as db:
        project = (await db.execute(
            select(Project).where(Project.id == project_id)
        )).scalar_one()

        await commit_project_status(db, project, PROJECT_STATUS_COMPOSING)

        try:
            editor = VideoEditorService()
            composition_id = await editor.compose(project_id, composition_options, db, episode_id=episode_id)
            await mark_completed_compositions_stale(
                db,
                project_id,
                episode_id=episode_id,
                exclude_composition_id=composition_id,
            )

            await commit_project_status(
                db,
                project,
                resolve_post_composition_status(
                    previous_status,
                    scoped_to_episode=bool(episode_id),
                ),
            )

            return {"composition_id": composition_id, "episode_id": episode_id}
        except ValueError:
            await commit_project_status(db, project, previous_status)
            raise
        except Exception:
            await commit_project_status(
                db,
                project,
                resolve_composition_failure_status(previous_status, scoped_to_episode=bool(episode_id)),
            )
            raise
