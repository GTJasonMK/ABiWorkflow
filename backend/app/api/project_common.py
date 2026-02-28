from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Character, Project, Scene
from app.schemas.project import ProjectResponse


async def get_project_or_404(project_id: str, db: AsyncSession) -> Project:
    """按 ID 查询项目，不存在时抛出 404。"""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def count_project_relations(project_id: str, db: AsyncSession) -> tuple[int, int]:
    """查询项目的场景数和角色数。"""
    scene_count = (await db.execute(
        select(func.count()).select_from(Scene).where(Scene.project_id == project_id)
    )).scalar() or 0
    character_count = (await db.execute(
        select(func.count()).select_from(Character).where(Character.project_id == project_id)
    )).scalar() or 0
    return scene_count, character_count


def to_project_response(project: Project, *, scene_count: int, character_count: int) -> ProjectResponse:
    """将 ORM 模型转为响应 Schema。"""
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        script_text=project.script_text,
        status=project.status,
        scene_count=scene_count,
        character_count=character_count,
        created_at=project.created_at,
        updated_at=project.updated_at,
    )
