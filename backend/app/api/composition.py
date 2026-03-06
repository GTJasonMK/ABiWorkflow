from __future__ import annotations

import logging
import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import get_episode_in_project_or_404, get_project_or_404
from app.api.project_status import (
    claim_project_status_or_409,
    force_recover_project_status,
    restore_project_status_and_raise_submit_error,
)
from app.api.task_mode import resolve_async_mode
from app.composition_status import COMPOSITION_STATUS_COMPLETED
from app.config import resolve_runtime_path
from app.database import get_db
from app.models import CompositionTask, Project
from app.project_status import (
    PROJECT_COMPOSE_ALLOWED_FROM,
    PROJECT_STATUS_COMPOSING,
    PROJECT_STATUS_PARSED,
    resolve_composition_failure_status,
    resolve_post_composition_status,
)
from app.schemas.common import ApiResponse
from app.services.composition_state import mark_completed_compositions_stale
from app.services.task_records import create_task_record, update_task_record
from app.services.video_editor import CompositionOptions, VideoEditorService, load_panels_for_composition

router = APIRouter(tags=["视频合成"])
logger = logging.getLogger(__name__)


def _build_compose_task_payload(
    project_id: str,
    episode_id: str | None,
    options: CompositionOptions,
) -> dict:
    return {
        "project_id": project_id,
        "episode_id": episode_id,
        "scope": "episode" if episode_id else "project",
        "options": options.model_dump(),
    }


def _serialize_composition_task(task: CompositionTask) -> dict:
    return {
        "id": task.id,
        "project_id": task.project_id,
        "episode_id": task.episode_id,
        "status": task.status,
        "output_path": task.output_path,
        "media_url": _build_media_url(task.output_path, task.project_id),
        "transition_type": task.transition_type,
        "include_subtitles": task.include_subtitles,
        "include_tts": task.include_tts,
        "duration_seconds": task.duration_seconds,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


def _build_media_url(output_path: str | None, project_id: str) -> str | None:
    """从数据库 output_path 计算静态文件服务 URL。"""
    if not output_path:
        return None
    filename = Path(output_path).name
    return f"/media/compositions/{project_id}/{filename}"


async def _get_composition_or_404(composition_id: str, db: AsyncSession) -> CompositionTask:
    task = (await db.execute(
        select(CompositionTask).where(CompositionTask.id == composition_id)
    )).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="合成任务不存在")
    return task


def _resolve_output_file_path(path_value: str) -> Path:
    raw_path = Path(path_value)
    if raw_path.is_absolute():
        return raw_path.resolve()

    runtime_based = resolve_runtime_path(raw_path)
    cwd_based = (Path.cwd() / raw_path).resolve()
    return runtime_based if runtime_based.exists() or not cwd_based.exists() else cwd_based


def _build_compose_result_payload(composition_id: str, episode_id: str | None) -> dict:
    return {
        "composition_id": composition_id,
        "episode_id": episode_id,
    }


async def _update_episode_compose_task(
    db: AsyncSession,
    task,
    *,
    status: str,
    message: str,
    result: dict | None = None,
    error_message: str | None = None,
) -> None:
    await update_task_record(
        db,
        task=task,
        status=status,
        progress_percent=100.0,
        message=message,
        result=result,
        error_message=error_message,
        event_type="completed" if status == "completed" else "failed",
    )


def _write_compose_error_log(traceback_text: str) -> None:
    try:
        err_log = resolve_runtime_path("./outputs/logs/compose-error.log")
        err_log.parent.mkdir(parents=True, exist_ok=True)
        err_log.write_text(traceback_text, encoding="utf-8")
    except Exception:
        pass


class TrimRequest(BaseModel):
    """视频裁剪请求参数"""

    start_time: float = Field(..., ge=0.0, description="裁剪起始时间（秒）")
    end_time: float = Field(..., gt=0.0, description="裁剪结束时间（秒）")

    @model_validator(mode="after")
    def validate_range(self) -> "TrimRequest":
        if self.end_time <= self.start_time:
            raise ValueError("end_time 必须大于 start_time")
        if self.end_time - self.start_time < 0.5:
            raise ValueError("裁剪片段最少 0.5 秒")
        return self


@router.get("/projects/{project_id}/compositions/latest", response_model=ApiResponse[dict | None])
async def get_latest_composition(
    project_id: str,
    episode_id: str | None = Query(None, description="可选：仅查询指定分集最新成片"),
    db: AsyncSession = Depends(get_db),
):
    """获取项目（或分集）最新的已完成合成记录"""
    if episode_id:
        await get_episode_in_project_or_404(project_id, episode_id, db)

    stmt = (
        select(CompositionTask)
        .where(
            CompositionTask.project_id == project_id,
            CompositionTask.status == COMPOSITION_STATUS_COMPLETED,
        )
        .order_by(CompositionTask.created_at.desc())
        .limit(1)
    )
    if episode_id:
        stmt = stmt.where(CompositionTask.episode_id == episode_id)

    task = (await db.execute(
        stmt
    )).scalar_one_or_none()
    if task is None:
        return ApiResponse(data=None)
    return ApiResponse(data=_serialize_composition_task(task))


@router.post("/projects/{project_id}/compose", response_model=ApiResponse[dict])
async def start_composition(
    project_id: str,
    options: CompositionOptions | None = None,
    episode_id: str | None = Query(None, description="可选：仅合成指定分集"),
    async_mode: bool = Query(False, description="是否异步执行合成"),
    force_recover: bool = Query(False, description="是否强制恢复卡住的 composing 状态"),
    db: AsyncSession = Depends(get_db),
):
    """启动视频合成"""
    project = await get_project_or_404(project_id, db)

    if episode_id:
        await get_episode_in_project_or_404(project_id, episode_id, db)
    try:
        await load_panels_for_composition(project_id, db, episode_id=episode_id)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    if force_recover:
        await force_recover_project_status(
            db,
            project=project,
            busy_status=PROJECT_STATUS_COMPOSING,
            recovered_status=PROJECT_STATUS_PARSED,
        )

    # 在强制恢复后再记录回滚目标，避免提交失败时误回滚到 composing。
    previous_status = project.status

    await claim_project_status_or_409(
        db,
        project_id=project_id,
        target_status=PROJECT_STATUS_COMPOSING,
        allowed_from_statuses=PROJECT_COMPOSE_ALLOWED_FROM,
        action_label="启动合成",
        recover_hint_status=PROJECT_STATUS_COMPOSING,
    )
    await db.commit()

    composition_options = options or CompositionOptions()
    async_mode = False if episode_id else resolve_async_mode(async_mode)
    sync_scope_task = None

    if async_mode:
        try:
            from app.tasks.compose_tasks import compose_video_task

            task = compose_video_task.delay(project_id, composition_options.model_dump(), previous_status, episode_id)
            await create_task_record(
                db,
                task_type="compose",
                target_type="episode" if episode_id else "project",
                target_id=episode_id or project_id,
                project_id=project_id,
                episode_id=episode_id,
                source_task_id=task.id,
                status="pending",
                message="合成任务已排队",
                payload={
                    **_build_compose_task_payload(project_id, episode_id, composition_options),
                },
            )
            await db.commit()
            return ApiResponse(data={"task_id": task.id, "mode": "async", "status": "queued"})
        except Exception as e:
            await restore_project_status_and_raise_submit_error(
                db,
                project_id=project_id,
                fallback_status=previous_status,
                detail_prefix="合成任务提交失败",
                error=e,
            )

    if episode_id:
        sync_scope_task = await create_task_record(
            db,
            task_type="compose",
            target_type="episode",
            target_id=episode_id,
            project_id=project_id,
            episode_id=episode_id,
            status="running",
            progress_percent=5.0,
            message="分集合成执行中",
            payload=_build_compose_task_payload(project_id, episode_id, composition_options),
        )
        await db.commit()

    try:
        editor = VideoEditorService()
        task_id = await editor.compose(project_id, composition_options, db, episode_id=episode_id)
        await mark_completed_compositions_stale(
            db,
            project_id,
            episode_id=episode_id,
            exclude_composition_id=task_id,
        )
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = resolve_post_composition_status(previous_status, scoped_to_episode=bool(episode_id))
        result_payload = _build_compose_result_payload(task_id, episode_id)
        if sync_scope_task is not None:
            await _update_episode_compose_task(
                db,
                sync_scope_task,
                status="completed",
                message="分集合成完成",
                result=result_payload,
            )
        await db.commit()
        return ApiResponse(data=result_payload)
    except ValueError as e:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = previous_status
        if sync_scope_task is not None:
            await _update_episode_compose_task(
                db,
                sync_scope_task,
                status="failed",
                message="分集合成失败",
                error_message=str(e),
            )
        await db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        tb = traceback.format_exc()
        logger.exception("视频合成失败: project=%s", project_id)
        _write_compose_error_log(tb)
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = resolve_composition_failure_status(previous_status, scoped_to_episode=bool(episode_id))
        if sync_scope_task is not None:
            await _update_episode_compose_task(
                db,
                sync_scope_task,
                status="failed",
                message="分集合成失败",
                error_message=str(e),
            )
        await db.commit()
        raise HTTPException(status_code=500, detail=f"合成失败: {e}\n\n--- traceback ---\n{tb}")


@router.get("/compositions/{composition_id}", response_model=ApiResponse[dict])
async def get_composition(composition_id: str, db: AsyncSession = Depends(get_db)):
    """查询合成任务"""
    task = await _get_composition_or_404(composition_id, db)
    return ApiResponse(data=_serialize_composition_task(task))


@router.get("/compositions/{composition_id}/download")
async def download_composition(composition_id: str, db: AsyncSession = Depends(get_db)):
    """下载合成视频"""
    task = await _get_composition_or_404(composition_id, db)
    if not task.output_path:
        raise HTTPException(status_code=404, detail="视频文件不存在")

    file_path = _resolve_output_file_path(task.output_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")

    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=f"composition_{composition_id}.mp4",
    )


@router.post("/compositions/{composition_id}/trim", response_model=ApiResponse[dict])
async def trim_composition(
    composition_id: str,
    request: TrimRequest,
    db: AsyncSession = Depends(get_db),
):
    """裁剪合成视频，生成新的合成记录"""
    task = (await db.execute(
        select(CompositionTask).where(CompositionTask.id == composition_id)
    )).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="合成任务不存在")
    if task.status != COMPOSITION_STATUS_COMPLETED:
        raise HTTPException(status_code=400, detail="只能裁剪已完成的合成视频")
    if task.duration_seconds and request.end_time > task.duration_seconds:
        raise HTTPException(
            status_code=400,
            detail=f"end_time ({request.end_time:.2f}) 超过视频时长 ({task.duration_seconds:.2f})",
        )

    try:
        editor = VideoEditorService()
        new_id = await editor.trim(composition_id, request.start_time, request.end_time, db)
        new_task = (await db.execute(
            select(CompositionTask).where(CompositionTask.id == new_id)
        )).scalar_one()
        return ApiResponse(data={
            "composition_id": new_task.id,
            "duration_seconds": new_task.duration_seconds,
            "media_url": _build_media_url(new_task.output_path, new_task.project_id),
        })
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("视频裁剪失败: composition=%s", composition_id)
        raise HTTPException(status_code=500, detail=f"裁剪失败: {e}")
