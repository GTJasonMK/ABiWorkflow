from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Character, Episode, Panel, Project
from app.schemas.project import ProjectResponse
from app.services.project_workflow_defaults import read_project_workflow_defaults


async def get_project_or_404(project_id: str, db: AsyncSession) -> Project:
    """按 ID 查询项目，不存在时抛出 404。"""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def get_episode_in_project_or_404(project_id: str, episode_id: str, db: AsyncSession) -> Episode:
    """按项目范围查询分集，不存在时抛出 404。"""
    stmt = select(Episode).where(Episode.id == episode_id, Episode.project_id == project_id)
    result = await db.execute(stmt)
    episode = result.scalar_one_or_none()
    if episode is None:
        raise HTTPException(status_code=404, detail="分集不存在")
    return episode


async def get_episode_or_404(episode_id: str, db: AsyncSession) -> Episode:
    """按 ID 查询分集，不存在时抛出 404。"""
    stmt = select(Episode).where(Episode.id == episode_id)
    result = await db.execute(stmt)
    episode = result.scalar_one_or_none()
    if episode is None:
        raise HTTPException(status_code=404, detail="分集不存在")
    return episode


async def get_panel_or_404(panel_id: str, db: AsyncSession) -> Panel:
    """按 ID 查询分镜，不存在时抛出 404。"""
    stmt = select(Panel).where(Panel.id == panel_id)
    result = await db.execute(stmt)
    panel = result.scalar_one_or_none()
    if panel is None:
        raise HTTPException(status_code=404, detail="分镜不存在")
    return panel


@dataclass(frozen=True, slots=True)
class ProjectAggregateCounts:
    character_count: int = 0
    episode_count: int = 0
    panel_count: int = 0
    generated_panel_count: int = 0


async def get_project_aggregate_counts(project_id: str, db: AsyncSession) -> ProjectAggregateCounts:
    stmt = select(
        select(func.count()).select_from(Character).where(Character.project_id == project_id).scalar_subquery(),
        select(func.count()).select_from(Episode).where(Episode.project_id == project_id).scalar_subquery(),
        select(func.count()).select_from(Panel).where(Panel.project_id == project_id).scalar_subquery(),
        select(func.count()).select_from(Panel).where(
            Panel.project_id == project_id,
            (Panel.video_url.is_not(None)) | (Panel.lipsync_video_url.is_not(None)),
        ).scalar_subquery(),
    )
    row = (await db.execute(stmt)).one()
    return ProjectAggregateCounts(
        character_count=int(row[0] or 0),
        episode_count=int(row[1] or 0),
        panel_count=int(row[2] or 0),
        generated_panel_count=int(row[3] or 0),
    )


def to_project_response(
    project: Project,
    *,
    character_count: int,
    episode_count: int = 0,
    panel_count: int = 0,
    generated_panel_count: int = 0,
) -> ProjectResponse:
    """将 ORM 模型转为响应 Schema。"""
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        script_text=project.script_text,
        status=project.status,
        episode_count=episode_count,
        panel_count=panel_count,
        generated_panel_count=generated_panel_count,
        character_count=character_count,
        workflow_defaults=read_project_workflow_defaults(project),
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
