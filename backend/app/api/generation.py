from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import get_episode_in_project_or_404, get_project_or_404
from app.api.project_status import (
    claim_project_status_or_409,
    force_recover_project_status,
    restore_project_status_and_raise_submit_error,
)
from app.api.task_mode import resolve_async_mode
from app.clip_status import CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED
from app.database import get_db
from app.generation_payload import (
    GEN_PAYLOAD_KEY_COMPLETED,
    GEN_PAYLOAD_KEY_FAILED,
    GEN_PAYLOAD_KEY_GENERATED,
    GEN_PAYLOAD_KEY_TOTAL_PANELS,
)
from app.models import Panel, Project, Scene
from app.panel_status import PANEL_STATUS_COMPLETED, PANEL_STATUS_FAILED
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
    resolve_post_scene_generation_status,
)
from app.scene_status import (
    READY_SCENE_STATUSES,
    REGENERATABLE_SCENE_STATUSES,
    SCENE_STATUS_FAILED,
    SCENE_STATUS_PENDING,
)
from app.schemas.common import ApiResponse
from app.services.composition_state import mark_completed_compositions_stale
from app.services.script_asset_compiler import compile_project_effective_bindings
from app.services.storyboard_bridge import (
    ensure_scene_projection_from_panels,
    list_project_scenes_ordered,
    sync_panel_outputs_from_scenes,
)
from app.services.task_records import create_task_record, update_task_record
from app.services.video_generator import VideoGeneratorService
from app.video_providers.registry import get_provider

router = APIRouter(tags=["视频生成"])


def _count_scope_panel_result(scope_panels: list[Panel]) -> tuple[int, int]:
    completed = sum(1 for item in scope_panels if item.status == PANEL_STATUS_COMPLETED)
    failed = sum(1 for item in scope_panels if item.status == PANEL_STATUS_FAILED)
    return completed, failed


async def _sync_and_resolve_project_storyboard(
    project_id: str,
    db: AsyncSession,
) -> tuple[list[Panel], list[Scene]]:
    panels, scenes = await ensure_scene_projection_from_panels(project_id, db)
    if not panels:
        raise HTTPException(status_code=400, detail="当前项目没有可生成的分镜")
    if len(scenes) != len(panels):
        raise HTTPException(
            status_code=409,
            detail="分镜执行映射数量不一致，请先执行项目批量生成以重建映射",
        )
    return panels, scenes


async def _sync_and_resolve_scene_for_panel(
    panel_id: str,
    db: AsyncSession,
) -> tuple[Project, Panel, Scene]:
    panel = (await db.execute(select(Panel).where(Panel.id == panel_id))).scalar_one_or_none()
    if panel is None:
        raise HTTPException(status_code=404, detail="分镜不存在")

    project = (await db.execute(select(Project).where(Project.id == panel.project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    panels, scenes = await _sync_and_resolve_project_storyboard(project.id, db)

    index_map = {item.id: idx for idx, item in enumerate(panels)}
    target_index = index_map.get(panel_id)
    if target_index is None:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return project, panels[target_index], scenes[target_index]


def _ensure_scene_has_prompt(scene: Scene, detail: str) -> None:
    if not scene.video_prompt or not scene.video_prompt.strip():
        raise HTTPException(status_code=400, detail=detail)


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


def _build_retry_panel_payload(panel_id: str, panel_status: str, clip_count: int) -> dict:
    return {
        "panel_id": panel_id,
        "status": panel_status,
        "clips": clip_count,
    }


def _build_candidate_payload(panel_id: str, panel_status: str, clips: list) -> dict:
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


async def _update_episode_generation_task(
    db: AsyncSession,
    task,
    result_payload: dict,
    *,
    all_done: bool,
    failed: int,
) -> None:
    if failed > 0:
        await update_task_record(
            db,
            task=task,
            status="failed",
            progress_percent=100.0,
            message="分集生成失败",
            error_message=f"仍有 {failed} 个分镜生成失败",
            result=result_payload,
            event_type="failed",
        )
        return
    if not all_done:
        await update_task_record(
            db,
            task=task,
            status="failed",
            progress_percent=100.0,
            message="分集生成失败",
            error_message="分集生成未全部完成",
            result=result_payload,
            event_type="failed",
        )
        return

    await update_task_record(
        db,
        task=task,
        status="completed",
        progress_percent=100.0,
        message="分集生成完成",
        result=result_payload,
        event_type="completed",
    )




@router.post("/projects/{project_id}/generate", response_model=ApiResponse[dict])
async def start_generation(
    project_id: str,
    episode_id: str | None = Query(None, description="可选：仅生成指定分集"),
    async_mode: bool = Query(False, description="是否异步执行生成"),
    force_recover: bool = Query(False, description="是否强制恢复卡住的 generating 状态"),
    force_regenerate: bool = Query(False, description="是否强制重新生成已完成的分镜"),
    db: AsyncSession = Depends(get_db),
):
    """启动项目视频生成"""
    project = await get_project_or_404(project_id, db)

    # 生成前编译分镜生效绑定（剧本默认 + 分集覆盖 + 分镜覆盖）。
    await compile_project_effective_bindings(project_id, db)
    panels, scenes = await _sync_and_resolve_project_storyboard(project_id, db)
    if not panels:
        raise HTTPException(status_code=400, detail="当前项目没有可生成的分镜，请先解析剧本或导入分镜")

    scope_panels = panels
    scope_scenes = scenes
    if episode_id:
        await get_episode_in_project_or_404(project_id, episode_id, db)

        scope_indexes = [idx for idx, item in enumerate(panels) if item.episode_id == episode_id]
        if not scope_indexes:
            raise HTTPException(status_code=400, detail="当前分集没有可生成的分镜")
        scope_panels = [panels[idx] for idx in scope_indexes]
        scope_scenes = [scenes[idx] for idx in scope_indexes]

    # force_regenerate 时将已完成分镜映射重置为 pending，使其重新参与生成。
    if force_regenerate:
        for s in scope_scenes:
            if s.status in READY_SCENE_STATUSES:
                s.status = SCENE_STATUS_PENDING
        await db.flush()

    regeneratable_scenes = [s for s in scope_scenes if s.status in REGENERATABLE_SCENE_STATUSES]
    empty_prompt_scenes = [s.title for s in regeneratable_scenes if not (s.video_prompt and s.video_prompt.strip())]
    if empty_prompt_scenes:
        titles = "、".join(empty_prompt_scenes[:5])
        raise HTTPException(status_code=400, detail=f"以下分镜缺少视频提示词: {titles}")

    if force_recover:
        await force_recover_project_status(
            db,
            project=project,
            busy_status=PROJECT_STATUS_GENERATING,
            recovered_status=PROJECT_STATUS_PARSED,
        )

    if project.status in {PROJECT_STATUS_DRAFT, PROJECT_STATUS_PARSING, PROJECT_STATUS_COMPOSING}:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 不允许启动生成")

    # 无待生成分镜时直接返回，避免不必要的状态切换与任务排队。
    all_ready = all(s.status in READY_SCENE_STATUSES for s in scope_scenes)
    if not regeneratable_scenes and all_ready:
        await sync_panel_outputs_from_scenes(project_id, db)
        completed, failed = _count_scope_panel_result(scope_panels)
        if project.status in {PROJECT_STATUS_FAILED, PROJECT_STATUS_GENERATING}:
            project.status = PROJECT_STATUS_PARSED
        await db.commit()
        return ApiResponse(data=_build_generation_result_payload(len(scope_panels), completed, failed))

    previous_status = project.status
    await claim_project_status_or_409(
        db,
        project_id=project_id,
        target_status=PROJECT_STATUS_GENERATING,
        allowed_from_statuses=PROJECT_GENERATE_ALLOWED_FROM,
        action_label="启动生成",
        recover_hint_status=PROJECT_STATUS_GENERATING,
    )

    async_mode = False if episode_id else resolve_async_mode(async_mode)
    sync_scope_task = None

    if async_mode:
        # 异步模式下先落库"项目已进入 generating"（含 force_regenerate 重置后的 pending 状态）。
        await db.commit()
        try:
            from app.tasks.generate_tasks import generate_videos_task

            task = generate_videos_task.delay(project_id, previous_status, force_regenerate)
            await create_task_record(
                db,
                task_type="generate",
                target_type="episode" if episode_id else "project",
                target_id=episode_id or project_id,
                project_id=project_id,
                episode_id=episode_id,
                source_task_id=task.id,
                status="pending",
                message="生成任务已排队",
                payload=_build_generation_task_payload(project_id, episode_id, force_regenerate),
            )
            await db.commit()
            return ApiResponse(data={"task_id": task.id, "mode": "async", "status": "queued"})
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

    # 同步模式下，一旦进入重生成流程，历史成片即视为过期（即使后续生成失败也不再代表当前素材状态）。
    if regeneratable_scenes or force_regenerate:
        await mark_completed_compositions_stale(db, project_id, episode_id=episode_id)
    await db.commit()

    try:
        provider = get_provider()
        generator = VideoGeneratorService(provider)
        scene_id_scope = {item.id for item in scope_scenes} if episode_id else None
        await generator.generate_all(project_id, db, scene_ids=scene_id_scope)

        refreshed_scenes = await list_project_scenes_ordered(project_id, db)
        if episode_id and scene_id_scope is not None:
            target_scenes = [scene for scene in refreshed_scenes if scene.id in scene_id_scope]
        else:
            target_scenes = refreshed_scenes
        all_done = all(s.status in READY_SCENE_STATUSES for s in target_scenes)
        await sync_panel_outputs_from_scenes(project_id, db)
        completed, failed = _count_scope_panel_result(scope_panels)
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = resolve_generation_completion_status(
            previous_status,
            scoped_to_episode=bool(episode_id),
            scope_all_done=all_done,
        )
        result_payload = _build_generation_result_payload(len(scope_panels), completed, failed)
        if sync_scope_task is not None:
            await _update_episode_generation_task(
                db,
                sync_scope_task,
                result_payload,
                all_done=all_done,
                failed=failed,
            )
        await db.commit()

        return ApiResponse(data=result_payload)
    except Exception as e:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = resolve_generation_failure_status(previous_status, scoped_to_episode=bool(episode_id))
        if sync_scope_task is not None:
            await update_task_record(
                db,
                task=sync_scope_task,
                status="failed",
                progress_percent=100.0,
                message="分集生成失败",
                error_message=str(e),
                event_type="failed",
            )
        await db.commit()
        raise HTTPException(status_code=500, detail=f"视频生成失败: {e}")


@router.post("/panels/{panel_id}/retry", response_model=ApiResponse[dict])
async def retry_panel(panel_id: str, db: AsyncSession = Depends(get_db)):
    """重试单个分镜的视频生成"""
    project, panel, scene = await _sync_and_resolve_scene_for_panel(panel_id, db)
    _ensure_scene_has_prompt(scene, "分镜缺少视频提示词，无法生成")

    previous_status = project.status
    original_scene_status = scene.status
    await claim_project_status_or_409(
        db,
        project_id=project.id,
        target_status=PROJECT_STATUS_GENERATING,
        allowed_from_statuses=PROJECT_GENERATE_ALLOWED_FROM,
        action_label="重试分镜生成",
    )

    scene.status = SCENE_STATUS_PENDING
    await db.flush()
    generation_started = False

    try:
        # 真正进入重生成前再失效旧成片，避免初始化失败时误判旧成片不可用。
        generator = await _create_video_generator_for_panel(project, panel, db)
        generation_started = True
        clips = await generator.generate_scene(scene, db)
        await sync_panel_outputs_from_scenes(project.id, db)

        # 单分镜重试属于局部操作；若之前已有成片，则需要降回 parsed，等待重新合成。
        project.status = (
            PROJECT_STATUS_PARSED
            if previous_status == PROJECT_STATUS_COMPLETED
            else resolve_post_scene_generation_status(previous_status)
        )
        await db.commit()

        updated_panel = await _load_current_panel(panel_id, panel, db)
        return ApiResponse(data=_build_retry_panel_payload(panel_id, updated_panel.status, len(clips)))
    except Exception as e:
        if not generation_started:
            # 生成尚未启动（例如 provider 初始化失败）时，回滚分镜映射状态，避免误报失败。
            scene.status = original_scene_status
            project.status = previous_status
        else:
            if scene.status not in READY_SCENE_STATUSES:
                scene.status = SCENE_STATUS_FAILED
            project.status = resolve_generation_failure_status(previous_status, scoped_to_episode=True)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"分镜重试失败: {e}")


@router.post("/panels/{panel_id}/generate-candidates", response_model=ApiResponse[dict])
async def generate_panel_candidates(
    panel_id: str,
    candidate_count: int = Query(3, ge=1, le=10, description="候选数量"),
    db: AsyncSession = Depends(get_db),
):
    """为分镜生成多个候选视频片段"""
    project, panel, scene = await _sync_and_resolve_scene_for_panel(panel_id, db)
    _ensure_scene_has_prompt(scene, "分镜缺少视频提示词，无法生成候选")

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
        clips = await generator.generate_candidates(scene, candidate_count, db)
        await sync_panel_outputs_from_scenes(project.id, db)

        # 恢复项目状态
        project.status = resolve_post_scene_generation_status(previous_status)
        await db.commit()

        updated_panel = await _load_current_panel(panel_id, panel, db)
        return ApiResponse(data=_build_candidate_payload(panel_id, updated_panel.status, clips))
    except Exception as e:
        if not generation_started:
            project.status = previous_status
        else:
            project.status = resolve_post_scene_generation_status(previous_status)
        await db.commit()
        raise HTTPException(status_code=500, detail=f"候选生成失败: {e}")
