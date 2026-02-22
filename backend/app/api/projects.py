from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Character, Project, Scene
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectListItem, ProjectResponse, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["项目管理"])


@router.post("", response_model=ApiResponse[ProjectResponse])
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """创建新项目"""
    project = Project(name=body.name, description=body.description)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ApiResponse(data=_to_response(project, scene_count=0, character_count=0))


@router.get("", response_model=ApiResponse[PaginatedResponse[ProjectListItem]])
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取项目列表（分页）"""
    count_stmt = select(func.count()).select_from(Project)
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Project)
        .order_by(Project.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    projects = result.scalars().all()

    items = []
    for p in projects:
        scene_count_stmt = select(func.count()).select_from(Scene).where(Scene.project_id == p.id)
        scene_count = (await db.execute(scene_count_stmt)).scalar() or 0
        items.append(ProjectListItem(
            id=p.id,
            name=p.name,
            description=p.description,
            status=p.status,
            scene_count=scene_count,
            created_at=p.created_at,
            updated_at=p.updated_at,
        ))

    return ApiResponse(data=PaginatedResponse(items=items, total=total, page=page, page_size=page_size))


@router.get("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目详情"""
    project = await _get_project_or_404(project_id, db)
    scene_count, character_count = await _count_relations(project.id, db)
    return ApiResponse(data=_to_response(project, scene_count=scene_count, character_count=character_count))


@router.put("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def update_project(project_id: str, body: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    """更新项目"""
    project = await _get_project_or_404(project_id, db)
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(project, key, value)
    await db.commit()
    await db.refresh(project)
    scene_count, character_count = await _count_relations(project.id, db)
    return ApiResponse(data=_to_response(project, scene_count=scene_count, character_count=character_count))


@router.post("/{project_id}/parse", response_model=ApiResponse[dict])
async def parse_script(project_id: str, db: AsyncSession = Depends(get_db)):
    """解析项目剧本：两阶段 LLM 分析"""
    project = await _get_project_or_404(project_id, db)
    if not project.script_text or not project.script_text.strip():
        raise HTTPException(status_code=400, detail="请先输入剧本内容")

    # 更新状态为解析中
    project.status = "parsing"
    await db.commit()

    llm = None
    try:
        from app.llm.factory import create_llm_adapter
        from app.services.script_parser import ScriptParserService

        llm = create_llm_adapter()
        parser = ScriptParserService(llm)
        result = await parser.parse_script(project_id, project.script_text, db)
        await db.commit()
        return ApiResponse(data={"character_count": result.character_count, "scene_count": result.scene_count})
    except Exception as e:
        # 回滚解析过程中的中间写入，再恢复到草稿态
        await db.rollback()
        project = await _get_project_or_404(project_id, db)
        project.status = "draft"
        await db.commit()
        raise HTTPException(status_code=500, detail=f"剧本解析失败: {e}")
    finally:
        if llm is not None:
            await llm.close()


@router.delete("/{project_id}", response_model=ApiResponse[None])
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """删除项目"""
    project = await _get_project_or_404(project_id, db)
    await db.delete(project)
    await db.commit()
    return ApiResponse(data=None)


async def _get_project_or_404(project_id: str, db: AsyncSession) -> Project:
    """按 ID 查询项目，不存在时抛出 404"""
    stmt = select(Project).where(Project.id == project_id)
    result = await db.execute(stmt)
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


async def _count_relations(project_id: str, db: AsyncSession) -> tuple[int, int]:
    """查询项目的场景数和角色数"""
    scene_count = (await db.execute(
        select(func.count()).select_from(Scene).where(Scene.project_id == project_id)
    )).scalar() or 0
    character_count = (await db.execute(
        select(func.count()).select_from(Character).where(Character.project_id == project_id)
    )).scalar() or 0
    return scene_count, character_count


def _to_response(project: Project, *, scene_count: int, character_count: int) -> ProjectResponse:
    """将 ORM 模型转为响应 Schema"""
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
