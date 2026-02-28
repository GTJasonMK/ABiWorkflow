from __future__ import annotations

import logging
import traceback
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_status import claim_project_status_or_409, try_restore_project_status
from app.api.task_mode import resolve_async_mode
from app.composition_status import COMPOSITION_STATUS_COMPLETED
from app.config import resolve_runtime_path
from app.database import get_db
from app.models import CompositionTask, Project, Scene
from app.project_status import (
    PROJECT_COMPOSE_ALLOWED_FROM,
    PROJECT_STATUS_COMPLETED,
    PROJECT_STATUS_COMPOSING,
    PROJECT_STATUS_FAILED,
    PROJECT_STATUS_PARSED,
)
from app.scene_status import READY_SCENE_STATUSES
from app.schemas.common import ApiResponse
from app.services.composition_state import mark_completed_compositions_stale
from app.services.task_records import create_task_record
from app.services.video_editor import CompositionOptions, VideoEditorService

router = APIRouter(tags=["视频合成"])
logger = logging.getLogger(__name__)


def _build_media_url(output_path: str | None, project_id: str) -> str | None:
    """从数据库 output_path 计算静态文件服务 URL。"""
    if not output_path:
        return None
    filename = Path(output_path).name
    return f"/media/compositions/{project_id}/{filename}"


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
async def get_latest_composition(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目最新的已完成合成记录"""
    task = (await db.execute(
        select(CompositionTask)
        .where(
            CompositionTask.project_id == project_id,
            CompositionTask.status == COMPOSITION_STATUS_COMPLETED,
        )
        .order_by(CompositionTask.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if task is None:
        return ApiResponse(data=None)
    return ApiResponse(data={
        "id": task.id,
        "project_id": task.project_id,
        "status": task.status,
        "output_path": task.output_path,
        "media_url": _build_media_url(task.output_path, task.project_id),
        "transition_type": task.transition_type,
        "include_subtitles": task.include_subtitles,
        "include_tts": task.include_tts,
        "duration_seconds": task.duration_seconds,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    })


@router.post("/projects/{project_id}/compose", response_model=ApiResponse[dict])
async def start_composition(
    project_id: str,
    options: CompositionOptions | None = None,
    async_mode: bool = Query(False, description="是否异步执行合成"),
    force_recover: bool = Query(False, description="是否强制恢复卡住的 composing 状态"),
    db: AsyncSession = Depends(get_db),
):
    """启动视频合成"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    scenes = (await db.execute(
        select(Scene).where(Scene.project_id == project_id).order_by(Scene.sequence_order)
    )).scalars().all()
    if not scenes:
        raise HTTPException(status_code=400, detail="当前项目没有可合成的场景")

    not_ready_scenes = [s.title for s in scenes if s.status not in READY_SCENE_STATUSES]
    if not_ready_scenes:
        title_preview = "、".join(not_ready_scenes[:5])
        raise HTTPException(status_code=400, detail=f"以下场景尚未生成完成: {title_preview}")

    if force_recover and project.status == PROJECT_STATUS_COMPOSING:
        project.status = PROJECT_STATUS_PARSED
        await db.commit()
        await db.refresh(project)

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
    async_mode = resolve_async_mode(async_mode)

    if async_mode:
        try:
            from app.tasks.compose_tasks import compose_video_task

            task = compose_video_task.delay(project_id, composition_options.model_dump(), previous_status)
            await create_task_record(
                db,
                task_type="compose",
                target_type="project",
                target_id=project_id,
                project_id=project_id,
                source_task_id=task.id,
                status="pending",
                message="合成任务已排队",
                payload={"project_id": project_id, "options": composition_options.model_dump()},
            )
            await db.commit()
            return ApiResponse(data={"task_id": task.id, "mode": "async", "status": "queued"})
        except Exception as e:
            await try_restore_project_status(db, project_id, previous_status)
            raise HTTPException(status_code=500, detail=f"合成任务提交失败: {e}")

    try:
        editor = VideoEditorService()
        task_id = await editor.compose(project_id, composition_options, db)
        await mark_completed_compositions_stale(db, project_id, exclude_composition_id=task_id)
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = PROJECT_STATUS_COMPLETED
        await db.commit()
        return ApiResponse(data={"composition_id": task_id})
    except ValueError as e:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = previous_status
        await db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        tb = traceback.format_exc()
        logger.exception("视频合成失败: project=%s", project_id)
        # 将完整调用栈写入专用文件，同时包含在 HTTP 响应中便于前端诊断
        try:
            from app.config import resolve_runtime_path
            err_log = resolve_runtime_path("./outputs/logs/compose-error.log")
            err_log.parent.mkdir(parents=True, exist_ok=True)
            err_log.write_text(tb, encoding="utf-8")
        except Exception:
            pass
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = PROJECT_STATUS_FAILED if previous_status != PROJECT_STATUS_COMPLETED else PROJECT_STATUS_COMPLETED
        await db.commit()
        raise HTTPException(status_code=500, detail=f"合成失败: {e}\n\n--- traceback ---\n{tb}")


@router.get("/compositions/{composition_id}", response_model=ApiResponse[dict])
async def get_composition(composition_id: str, db: AsyncSession = Depends(get_db)):
    """查询合成任务"""
    task = (await db.execute(
        select(CompositionTask).where(CompositionTask.id == composition_id)
    )).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="合成任务不存在")
    return ApiResponse(data={
        "id": task.id,
        "project_id": task.project_id,
        "status": task.status,
        "output_path": task.output_path,
        "media_url": _build_media_url(task.output_path, task.project_id),
        "transition_type": task.transition_type,
        "include_subtitles": task.include_subtitles,
        "include_tts": task.include_tts,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    })


@router.get("/compositions/{composition_id}/download")
async def download_composition(composition_id: str, db: AsyncSession = Depends(get_db)):
    """下载合成视频"""
    task = (await db.execute(
        select(CompositionTask).where(CompositionTask.id == composition_id)
    )).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="合成任务不存在")
    if not task.output_path:
        raise HTTPException(status_code=404, detail="视频文件不存在")

    raw_path = Path(task.output_path)
    if raw_path.is_absolute():
        file_path = raw_path.resolve()
    else:
        runtime_based = resolve_runtime_path(raw_path)
        cwd_based = (Path.cwd() / raw_path).resolve()
        file_path = runtime_based if runtime_based.exists() or not cwd_based.exists() else cwd_based
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
