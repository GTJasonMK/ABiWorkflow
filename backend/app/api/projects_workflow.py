from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import (
    get_project_aggregate_counts,
    get_project_or_404,
    to_project_response,
)
from app.api.project_status import (
    claim_project_status_or_409,
    commit_project_status,
    restore_project_status_and_raise_submit_error,
    rollback_and_restore_project_status,
)
from app.api.task_mode import resolve_async_mode
from app.api.task_submission import submit_async_task_with_record
from app.database import get_db
from app.models import Character, Episode, Panel, Project
from app.panel_status import PANEL_STATUS_PENDING
from app.progress_payload import (
    PROGRESS_KEY_CHARACTER_COUNT,
    PROGRESS_KEY_EPISODE_COUNT,
    PROGRESS_KEY_MESSAGE,
    PROGRESS_KEY_PANEL_COUNT,
    PROGRESS_KEY_PERCENT,
)
from app.project_status import (
    PROJECT_BUSY_STATUSES,
    PROJECT_PARSE_ALLOWED_FROM,
    PROJECT_STATUS_DRAFT,
    PROJECT_STATUS_PARSED,
    PROJECT_STATUS_PARSING,
)
from app.schemas.common import ApiResponse
from app.schemas.project import ProjectResponse
from app.services.episode_import import split_by_markers, split_with_llm
from app.services.episode_parse_pipeline import parse_project_from_episodes
from app.services.progress import publish_progress

workflow_router = APIRouter()
logger = logging.getLogger(__name__)


class ImportSplitRequest(BaseModel):
    content: str = Field(min_length=100, description="待切分的原始文案")

def _build_parse_result_payload(result) -> dict:
    return {
        "character_count": result.character_count,
        "panel_count": result.panel_count,
        "episode_count": result.episode_count,
    }


def _publish_parse_progress(project_id: str, event_type: str, message: str, *, percent: int, result=None) -> None:
    payload = {
        PROGRESS_KEY_MESSAGE: message,
        PROGRESS_KEY_PERCENT: percent,
    }
    if result is not None:
        payload.update({
            PROGRESS_KEY_CHARACTER_COUNT: result.character_count,
            PROGRESS_KEY_PANEL_COUNT: result.panel_count,
            PROGRESS_KEY_EPISODE_COUNT: result.episode_count,
        })
    publish_progress(project_id, event_type, payload)


def _duplicate_character_row(source: Character, project_id: str) -> Character:
    return Character(
        project_id=project_id,
        name=source.name,
        appearance=source.appearance,
        personality=source.personality,
        costume=source.costume,
    )


def _duplicate_episode_row(source: Episode, project_id: str) -> Episode:
    return Episode(
        project_id=project_id,
        episode_order=source.episode_order,
        title=source.title,
        summary=source.summary,
        script_text=source.script_text,
        video_provider_key=source.video_provider_key,
        tts_provider_key=source.tts_provider_key,
        lipsync_provider_key=source.lipsync_provider_key,
        provider_payload_defaults_json=source.provider_payload_defaults_json,
        skipped_checks_json=source.skipped_checks_json,
        status=source.status,
    )


def _duplicate_panel_row(source: Panel, project_id: str, episode_id: str) -> Panel:
    return Panel(
        project_id=project_id,
        episode_id=episode_id,
        panel_order=source.panel_order,
        title=source.title,
        script_text=source.script_text,
        visual_prompt=source.visual_prompt,
        negative_prompt=source.negative_prompt,
        camera_hint=source.camera_hint,
        duration_seconds=source.duration_seconds,
        reference_image_url=source.reference_image_url,
        style_preset=source.style_preset,
        tts_text=source.tts_text,
        status=PANEL_STATUS_PENDING,
    )


@workflow_router.post("/{project_id}/parse", response_model=ApiResponse[dict])
async def parse_script(
    project_id: str,
    async_mode: bool = Query(False, description="是否异步执行解析"),
    db: AsyncSession = Depends(get_db),
):
    """解析项目剧本：两阶段 LLM 分析"""
    project = await get_project_or_404(project_id, db)
    if not project.script_text or not project.script_text.strip():
        raise HTTPException(status_code=400, detail="请先输入剧本内容")

    previous_status = project.status
    script_text = project.script_text
    async_mode = resolve_async_mode(async_mode)

    # 原子抢占状态，避免并发重复触发解析。
    await claim_project_status_or_409(
        db,
        project_id=project_id,
        target_status=PROJECT_STATUS_PARSING,
        allowed_from_statuses=PROJECT_PARSE_ALLOWED_FROM,
        action_label="解析剧本",
    )
    await db.commit()

    if async_mode:
        try:
            from app.tasks.parse_tasks import parse_script_task

            return ApiResponse(data=await submit_async_task_with_record(
                db,
                submit=lambda: parse_script_task.delay(project_id, previous_status, script_text),
                task_type="parse",
                target_type="project",
                target_id=project_id,
                project_id=project_id,
                message="解析任务已排队",
                payload={"project_id": project_id},
            ))
        except Exception as exc:  # noqa: BLE001
            await restore_project_status_and_raise_submit_error(
                db,
                project_id=project_id,
                fallback_status=previous_status,
                detail_prefix="解析任务提交失败",
                error=exc,
            )

    llm = None
    try:
        from app.llm.factory import create_llm_adapter

        _publish_parse_progress(project_id, "parse_start", "开始解析剧本", percent=2)
        llm = create_llm_adapter()
        result = await parse_project_from_episodes(project_id, script_text, llm, db)
        await db.commit()
        _publish_parse_progress(project_id, "parse_complete", "解析完成", percent=100, result=result)
        return ApiResponse(data=_build_parse_result_payload(result))
    except Exception as exc:  # noqa: BLE001
        # 回滚解析过程中的中间写入，再恢复到解析前状态。
        await rollback_and_restore_project_status(
            db,
            project_id=project_id,
            fallback_status=previous_status,
        )
        _publish_parse_progress(project_id, "parse_failed", f"解析失败: {exc}", percent=100)
        raise HTTPException(status_code=500, detail=f"剧本解析失败: {exc}")
    finally:
        if llm is not None:
            await llm.close()


@workflow_router.post("/{project_id}/abort", response_model=ApiResponse[dict])
async def abort_project_task(project_id: str, db: AsyncSession = Depends(get_db)):
    """中止项目当前正在执行的任务（解析/生成/合成），将项目状态恢复为可操作。"""
    project = await get_project_or_404(project_id, db)

    if project.status not in PROJECT_BUSY_STATUSES:
        return ApiResponse(data={
            "aborted": False,
            "status": project.status,
            "message": f"项目当前状态为 {project.status}，无需中止",
        })

    previous_busy = project.status
    await commit_project_status(
        db,
        project,
        PROJECT_STATUS_PARSED,
    )
    return ApiResponse(data={
        "aborted": True,
        "previous_status": previous_busy,
        "status": project.status,
        "message": f"已从 {previous_busy} 恢复为 {project.status}",
    })


@workflow_router.post("/{project_id}/duplicate", response_model=ApiResponse[ProjectResponse])
async def duplicate_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """复制项目（含角色与分集分镜文本，不含生成产物）"""
    source = await get_project_or_404(project_id, db)

    new_project = Project(
        name=f"{source.name} (副本)",
        description=source.description,
        script_text=source.script_text,
        default_video_provider_key=source.default_video_provider_key,
        default_tts_provider_key=source.default_tts_provider_key,
        default_lipsync_provider_key=source.default_lipsync_provider_key,
        default_provider_payload_defaults_json=source.default_provider_payload_defaults_json,
        status=PROJECT_STATUS_DRAFT,
    )
    db.add(new_project)
    await db.flush()

    source_characters = (await db.execute(
        select(Character).where(Character.project_id == source.id)
    )).scalars().all()
    if source_characters:
        db.add_all([_duplicate_character_row(character, new_project.id) for character in source_characters])

    source_episodes = (await db.execute(
        select(Episode)
        .where(Episode.project_id == source.id)
        .order_by(Episode.episode_order, Episode.created_at)
    )).scalars().all()
    source_panels = (await db.execute(
        select(Panel)
        .join(Episode, Panel.episode_id == Episode.id)
        .where(Panel.project_id == source.id)
        .order_by(Episode.episode_order, Panel.panel_order, Panel.created_at)
    )).scalars().all()

    copied_episodes = [_duplicate_episode_row(episode, new_project.id) for episode in source_episodes]
    if copied_episodes:
        db.add_all(copied_episodes)
        await db.flush()
    episode_id_map = {
        source_episode.id: copied_episode.id
        for source_episode, copied_episode in zip(source_episodes, copied_episodes)
    }

    copied_panels = [
        _duplicate_panel_row(panel, new_project.id, mapped_episode_id)
        for panel in source_panels
        if (mapped_episode_id := episode_id_map.get(panel.episode_id)) is not None
    ]
    if copied_panels:
        db.add_all(copied_panels)

    await db.commit()
    await db.refresh(new_project)

    counts = await get_project_aggregate_counts(new_project.id, db)
    return ApiResponse(data=to_project_response(
        new_project,
        character_count=counts.character_count,
        episode_count=counts.episode_count,
        panel_count=counts.panel_count,
        generated_panel_count=counts.generated_panel_count,
    ))


@workflow_router.post("/{project_id}/import/marker-split", response_model=ApiResponse[dict])
async def marker_split_import(
    project_id: str,
    body: ImportSplitRequest,
    db: AsyncSession = Depends(get_db),
):
    """根据分集标识符切分文案，不调用远程模型。"""
    await get_project_or_404(project_id, db)
    result = split_by_markers(body.content)
    return ApiResponse(data=result)


@workflow_router.post("/{project_id}/import/llm-split", response_model=ApiResponse[dict])
async def llm_split_import(
    project_id: str,
    body: ImportSplitRequest,
    async_mode: bool = Query(True, description="是否异步执行 AI 分集"),
    db: AsyncSession = Depends(get_db),
):
    """AI 分集。"""
    await get_project_or_404(project_id, db)
    async_mode = resolve_async_mode(async_mode, fallback_to_sync=True)

    if async_mode:
        try:
            from app.tasks.import_tasks import split_episodes_llm_task

            return ApiResponse(data=await submit_async_task_with_record(
                db,
                submit=lambda: split_episodes_llm_task.delay(project_id, body.content),
                task_type="episode_split_llm",
                target_type="project",
                target_id=project_id,
                project_id=project_id,
                message="AI 分集任务已排队",
                payload={"project_id": project_id, "content": body.content},
            ))
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"AI 分集任务提交失败: {exc}") from exc

    try:
        result = await split_with_llm(body.content)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"AI 分集失败: {exc}") from exc
    return ApiResponse(data=result)
