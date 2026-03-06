from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import get_episode_or_404
from app.api.response_utils import isoformat_or_empty
from app.database import get_db
from app.models import Episode, Panel
from app.schemas.common import ApiResponse

router = APIRouter(tags=["分集管理"])


class EpisodeCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    summary: str | None = None
    script_text: str | None = None


class EpisodeUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    summary: str | None = None
    script_text: str | None = None
    status: str | None = None


class EpisodeReorderRequest(BaseModel):
    episode_ids: list[str]


class EpisodeResponse(BaseModel):
    id: str
    project_id: str
    episode_order: int
    title: str
    summary: str | None
    script_text: str | None
    status: str
    panel_count: int = 0
    created_at: str
    updated_at: str


def _to_episode_response(episode: Episode, panel_count: int = 0) -> EpisodeResponse:
    return EpisodeResponse(
        id=episode.id,
        project_id=episode.project_id,
        episode_order=episode.episode_order,
        title=episode.title,
        summary=episode.summary,
        script_text=episode.script_text,
        status=episode.status,
        panel_count=panel_count,
        created_at=isoformat_or_empty(episode.created_at),
        updated_at=isoformat_or_empty(episode.updated_at),
    )



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
    return ApiResponse(data=[_to_episode_response(item, panel_count_map.get(item.id, 0)) for item in episodes])


@router.post("/projects/{project_id}/episodes", response_model=ApiResponse[EpisodeResponse])
async def create_episode(project_id: str, body: EpisodeCreate, db: AsyncSession = Depends(get_db)):
    title = body.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="分集标题不能为空")

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
    db.add(episode)
    await db.commit()
    await db.refresh(episode)
    return ApiResponse(data=_to_episode_response(episode))


@router.get("/episodes/{episode_id}", response_model=ApiResponse[EpisodeResponse])
async def get_episode(episode_id: str, db: AsyncSession = Depends(get_db)):
    episode = await get_episode_or_404(episode_id, db)
    panel_count = (await db.execute(
        select(func.count(Panel.id)).where(Panel.episode_id == episode_id)
    )).scalar() or 0
    return ApiResponse(data=_to_episode_response(episode, int(panel_count)))


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
    if "status" in updates and updates["status"] is not None:
        episode.status = str(updates["status"]).strip() or episode.status

    await db.commit()
    await db.refresh(episode)
    panel_count = (await db.execute(
        select(func.count(Panel.id)).where(Panel.episode_id == episode_id)
    )).scalar() or 0
    return ApiResponse(data=_to_episode_response(episode, int(panel_count)))


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
