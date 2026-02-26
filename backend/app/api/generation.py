from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_status import claim_project_status_or_409, try_restore_project_status
from app.api.task_mode import resolve_async_mode
from app.database import get_db
from app.models import Project, Scene
from app.schemas.common import ApiResponse
from app.services.composition_state import mark_completed_compositions_stale
from app.services.video_generator import VideoGeneratorService
from app.video_providers.registry import get_provider

router = APIRouter(tags=["视频生成"])
READY_SCENE_STATUSES = {"generated", "completed"}
REGENERATABLE_SCENE_STATUSES = {"pending", "failed", "generating"}


@router.post("/projects/{project_id}/generate", response_model=ApiResponse[dict])
async def start_generation(
    project_id: str,
    async_mode: bool = Query(False, description="是否异步执行生成"),
    force_recover: bool = Query(False, description="是否强制恢复卡住的 generating 状态"),
    force_regenerate: bool = Query(False, description="是否强制重新生成已完成的场景"),
    db: AsyncSession = Depends(get_db),
):
    """启动项目视频生成"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    scenes = (await db.execute(
        select(Scene).where(Scene.project_id == project_id).order_by(Scene.sequence_order)
    )).scalars().all()
    if not scenes:
        raise HTTPException(status_code=400, detail="当前项目没有可生成的场景，请先解析剧本")

    # force_regenerate 时将已完成场景重置为 pending，使其重新参与生成。
    if force_regenerate:
        for s in scenes:
            if s.status in READY_SCENE_STATUSES:
                s.status = "pending"
        await db.flush()

    regeneratable_scenes = [s for s in scenes if s.status in REGENERATABLE_SCENE_STATUSES]
    empty_prompt_scenes = [s.title for s in regeneratable_scenes if not (s.video_prompt and s.video_prompt.strip())]
    if empty_prompt_scenes:
        titles = "、".join(empty_prompt_scenes[:5])
        raise HTTPException(status_code=400, detail=f"以下场景缺少视频提示词: {titles}")

    if force_recover and project.status == "generating":
        project.status = "parsed"
        await db.commit()
        await db.refresh(project)

    if project.status in {"draft", "parsing", "composing"}:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 不允许启动生成")

    # 无待生成场景时直接返回，避免不必要的状态切换与任务排队。
    all_ready = all(s.status in READY_SCENE_STATUSES for s in scenes)
    if not regeneratable_scenes and all_ready:
        if project.status in {"failed", "generating"}:
            project.status = "parsed"
            await db.commit()
        return ApiResponse(data={
            "total_scenes": len(scenes),
            "completed": len(scenes),
            "failed": 0,
        })

    previous_status = project.status
    await claim_project_status_or_409(
        db,
        project_id=project_id,
        target_status="generating",
        allowed_from_statuses=["parsed", "failed", "completed"],
        action_label="启动生成",
        recover_hint_status="generating",
    )

    async_mode = resolve_async_mode(async_mode)

    if async_mode:
        # 异步模式下先落库"项目已进入 generating"（含 force_regenerate 重置后的 pending 状态）。
        await db.commit()
        try:
            from app.tasks.generate_tasks import generate_videos_task

            task = generate_videos_task.delay(project_id, previous_status, force_regenerate)
            return ApiResponse(data={"task_id": task.id, "mode": "async", "status": "queued"})
        except Exception as e:
            await try_restore_project_status(db, project_id, previous_status)
            raise HTTPException(status_code=500, detail=f"生成任务提交失败: {e}")

    # 同步模式下，一旦进入重生成流程，历史成片即视为过期（即使后续生成失败也不再代表当前素材状态）。
    if regeneratable_scenes or force_regenerate:
        await mark_completed_compositions_stale(db, project_id)
    await db.commit()

    try:
        provider = get_provider()
        generator = VideoGeneratorService(provider)
        await generator.generate_all(project_id, db)

        # 检查是否全部成功
        scenes = (await db.execute(
            select(Scene).where(Scene.project_id == project_id)
        )).scalars().all()
        all_done = all(s.status in READY_SCENE_STATUSES for s in scenes)
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        if all_done:
            project.status = "completed" if previous_status == "completed" else "parsed"
        else:
            project.status = "failed"
        await db.commit()

        return ApiResponse(data={
            "total_scenes": len(scenes),
            "completed": sum(1 for s in scenes if s.status in READY_SCENE_STATUSES),
            "failed": sum(1 for s in scenes if s.status == "failed"),
        })
    except Exception as e:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = "failed" if previous_status != "completed" else "completed"
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
    previous_status = project.status
    original_scene_status = scene.status
    await claim_project_status_or_409(
        db,
        project_id=project.id,
        target_status="generating",
        allowed_from_statuses=["parsed", "failed", "completed"],
        action_label="重试场景生成",
    )

    scene.status = "pending"
    await db.flush()
    generation_started = False

    try:
        provider = get_provider()
        generator = VideoGeneratorService(provider)
        # 真正进入重生成前再失效旧成片，避免初始化失败时误判旧成片不可用。
        await mark_completed_compositions_stale(db, scene.project_id)
        generation_started = True
        clips = await generator.generate_scene(scene, db)

        project_scenes = (await db.execute(
            select(Scene).where(Scene.project_id == scene.project_id)
        )).scalars().all()
        # 单场景重试后，只要项目内不存在失败场景，就保持为 parsed（可能仍有 pending 待后续批量生成）。
        project.status = "failed" if any(s.status == "failed" for s in project_scenes) else "parsed"
        await db.commit()

        return ApiResponse(data={
            "scene_id": scene_id,
            "status": scene.status,
            "clips": len(clips),
        })
    except Exception as e:
        if not generation_started:
            # 生成尚未启动（例如 provider 初始化失败）时，回滚场景状态，避免误报失败。
            scene.status = original_scene_status
            project.status = previous_status
        else:
            if scene.status not in READY_SCENE_STATUSES:
                scene.status = "failed"
            project.status = "failed" if previous_status != "completed" else "completed"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"场景重试失败: {e}")


@router.post("/scenes/{scene_id}/generate-candidates", response_model=ApiResponse[dict])
async def generate_candidates(
    scene_id: str,
    candidate_count: int = Query(3, ge=1, le=10, description="候选数量"),
    db: AsyncSession = Depends(get_db),
):
    """为场景生成多个候选视频片段"""
    scene = (await db.execute(select(Scene).where(Scene.id == scene_id))).scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="场景不存在")
    if not scene.video_prompt or not scene.video_prompt.strip():
        raise HTTPException(status_code=400, detail="场景缺少视频提示词，无法生成候选")

    project = (await db.execute(select(Project).where(Project.id == scene.project_id))).scalar_one()
    previous_status = project.status
    await claim_project_status_or_409(
        db,
        project_id=project.id,
        target_status="generating",
        allowed_from_statuses=["parsed", "failed", "completed"],
        action_label="生成候选片段",
    )

    await db.flush()
    generation_started = False

    try:
        provider = get_provider()
        generator = VideoGeneratorService(provider)
        await mark_completed_compositions_stale(db, scene.project_id)
        generation_started = True
        clips = await generator.generate_candidates(scene, candidate_count, db)

        # 恢复项目状态
        project.status = previous_status if previous_status in {"parsed", "completed"} else "parsed"
        await db.commit()

        generated_count = sum(1 for c in clips if c.status == "completed")
        failed_count = sum(1 for c in clips if c.status == "failed")

        return ApiResponse(data={
            "scene_id": scene_id,
            "generated": generated_count,
            "failed": failed_count,
        })
    except Exception as e:
        if not generation_started:
            project.status = previous_status
        else:
            project.status = previous_status if previous_status in {"parsed", "completed"} else "parsed"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"候选生成失败: {e}")
