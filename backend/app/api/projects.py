from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import count_project_relations, count_project_storyboard, get_project_or_404, to_project_response
from app.api.projects_workflow import workflow_router
from app.config import resolve_runtime_path, settings
from app.database import get_db
from app.models import Character, Episode, Panel, Project
from app.project_status import (
    PROJECT_BUSY_STATUSES,
    PROJECT_RESET_TO_DRAFT_ON_SCRIPT_CHANGE,
    PROJECT_STATUS_DRAFT,
)
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectListItem, ProjectResponse, ProjectUpdate
from app.services.composition_state import mark_completed_compositions_stale

router = APIRouter(prefix="/projects", tags=["项目管理"])
logger = logging.getLogger(__name__)

# 允许排序的字段白名单
_SORT_COLUMNS = {
    "created_at": Project.created_at,
    "updated_at": Project.updated_at,
    "name": Project.name,
}


@router.post("", response_model=ApiResponse[ProjectResponse])
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    """创建新项目"""
    normalized_name = body.name.strip()
    if not normalized_name:
        raise HTTPException(status_code=400, detail="项目名称不能为空")

    project = Project(name=normalized_name, description=body.description)
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return ApiResponse(data=to_project_response(
        project,
        character_count=0,
        episode_count=0,
        panel_count=0,
        generated_panel_count=0,
    ))


@router.get("", response_model=ApiResponse[PaginatedResponse[ProjectListItem]])
async def list_projects(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query("", description="按项目名称模糊搜索"),
    status: str = Query("", description="按状态筛选，多个状态用逗号分隔"),
    sort_by: str = Query("created_at", description="排序字段：created_at / updated_at / name"),
    sort_order: str = Query("desc", description="排序方向：asc / desc"),
    db: AsyncSession = Depends(get_db),
):
    """获取项目列表（分页），支持搜索、筛选和排序"""
    # 构建过滤条件
    filters = []
    if keyword.strip():
        filters.append(Project.name.ilike(f"%{keyword.strip()}%"))
    if status.strip():
        status_list = [s.strip() for s in status.split(",") if s.strip()]
        if status_list:
            filters.append(Project.status.in_(status_list))

    # 全局状态聚合（不受搜索/筛选影响，始终反映全库数据）
    stats_rows = (await db.execute(
        select(Project.status, func.count(Project.id)).group_by(Project.status)
    )).all()
    stats = {row[0]: row[1] for row in stats_rows}

    # 计数（受搜索/筛选影响）
    count_stmt = select(func.count()).select_from(Project)
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = (await db.execute(count_stmt)).scalar() or 0

    # 排序
    sort_column = _SORT_COLUMNS.get(sort_by, Project.created_at)
    order_clause = sort_column.asc() if sort_order == "asc" else sort_column.desc()

    # 分页查询
    stmt = select(Project).order_by(order_clause).offset((page - 1) * page_size).limit(page_size)
    for f in filters:
        stmt = stmt.where(f)
    result = await db.execute(stmt)
    projects = result.scalars().all()

    # 批量查询分镜统计和角色数
    project_ids = [p.id for p in projects]
    episode_count_map: dict[str, int] = {}
    panel_count_map: dict[str, int] = {}
    generated_panel_count_map: dict[str, int] = {}
    character_count_map: dict[str, int] = {}
    if project_ids:
        episode_count_rows = await db.execute(
            select(Episode.project_id, func.count(Episode.id))
            .where(Episode.project_id.in_(project_ids))
            .group_by(Episode.project_id)
        )
        episode_count_map = {pid: cnt for pid, cnt in episode_count_rows.all()}

        panel_count_rows = await db.execute(
            select(Panel.project_id, func.count(Panel.id))
            .where(Panel.project_id.in_(project_ids))
            .group_by(Panel.project_id)
        )
        panel_count_map = {pid: cnt for pid, cnt in panel_count_rows.all()}

        generated_panel_rows = await db.execute(
            select(Panel.project_id, func.count(Panel.id))
            .where(
                Panel.project_id.in_(project_ids),
                (Panel.video_url.is_not(None)) | (Panel.lipsync_video_url.is_not(None)),
            )
            .group_by(Panel.project_id)
        )
        generated_panel_count_map = {pid: cnt for pid, cnt in generated_panel_rows.all()}

        char_count_rows = await db.execute(
            select(Character.project_id, func.count(Character.id))
            .where(Character.project_id.in_(project_ids))
            .group_by(Character.project_id)
        )
        character_count_map = {pid: cnt for pid, cnt in char_count_rows.all()}

    items = []
    for p in projects:
        items.append(ProjectListItem(
            id=p.id,
            name=p.name,
            description=p.description,
            status=p.status,
            episode_count=episode_count_map.get(p.id, 0),
            panel_count=panel_count_map.get(p.id, 0),
            generated_panel_count=generated_panel_count_map.get(p.id, 0),
            character_count=character_count_map.get(p.id, 0),
            created_at=p.created_at,
            updated_at=p.updated_at,
        ))

    return ApiResponse(data=PaginatedResponse(
        items=items, total=total, page=page, page_size=page_size, stats=stats,
    ))


@router.get("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目详情"""
    project = await get_project_or_404(project_id, db)
    _, character_count = await count_project_relations(project.id, db)
    episode_count, panel_count, generated_panel_count = await count_project_storyboard(project.id, db)
    return ApiResponse(data=to_project_response(
        project,
        character_count=character_count,
        episode_count=episode_count,
        panel_count=panel_count,
        generated_panel_count=generated_panel_count,
    ))


@router.put("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def update_project(project_id: str, body: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    """更新项目"""
    project = await get_project_or_404(project_id, db)
    update_data = body.model_dump(exclude_unset=True)

    if update_data and project.status in PROJECT_BUSY_STATUSES:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许更新项目信息")

    if "name" in update_data and update_data["name"] is not None:
        normalized_name = update_data["name"].strip()
        if not normalized_name:
            raise HTTPException(status_code=400, detail="项目名称不能为空")
        update_data["name"] = normalized_name

    script_text_changed = "script_text" in update_data and update_data["script_text"] != project.script_text
    for key, value in update_data.items():
        setattr(project, key, value)

    if script_text_changed:
        # 剧本文本发生变化后，原解析/生成结果不再可信，需回退到 draft 重新走流程。
        if project.status in PROJECT_RESET_TO_DRAFT_ON_SCRIPT_CHANGE:
            project.status = PROJECT_STATUS_DRAFT
        await mark_completed_compositions_stale(db, project.id)

    await db.commit()
    await db.refresh(project)
    _, character_count = await count_project_relations(project.id, db)
    episode_count, panel_count, generated_panel_count = await count_project_storyboard(project.id, db)
    return ApiResponse(data=to_project_response(
        project,
        character_count=character_count,
        episode_count=episode_count,
        panel_count=panel_count,
        generated_panel_count=generated_panel_count,
    ))


@router.delete("/{project_id}", response_model=ApiResponse[None])
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """删除项目"""
    project = await get_project_or_404(project_id, db)
    if project.status in PROJECT_BUSY_STATUSES:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许删除")
    await db.delete(project)
    await db.commit()

    # 级联清理磁盘文件（按项目隔离的子目录）
    for dir_setting in (settings.video_output_dir, settings.composition_output_dir):
        project_dir = resolve_runtime_path(dir_setting) / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)

    return ApiResponse(data=None)

router.include_router(workflow_router)
