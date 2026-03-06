from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import (
    count_project_relations,
    count_project_storyboard,
    get_project_or_404,
    to_project_response,
)
from app.api.project_status import (
    claim_project_status_or_409,
    force_recover_project_status,
    restore_project_status_and_raise_submit_error,
)
from app.api.task_mode import resolve_async_mode
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
from app.services.task_records import create_task_record

workflow_router = APIRouter()
logger = logging.getLogger(__name__)


class ImportSplitRequest(BaseModel):
    content: str = Field(min_length=100, description="待切分的原始文案")


class ImportEpisodeDraft(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    script_text: str = Field(min_length=1)


class ImportCommitRequest(BaseModel):
    episodes: list[ImportEpisodeDraft]


def _normalize_import_episodes(raw_episodes: list[ImportEpisodeDraft]) -> list[ImportEpisodeDraft]:
    normalized: list[ImportEpisodeDraft] = []
    for item in raw_episodes:
        title = (item.title or "").strip()
        script_text = (item.script_text or "").strip()
        if not title or not script_text:
            continue
        normalized.append(
            ImportEpisodeDraft(
                title=title[:200],
                summary=((item.summary or "").strip() or None),
                script_text=script_text,
            )
        )
    return normalized


def _merge_import_episodes_to_script(episodes: list[ImportEpisodeDraft]) -> str:
    segments: list[str] = []
    for index, item in enumerate(episodes):
        heading = item.title
        if not heading.startswith("第"):
            heading = f"第{index + 1}集 {heading}"
        segments.append(f"{heading}\n{item.script_text.strip()}")
    return "\n\n".join(segments).strip()


async def _project_has_structured_parse_data(project_id: str, db: AsyncSession) -> bool:
    for model in (Panel, Episode, Character):
        exists = (await db.execute(
            select(model.id).where(model.project_id == project_id).limit(1)
        )).scalar_one_or_none()
        if exists is not None:
            return True
    return False


def _resolve_project_recover_status(has_structured_data: bool) -> str:
    return PROJECT_STATUS_DRAFT if not has_structured_data else PROJECT_STATUS_PARSED


@workflow_router.post("/{project_id}/parse", response_model=ApiResponse[dict])
async def parse_script(
    project_id: str,
    async_mode: bool = Query(False, description="是否异步执行解析"),
    force_recover: bool = Query(False, description="是否强制恢复卡住的 parsing 状态"),
    db: AsyncSession = Depends(get_db),
):
    """解析项目剧本：两阶段 LLM 分析"""
    project = await get_project_or_404(project_id, db)
    if not project.script_text or not project.script_text.strip():
        raise HTTPException(status_code=400, detail="请先输入剧本内容")

    if force_recover and project.status == PROJECT_STATUS_PARSING:
        await force_recover_project_status(
            db,
            project=project,
            busy_status=PROJECT_STATUS_PARSING,
            recovered_status=_resolve_project_recover_status(
                await _project_has_structured_parse_data(project_id, db)
            ),
        )

    previous_status = project.status
    script_text = project.script_text

    # 原子抢占状态，避免并发重复触发解析。
    await claim_project_status_or_409(
        db,
        project_id=project_id,
        target_status=PROJECT_STATUS_PARSING,
        allowed_from_statuses=PROJECT_PARSE_ALLOWED_FROM,
        action_label="解析剧本",
        recover_hint_status=PROJECT_STATUS_PARSING,
    )
    await db.commit()

    async_mode = resolve_async_mode(async_mode)

    if async_mode:
        try:
            from app.tasks.parse_tasks import parse_script_task

            task = parse_script_task.delay(project_id, previous_status, script_text)
            await create_task_record(
                db,
                task_type="parse",
                target_type="project",
                target_id=project_id,
                project_id=project_id,
                source_task_id=task.id,
                status="pending",
                message="解析任务已排队",
                payload={"project_id": project_id},
            )
            await db.commit()
            return ApiResponse(data={"task_id": task.id, "mode": "async", "status": "queued"})
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

        publish_progress(project_id, "parse_start", {PROGRESS_KEY_MESSAGE: "开始解析剧本", PROGRESS_KEY_PERCENT: 2})
        llm = create_llm_adapter()
        result = await parse_project_from_episodes(project_id, script_text, llm, db)
        await db.commit()
        publish_progress(project_id, "parse_complete", {
            PROGRESS_KEY_MESSAGE: "解析完成",
            PROGRESS_KEY_PERCENT: 100,
            PROGRESS_KEY_CHARACTER_COUNT: result.character_count,
            PROGRESS_KEY_PANEL_COUNT: result.panel_count,
            PROGRESS_KEY_EPISODE_COUNT: result.episode_count,
        })
        return ApiResponse(data={
            "character_count": result.character_count,
            "panel_count": result.panel_count,
            "episode_count": result.episode_count,
        })
    except Exception as exc:  # noqa: BLE001
        # 回滚解析过程中的中间写入，再恢复到解析前状态。
        await db.rollback()
        project = await get_project_or_404(project_id, db)
        project.status = previous_status
        await db.commit()
        publish_progress(project_id, "parse_failed", {
            PROGRESS_KEY_MESSAGE: f"解析失败: {exc}",
            PROGRESS_KEY_PERCENT: 100,
        })
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
    project.status = _resolve_project_recover_status(
        await _project_has_structured_parse_data(project_id, db)
    )

    await db.commit()
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
        status=PROJECT_STATUS_DRAFT,
    )
    db.add(new_project)
    await db.flush()

    source_characters = (await db.execute(
        select(Character).where(Character.project_id == source.id)
    )).scalars().all()
    for character in source_characters:
        copied_character = Character(
            project_id=new_project.id,
            name=character.name,
            appearance=character.appearance,
            personality=character.personality,
            costume=character.costume,
        )
        db.add(copied_character)
        await db.flush()

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

    episode_id_map: dict[str, str] = {}
    for episode in source_episodes:
        copied_episode = Episode(
            project_id=new_project.id,
            episode_order=episode.episode_order,
            title=episode.title,
            summary=episode.summary,
            script_text=episode.script_text,
            status=episode.status,
        )
        db.add(copied_episode)
        await db.flush()
        episode_id_map[episode.id] = copied_episode.id

    for panel in source_panels:
        mapped_episode_id = episode_id_map.get(panel.episode_id)
        if mapped_episode_id is None:
            continue
        db.add(Panel(
            project_id=new_project.id,
            episode_id=mapped_episode_id,
            panel_order=panel.panel_order,
            title=panel.title,
            script_text=panel.script_text,
            visual_prompt=panel.visual_prompt,
            negative_prompt=panel.negative_prompt,
            camera_hint=panel.camera_hint,
            duration_seconds=panel.duration_seconds,
            reference_image_url=panel.reference_image_url,
            style_preset=panel.style_preset,
            tts_text=panel.tts_text,
            status=PANEL_STATUS_PENDING,
        ))

    await db.commit()
    await db.refresh(new_project)

    _, character_count = await count_project_relations(new_project.id, db)
    episode_count, panel_count, generated_panel_count = await count_project_storyboard(new_project.id, db)
    return ApiResponse(data=to_project_response(
        new_project,
        character_count=character_count,
        episode_count=episode_count,
        panel_count=panel_count,
        generated_panel_count=generated_panel_count,
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
    """AI 分集（失败会自动回退到规则切分）。"""
    await get_project_or_404(project_id, db)
    async_mode = resolve_async_mode(async_mode)

    if async_mode:
        try:
            from app.tasks.import_tasks import split_episodes_llm_task

            task = split_episodes_llm_task.delay(project_id, body.content)
            await create_task_record(
                db,
                task_type="episode_split_llm",
                target_type="project",
                target_id=project_id,
                project_id=project_id,
                source_task_id=task.id,
                status="pending",
                message="AI 分集任务已排队",
                payload={"project_id": project_id, "content": body.content},
            )
            await db.commit()
            return ApiResponse(data={"task_id": task.id, "mode": "async", "status": "queued"})
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"AI 分集任务提交失败: {exc}") from exc

    result = await split_with_llm(body.content)
    return ApiResponse(data=result)


@workflow_router.post("/{project_id}/import/commit", response_model=ApiResponse[dict])
async def commit_import(
    project_id: str,
    body: ImportCommitRequest,
    async_mode: bool = Query(True, description="是否在导入后直接触发解析"),
    db: AsyncSession = Depends(get_db),
):
    """确认导入分集草稿，合并回项目剧本（解析统一走 /parse 单轨）。"""
    project = await get_project_or_404(project_id, db)
    if project.status in PROJECT_BUSY_STATUSES:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许导入分集")

    normalized = _normalize_import_episodes(body.episodes)
    if not normalized:
        raise HTTPException(status_code=400, detail="没有可写入的有效分集数据")

    merged_script = _merge_import_episodes_to_script(normalized)
    if not merged_script:
        raise HTTPException(status_code=400, detail="导入内容为空，无法更新剧本")

    project.script_text = merged_script
    await db.commit()
    parse_response = await parse_script(
        project_id=project_id,
        async_mode=async_mode,
        force_recover=False,
        db=db,
    )

    result = parse_response.data or {}
    return ApiResponse(data={
        "episode_count": len(normalized),
        "script_char_count": len(merged_script),
        "parse": result,
    })

