from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Project, Scene
from app.schemas.common import ApiResponse
from app.services.video_generator import VideoGeneratorService
from app.video_providers.registry import get_provider

router = APIRouter(tags=["视频生成"])


@router.post("/projects/{project_id}/generate", response_model=ApiResponse[dict])
async def start_generation(project_id: str, db: AsyncSession = Depends(get_db)):
    """启动项目视频生成"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.status not in ("parsed", "generating"):
        raise HTTPException(status_code=400, detail=f"项目状态 {project.status} 不允许生成视频")

    scenes = (await db.execute(
        select(Scene).where(Scene.project_id == project_id).order_by(Scene.sequence_order)
    )).scalars().all()
    if not scenes:
        raise HTTPException(status_code=400, detail="当前项目没有可生成的场景，请先解析剧本")

    empty_prompt_scenes = [s.title for s in scenes if not (s.video_prompt and s.video_prompt.strip())]
    if empty_prompt_scenes:
        titles = "、".join(empty_prompt_scenes[:5])
        raise HTTPException(status_code=400, detail=f"以下场景缺少视频提示词: {titles}")

    project.status = "generating"
    await db.commit()

    try:
        provider = get_provider()
        generator = VideoGeneratorService(provider)
        await generator.generate_all(project_id, db)

        # 检查是否全部成功
        scenes = (await db.execute(
            select(Scene).where(Scene.project_id == project_id)
        )).scalars().all()
        all_done = all(s.status == "generated" for s in scenes)
        project.status = "parsed" if all_done else "failed"
        await db.commit()

        return ApiResponse(data={
            "total_scenes": len(scenes),
            "completed": sum(1 for s in scenes if s.status == "generated"),
            "failed": sum(1 for s in scenes if s.status == "failed"),
        })
    except Exception as e:
        project.status = "failed"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"视频生成失败: {e}")


@router.post("/scenes/{scene_id}/retry", response_model=ApiResponse[dict])
async def retry_scene(scene_id: str, db: AsyncSession = Depends(get_db)):
    """重试单个场景的视频生成"""
    scene = (await db.execute(select(Scene).where(Scene.id == scene_id))).scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="场景不存在")
    if not scene.video_prompt or not scene.video_prompt.strip():
        raise HTTPException(status_code=400, detail="场景缺少视频提示词，无法生成")

    project = (await db.execute(select(Project).where(Project.id == scene.project_id))).scalar_one()
    project.status = "generating"

    scene.status = "pending"
    await db.flush()

    provider = get_provider()
    generator = VideoGeneratorService(provider)
    clips = await generator.generate_scene(scene, db)

    project_scenes = (await db.execute(
        select(Scene).where(Scene.project_id == scene.project_id)
    )).scalars().all()
    project.status = "parsed" if all(s.status == "generated" for s in project_scenes) else "failed"
    await db.commit()

    return ApiResponse(data={
        "scene_id": scene_id,
        "status": scene.status,
        "clips": len(clips),
    })
