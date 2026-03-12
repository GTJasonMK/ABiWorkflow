from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import get_episode_in_project_or_404, get_project_or_404
from app.api.project_status import (
    claim_project_status_or_409,
    commit_project_status,
    restore_project_status_and_raise_submit_error,
)
from app.api.task_mode import resolve_async_mode
from app.api.task_submission import submit_async_task_with_record
from app.clip_status import CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED
from app.database import get_db
from app.generation_payload import (
    GEN_PAYLOAD_KEY_COMPLETED,
    GEN_PAYLOAD_KEY_FAILED,
    GEN_PAYLOAD_KEY_GENERATED,
    GEN_PAYLOAD_KEY_TOTAL_PANELS,
)
from app.models import Panel, Project, VideoClip
from app.panel_status import PANEL_READY_STATUSES, PANEL_REGENERATABLE_STATUSES, PANEL_STATUS_FAILED
from app.project_status import (
    PROJECT_GENERATE_ALLOWED_FROM,
    PROJECT_STATUS_COMPLETED,
    PROJECT_STATUS_COMPOSING,
    PROJECT_STATUS_DRAFT,
    PROJECT_STATUS_FAILED,
    PROJECT_STATUS_GENERATING,
    PROJECT_STATUS_PARSED,
    PROJECT_STATUS_PARSING,
    resolve_generation_completion_status,
    resolve_generation_failure_status,
    resolve_post_panel_generation_status,
)
from app.schemas.common import ApiResponse
from app.services.composition_state import mark_completed_compositions_stale
from app.services.panel_generation import (
    count_panel_generation_result,
    list_project_panels_ordered,
    resolve_panel_generation_prompt,
    sync_panel_outputs_from_clips,
)
from app.services.script_asset_compiler import compile_project_effective_bindings, get_panel_effective_binding
from app.services.task_records import create_task_record, update_task_record
from app.services.video_generator import VideoGeneratorService
from app.video_providers.registry import get_provider

router = APIRouter(tags=["视频生成"])


async def _load_project_and_panel(panel_id: str, db: AsyncSession) -> tuple[Project, Panel]:
    panel = (await db.execute(select(Panel).where(Panel.id == panel_id))).scalar_one_or_none()
    if panel is None:
        raise HTTPException(status_code=404, detail="分镜不存在")

    project = (await db.execute(select(Project).where(Project.id == panel.project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project, panel


async def _load_project_panels(project_id: str, db: AsyncSession) -> list[Panel]:
    panels = await list_project_panels_ordered(project_id, db)
    if not panels:
        raise HTTPException(status_code=400, detail="当前项目没有可生成的分镜")
    return panels


async def _ensure_panels_have_prompt(panels: list[Panel], db: AsyncSession) -> None:
    missing_titles: list[str] = []
    for panel in panels:
        effective = await get_panel_effective_binding(panel.id, db, auto_compile=True)
        if not resolve_panel_generation_prompt(panel, effective):
            missing_titles.append(panel.title)
    if missing_titles:
        titles = "、".join(missing_titles[:5])
        raise HTTPException(status_code=400, detail=f"以下分镜缺少视频提示词: {titles}")


async def _create_video_generator_for_panel(
    project: Project,
    panel: Panel,
    db: AsyncSession,
) -> VideoGeneratorService:
    provider = get_provider()
    generator = VideoGeneratorService(provider)
    await mark_completed_compositions_stale(db, project.id, episode_id=panel.episode_id)
    return generator


async def _load_current_panel(panel_id: str, panel: Panel, db: AsyncSession) -> Panel:
    return (await db.execute(select(Panel).where(Panel.id == panel_id))).scalar_one_or_none() or panel


async def _load_project_for_update(project_id: str, db: AsyncSession) -> Project:
    return (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()


def _build_retry_panel_payload(panel_id: str, panel_status: str, clip_count: int) -> dict:
    return {
        "panel_id": panel_id,
        "status": panel_status,
        "clips": clip_count,
    }


def _build_candidate_payload(panel_id: str, panel_status: str, clips: list[VideoClip]) -> dict:
    generated_count = sum(1 for clip in clips if clip.status == CLIP_STATUS_COMPLETED)
    failed_count = sum(1 for clip in clips if clip.status == CLIP_STATUS_FAILED)
    return {
        "panel_id": panel_id,
        "status": panel_status,
        GEN_PAYLOAD_KEY_GENERATED: generated_count,
        GEN_PAYLOAD_KEY_FAILED: failed_count,
    }


def _build_generation_task_payload(
    project_id: str,
    episode_id: str | None,
    force_regenerate: bool,
) -> dict:
    return {
        "project_id": project_id,
        "episode_id": episode_id,
        "scope": "episode" if episode_id else "project",
        "force_regenerate": force_regenerate,
    }


def _build_generation_result_payload(total_panels: int, completed: int, failed: int) -> dict:
    return {
        GEN_PAYLOAD_KEY_TOTAL_PANELS: total_panels,
        GEN_PAYLOAD_KEY_COMPLETED: completed,
        GEN_PAYLOAD_KEY_FAILED: failed,
    }


def _resolve_episode_generation_task_result(*, all_done: bool, failed: int) -> tuple[str, str, str | None]:
    if failed > 0:
        return "failed", "分集生成失败", f"仍有 {failed} 个分镜生成失败"
    if not all_done:
        return "failed", "分集生成失败", "分集生成未全部完成"
    return "completed", "分集生成完成", None


async def _update_episode_generation_task(
    db: AsyncSession,
    task,
    result_payload: dict,
    *,
    all_done: bool,
    failed: int,
) -> None:
    status, message, error_message = _resolve_episode_generation_task_result(
        all_done=all_done,
        failed=failed,
    )
    await update_task_record(
        db,
        task=task,
        status=status,
        progress_percent=100.0,
        message=message,
        error_message=error_message,
        result=result_payload,
        event_type="completed" if status == "completed" else "failed",
    )


async def _fail_episode_generation_task(db: AsyncSession, task, error_message: str) -> None:
    await update_task_record(
        db,
        task=task,
        status="failed",
        progress_percent=100.0,
        message="分集生成失败",
        error_message=error_message,
        event_type="failed",
    )


@router.post("/projects/{project_id}/generate", response_model=ApiResponse[dict])
async def start_generation(
    project_id: str,
    episode_id: str | None = Query(None, description="可选：仅生成指定分集"),
    async_mode: bool = Query(False, description="是否异步执行生成"),
    force_regenerate: bool = Query(False, description="是否强制重新生成已完成的分镜"),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project_or_404(project_id, db)
    if episode_id:
        await get_episode_in_project_or_404(project_id, episode_id, db)

    if episode_id and async_mode:
        raise HTTPException(status_code=400, detail="分集生成暂不支持异步执行")
    async_mode = resolve_async_mode(async_mode)

    await compile_project_effective_bindings(project_id, db)
    panels = await _load_project_panels(project_id, db)
    await sync_panel_outputs_from_clips(project_id, db)

    scope_panels = [panel for panel in panels if not episode_id or panel.episode_id == episode_id]
    if not scope_panels:
        raise HTTPException(status_code=400, detail="当前分集没有可生成的分镜")

    if force_regenerate:
        for panel in scope_panels:
            if panel.status in PANEL_READY_STATUSES:
                panel.status = "pending"
                panel.video_url = None
                panel.lipsync_video_url = None
                panel.error_message = None
        await db.flush()

    regeneratable_panels = [panel for panel in scope_panels if panel.status in PANEL_REGENERATABLE_STATUSES]
    await _ensure_panels_have_prompt(regeneratable_panels, db)

    if project.status in {PROJECT_STATUS_PARSING, PROJECT_STATUS_COMPOSING}:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 不允许启动生成")

    all_ready = all(panel.status in PANEL_READY_STATUSES for panel in scope_panels)
    if not regeneratable_panels and all_ready:
        completed, failed = count_panel_generation_result(scope_panels)
        if project.status in {PROJECT_STATUS_FAILED, PROJECT_STATUS_GENERATING, PROJECT_STATUS_DRAFT}:
            await commit_project_status(db, project, PROJECT_STATUS_PARSED)
        else:
            await db.commit()
        return ApiResponse(data=_build_generation_result_payload(len(scope_panels), completed, failed))

    previous_status = project.status
    await claim_project_status_or_409(
        db,
        project_id=project_id,
        target_status=PROJECT_STATUS_GENERATING,
        allowed_from_statuses=PROJECT_GENERATE_ALLOWED_FROM,
        action_label="启动生成",
    )

    sync_scope_task = None
    if async_mode:
        await db.commit()
        try:
            from app.tasks.generate_tasks import generate_videos_task

            return ApiResponse(data=await submit_async_task_with_record(
                db,
                submit=lambda: generate_videos_task.delay(project_id, previous_status, force_regenerate),
                task_type="generate",
                target_type="episode" if episode_id else "project",
                target_id=episode_id or project_id,
                project_id=project_id,
                episode_id=episode_id,
                message="生成任务已排队",
                payload=_build_generation_task_payload(project_id, episode_id, force_regenerate),
            ))
        except Exception as e:
            await restore_project_status_and_raise_submit_error(
                db,
                project_id=project_id,
                fallback_status=previous_status,
                detail_prefix="生成任务提交失败",
                error=e,
            )

    if episode_id:
        sync_scope_task = await create_task_record(
            db,
            task_type="generate",
            target_type="episode",
            target_id=episode_id,
            project_id=project_id,
            episode_id=episode_id,
            status="running",
            progress_percent=5.0,
            message="分集生成执行中",
            payload=_build_generation_task_payload(project_id, episode_id, force_regenerate),
        )

    if regeneratable_panels or force_regenerate:
        await mark_completed_compositions_stale(db, project_id, episode_id=episode_id)
    await db.commit()

    try:
        provider = get_provider()
        generator = VideoGeneratorService(provider)
        panel_id_scope = {panel.id for panel in scope_panels} if episode_id else None
        await generator.generate_all(project_id, db, panel_ids=panel_id_scope)

        await sync_panel_outputs_from_clips(project_id, db, panel_ids=panel_id_scope)
        refreshed_panels = await _load_project_panels(project_id, db)
        target_panels = [panel for panel in refreshed_panels if not panel_id_scope or panel.id in panel_id_scope]
        all_done = all(panel.status in PANEL_READY_STATUSES for panel in target_panels)
        completed, failed = count_panel_generation_result(target_panels)
        project = await _load_project_for_update(project_id, db)
        result_payload = _build_generation_result_payload(len(scope_panels), completed, failed)
        if sync_scope_task is not None:
            await _update_episode_generation_task(
                db,
                sync_scope_task,
                result_payload,
                all_done=all_done,
                failed=failed,
            )
        await commit_project_status(
            db,
            project,
            resolve_generation_completion_status(
                previous_status,
                scoped_to_episode=bool(episode_id),
                scope_all_done=all_done,
            ),
        )
        return ApiResponse(data=result_payload)
    except Exception as e:
        project = await _load_project_for_update(project_id, db)
        if sync_scope_task is not None:
            await _fail_episode_generation_task(db, sync_scope_task, str(e))
        await commit_project_status(
            db,
            project,
            resolve_generation_failure_status(previous_status, scoped_to_episode=bool(episode_id)),
        )
        raise HTTPException(status_code=500, detail=f"视频生成失败: {e}")


@router.post("/panels/{panel_id}/retry", response_model=ApiResponse[dict])
async def retry_panel(panel_id: str, db: AsyncSession = Depends(get_db)):
    project, panel = await _load_project_and_panel(panel_id, db)
    await _ensure_panels_have_prompt([panel], db)

    previous_status = project.status
    await claim_project_status_or_409(
        db,
        project_id=project.id,
        target_status=PROJECT_STATUS_GENERATING,
        allowed_from_statuses=PROJECT_GENERATE_ALLOWED_FROM,
        action_label="重试分镜生成",
    )

    generation_started = False
    try:
        generator = await _create_video_generator_for_panel(project, panel, db)
        generation_started = True
        clips = await generator.generate_panel(panel, db)
        await sync_panel_outputs_from_clips(project.id, db, panel_ids={panel.id})
        await commit_project_status(
            db,
            project,
            PROJECT_STATUS_PARSED
            if previous_status == PROJECT_STATUS_COMPLETED
            else resolve_post_panel_generation_status(previous_status),
        )
        updated_panel = await _load_current_panel(panel_id, panel, db)
        return ApiResponse(data=_build_retry_panel_payload(panel_id, updated_panel.status, len(clips)))
    except Exception as e:
        if generation_started and panel.status not in PANEL_READY_STATUSES:
            panel.status = PANEL_STATUS_FAILED
        await commit_project_status(
            db,
            project,
            previous_status if not generation_started else resolve_generation_failure_status(previous_status, scoped_to_episode=True),
        )
        raise HTTPException(status_code=500, detail=f"分镜重试失败: {e}")


@router.post("/panels/{panel_id}/generate-candidates", response_model=ApiResponse[dict])
async def generate_panel_candidates(
    panel_id: str,
    candidate_count: int = Query(3, ge=1, le=10, description="候选数量"),
    db: AsyncSession = Depends(get_db),
):
    project, panel = await _load_project_and_panel(panel_id, db)
    await _ensure_panels_have_prompt([panel], db)

    previous_status = project.status
    await claim_project_status_or_409(
        db,
        project_id=project.id,
        target_status=PROJECT_STATUS_GENERATING,
        allowed_from_statuses=PROJECT_GENERATE_ALLOWED_FROM,
        action_label="生成分镜候选片段",
    )
    await db.flush()

    generation_started = False
    try:
        generator = await _create_video_generator_for_panel(project, panel, db)
        generation_started = True
        clips = await generator.generate_candidates(panel, candidate_count, db)
        await sync_panel_outputs_from_clips(project.id, db, panel_ids={panel.id})
        await commit_project_status(db, project, resolve_post_panel_generation_status(previous_status))
        updated_panel = await _load_current_panel(panel_id, panel, db)
        return ApiResponse(data=_build_candidate_payload(panel_id, updated_panel.status, clips))
    except Exception as e:
        await commit_project_status(
            db,
            project,
            previous_status if not generation_started else resolve_post_panel_generation_status(previous_status),
        )
        raise HTTPException(status_code=500, detail=f"候选生成失败: {e}")
