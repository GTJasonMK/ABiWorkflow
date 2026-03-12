from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import get_episode_or_404, get_project_or_404
from app.database import get_db
from app.models import Episode, Panel
from app.schemas.common import ApiResponse
from app.schemas.episode import EpisodeResponse
from app.services.episode_response_builder import build_episode_response, build_episode_responses
from app.services.episode_workflow import (
    build_episode_workflow_summaries,
)
from app.services.episode_workflow_config import (
    apply_episode_workflow_config,
    resolve_episode_create_workflow_config,
    resolve_episode_update_workflow_config,
)

router = APIRouter(tags=["分集管理"])


class EpisodeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    script_text: str | None = None
    video_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    tts_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    lipsync_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    provider_payload_defaults: dict[str, dict[str, Any]] | None = None
    skipped_checks: list[str] = Field(default_factory=list)


class EpisodeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = None
    script_text: str | None = None
    video_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    tts_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    lipsync_provider_key: str | None = Field(default=None, min_length=1, max_length=120)
    provider_payload_defaults: dict[str, dict[str, Any]] | None = None
    skipped_checks: list[str] | None = None
    status: str | None = None


class EpisodeReorderRequest(BaseModel):
    episode_ids: list[str]


@router.get("/projects/{project_id}/episodes", response_model=ApiResponse[list[EpisodeResponse]])
async def list_episodes(project_id: str, db: AsyncSession = Depends(get_db)):
    episodes = (await db.execute(
        select(Episode).where(Episode.project_id == project_id).order_by(Episode.episode_order, Episode.created_at)
    )).scalars().all()
    if not episodes:
        return ApiResponse(data=[])

    count_rows = (await db.execute(
        select(Panel.episode_id, func.count(Panel.id))
        .where(Panel.project_id == project_id)
        .group_by(Panel.episode_id)
    )).all()
    panel_count_map = {episode_id: int(count or 0) for episode_id, count in count_rows}
    data = await build_episode_responses(episodes, db=db, panel_count_map=panel_count_map)
    return ApiResponse(data=data)


@router.post("/projects/{project_id}/episodes", response_model=ApiResponse[EpisodeResponse])
async def create_episode(project_id: str, body: EpisodeCreate, db: AsyncSession = Depends(get_db)):
    project = await get_project_or_404(project_id, db)
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="分集标题不能为空")

    try:
        workflow_config = await resolve_episode_create_workflow_config(
            db,
            project=project,
            raw_config=body.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    max_order = (await db.execute(
        select(func.coalesce(func.max(Episode.episode_order), -1)).where(Episode.project_id == project_id)
    )).scalar_one()

    episode = Episode(
        project_id=project_id,
        episode_order=int(max_order or -1) + 1,
        title=title,
        summary=(body.summary or "").strip() or None,
        script_text=(body.script_text or "").strip() or None,
    )
    apply_episode_workflow_config(episode, workflow_config)
    db.add(episode)
    await db.commit()
    await db.refresh(episode)
    response = (await build_episode_responses([episode], db=db))[0]
    return ApiResponse(data=response)


@router.get("/episodes/{episode_id}", response_model=ApiResponse[EpisodeResponse])
async def get_episode(episode_id: str, db: AsyncSession = Depends(get_db)):
    episode = await get_episode_or_404(episode_id, db)
    panel_count = (await db.execute(
        select(func.count(Panel.id)).where(Panel.episode_id == episode_id)
    )).scalar() or 0
    workflow_summary = (await build_episode_workflow_summaries([episode], db)).get(episode.id, {})
    response = build_episode_response(
        episode,
        panel_count=int(panel_count),
        workflow_summary=workflow_summary,
    )
    return ApiResponse(data=response)


@router.put("/episodes/{episode_id}", response_model=ApiResponse[EpisodeResponse])
async def update_episode(episode_id: str, body: EpisodeUpdate, db: AsyncSession = Depends(get_db)):
    episode = await get_episode_or_404(episode_id, db)
    updates = body.model_dump(exclude_unset=True)

    if "title" in updates and updates["title"] is not None:
        title = updates["title"].strip()
        if not title:
            raise HTTPException(status_code=400, detail="分集标题不能为空")
        episode.title = title
    if "summary" in updates:
        episode.summary = (updates["summary"] or "").strip() or None
    if "script_text" in updates:
        episode.script_text = (updates["script_text"] or "").strip() or None
    try:
        workflow_config = await resolve_episode_update_workflow_config(db, raw_updates=updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    apply_episode_workflow_config(episode, workflow_config)
    if "status" in updates and updates["status"] is not None:
        episode.status = str(updates["status"]).strip() or episode.status

    await db.commit()
    await db.refresh(episode)
    panel_count = (await db.execute(
        select(func.count(Panel.id)).where(Panel.episode_id == episode_id)
    )).scalar() or 0
    workflow_summary = (await build_episode_workflow_summaries([episode], db)).get(episode.id, {})
    response = build_episode_response(
        episode,
        panel_count=int(panel_count),
        workflow_summary=workflow_summary,
    )
    return ApiResponse(data=response)


@router.delete("/episodes/{episode_id}", response_model=ApiResponse[None])
async def delete_episode(episode_id: str, db: AsyncSession = Depends(get_db)):
    episode = await get_episode_or_404(episode_id, db)
    project_id = episode.project_id
    await db.delete(episode)
    await db.flush()

    remaining = (await db.execute(
        select(Episode).where(Episode.project_id == project_id).order_by(Episode.episode_order, Episode.created_at)
    )).scalars().all()
    for idx, item in enumerate(remaining):
        item.episode_order = idx

    await db.commit()
    return ApiResponse(data=None)


@router.put("/projects/{project_id}/episodes/reorder", response_model=ApiResponse[None])
async def reorder_episodes(project_id: str, body: EpisodeReorderRequest, db: AsyncSession = Depends(get_db)):
    episodes = (await db.execute(
        select(Episode).where(Episode.project_id == project_id)
    )).scalars().all()
    existing_ids = [item.id for item in episodes]
    if len(body.episode_ids) != len(existing_ids) or set(body.episode_ids) != set(existing_ids):
        raise HTTPException(status_code=400, detail="episode_ids 必须完整覆盖当前项目分集")

    mapping = {item.id: item for item in episodes}
    for idx, episode_id in enumerate(body.episode_ids):
        mapping[episode_id].episode_order = idx
    await db.commit()
    return ApiResponse(data=None)
