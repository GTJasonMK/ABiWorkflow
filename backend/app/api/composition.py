from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CompositionTask, Project, Scene
from app.schemas.common import ApiResponse
from app.services.video_editor import CompositionOptions, VideoEditorService

router = APIRouter(tags=["视频合成"])


@router.post("/projects/{project_id}/compose", response_model=ApiResponse[dict])
async def start_composition(
    project_id: str,
    options: CompositionOptions | None = None,
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

    not_ready_scenes = [s.title for s in scenes if s.status != "generated"]
    if not_ready_scenes:
        title_preview = "、".join(not_ready_scenes[:5])
        raise HTTPException(status_code=400, detail=f"以下场景尚未生成完成: {title_preview}")

    project.status = "composing"
    await db.commit()

    try:
        editor = VideoEditorService()
        task_id = await editor.compose(project_id, options or CompositionOptions(), db)
        project.status = "completed"
        await db.commit()
        return ApiResponse(data={"composition_id": task_id})
    except ValueError as e:
        project.status = "parsed"
        await db.commit()
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        project.status = "failed"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"合成失败: {e}")


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

    file_path = Path(task.output_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在")

    return FileResponse(
        path=str(file_path),
        media_type="video/mp4",
        filename=f"composition_{composition_id}.mp4",
    )
