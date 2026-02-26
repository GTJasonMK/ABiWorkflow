from __future__ import annotations

import logging
import shutil

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_status import claim_project_status_or_409, try_restore_project_status
from app.api.task_mode import resolve_async_mode
from app.config import resolve_runtime_path, settings
from app.database import get_db
from app.models import Character, Project, Scene, SceneCharacter
from app.schemas.common import ApiResponse, PaginatedResponse
from app.schemas.project import ProjectCreate, ProjectListItem, ProjectResponse, ProjectUpdate
from app.services.composition_state import mark_completed_compositions_stale
from app.services.progress import publish_progress

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
    return ApiResponse(data=_to_response(project, scene_count=0, character_count=0))


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

    # 批量查询场景数和角色数
    project_ids = [p.id for p in projects]
    scene_count_map: dict[str, int] = {}
    character_count_map: dict[str, int] = {}
    if project_ids:
        scene_count_rows = await db.execute(
            select(Scene.project_id, func.count(Scene.id))
            .where(Scene.project_id.in_(project_ids))
            .group_by(Scene.project_id)
        )
        scene_count_map = {pid: cnt for pid, cnt in scene_count_rows.all()}

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
            scene_count=scene_count_map.get(p.id, 0),
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
    project = await _get_project_or_404(project_id, db)
    scene_count, character_count = await _count_relations(project.id, db)
    return ApiResponse(data=_to_response(project, scene_count=scene_count, character_count=character_count))


@router.put("/{project_id}", response_model=ApiResponse[ProjectResponse])
async def update_project(project_id: str, body: ProjectUpdate, db: AsyncSession = Depends(get_db)):
    """更新项目"""
    project = await _get_project_or_404(project_id, db)
    update_data = body.model_dump(exclude_unset=True)

    if update_data and project.status in {"parsing", "generating", "composing"}:
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
        if project.status in {"parsed", "failed", "completed"}:
            project.status = "draft"
        await mark_completed_compositions_stale(db, project.id)

    await db.commit()
    await db.refresh(project)
    scene_count, character_count = await _count_relations(project.id, db)
    return ApiResponse(data=_to_response(project, scene_count=scene_count, character_count=character_count))


@router.post("/{project_id}/parse", response_model=ApiResponse[dict])
async def parse_script(
    project_id: str,
    async_mode: bool = Query(False, description="是否异步执行解析"),
    force_recover: bool = Query(False, description="是否强制恢复卡住的 parsing 状态"),
    db: AsyncSession = Depends(get_db),
):
    """解析项目剧本：两阶段 LLM 分析"""
    project = await _get_project_or_404(project_id, db)
    if not project.script_text or not project.script_text.strip():
        raise HTTPException(status_code=400, detail="请先输入剧本内容")

    if force_recover and project.status == "parsing":
        has_scene = (await db.execute(
            select(Scene.id).where(Scene.project_id == project_id).limit(1)
        )).scalar_one_or_none() is not None
        has_character = (await db.execute(
            select(Character.id).where(Character.project_id == project_id).limit(1)
        )).scalar_one_or_none() is not None
        project.status = "parsed" if (has_scene or has_character) else "draft"
        await db.commit()
        await db.refresh(project)

    previous_status = project.status
    script_text = project.script_text

    # 原子抢占状态，避免并发重复触发解析。
    await claim_project_status_or_409(
        db,
        project_id=project_id,
        target_status="parsing",
        allowed_from_statuses=["draft", "parsed", "failed", "completed"],
        action_label="解析剧本",
        recover_hint_status="parsing",
    )
    await db.commit()

    async_mode = resolve_async_mode(async_mode)

    if async_mode:
        try:
            from app.tasks.parse_tasks import parse_script_task

            task = parse_script_task.delay(project_id, previous_status, script_text)
            return ApiResponse(data={"task_id": task.id, "mode": "async", "status": "queued"})
        except Exception as e:
            await try_restore_project_status(db, project_id, previous_status)
            raise HTTPException(status_code=500, detail=f"解析任务提交失败: {e}")

    llm = None
    try:
        from app.llm.factory import create_llm_adapter
        from app.services.script_parser import ScriptParserService

        publish_progress(project_id, "parse_start", {"message": "开始解析剧本", "percent": 2})
        llm = create_llm_adapter()
        parser = ScriptParserService(llm)
        result = await parser.parse_script(project_id, script_text, db)
        await db.commit()
        publish_progress(project_id, "parse_complete", {
            "message": "解析完成",
            "percent": 100,
            "character_count": result.character_count,
            "scene_count": result.scene_count,
        })
        return ApiResponse(data={"character_count": result.character_count, "scene_count": result.scene_count})
    except Exception as e:
        # 回滚解析过程中的中间写入，再恢复到解析前状态。
        await db.rollback()
        project = await _get_project_or_404(project_id, db)
        project.status = previous_status
        await db.commit()
        publish_progress(project_id, "parse_failed", {"message": f"解析失败: {e}", "percent": 100})
        raise HTTPException(status_code=500, detail=f"剧本解析失败: {e}")
    finally:
        if llm is not None:
            await llm.close()


@router.post("/{project_id}/abort", response_model=ApiResponse[dict])
async def abort_project_task(project_id: str, db: AsyncSession = Depends(get_db)):
    """中止项目当前正在执行的任务（解析/生成/合成），将项目状态恢复为可操作。

    仅当项目处于 parsing / generating / composing 时生效。
    """
    project = await _get_project_or_404(project_id, db)

    busy_statuses = {"parsing", "generating", "composing"}
    if project.status not in busy_statuses:
        return ApiResponse(data={
            "aborted": False,
            "status": project.status,
            "message": f"项目当前状态为 {project.status}，无需中止",
        })

    previous_busy = project.status

    # 根据已有数据决定恢复到哪个状态
    has_scene = (await db.execute(
        select(Scene.id).where(Scene.project_id == project_id).limit(1)
    )).scalar_one_or_none() is not None

    if has_scene:
        project.status = "parsed"
    else:
        project.status = "draft"

    await db.commit()
    return ApiResponse(data={
        "aborted": True,
        "previous_status": previous_busy,
        "status": project.status,
        "message": f"已从 {previous_busy} 恢复为 {project.status}",
    })


@router.delete("/{project_id}", response_model=ApiResponse[None])
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """删除项目"""
    project = await _get_project_or_404(project_id, db)
    if project.status in {"parsing", "generating", "composing"}:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许删除")
    await db.delete(project)
    await db.commit()

    # 级联清理磁盘文件（按项目隔离的子目录）
    for dir_setting in (settings.video_output_dir, settings.composition_output_dir):
        project_dir = resolve_runtime_path(dir_setting) / project_id
        if project_dir.exists():
            shutil.rmtree(project_dir, ignore_errors=True)

    return ApiResponse(data=None)


@router.post("/{project_id}/duplicate", response_model=ApiResponse[ProjectResponse])
async def duplicate_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """复制项目（含角色和场景文本，不含生成产物）"""
    source = await _get_project_or_404(project_id, db)

    new_project = Project(
        name=f"{source.name} (副本)",
        description=source.description,
        script_text=source.script_text,
        status="draft",
    )
    db.add(new_project)
    await db.flush()

    # 复制角色，建立 old_id -> new_id 映射用于后续关联复制
    source_characters = (await db.execute(
        select(Character).where(Character.project_id == source.id)
    )).scalars().all()
    char_id_map: dict[str, str] = {}
    for ch in source_characters:
        new_ch = Character(
            project_id=new_project.id,
            name=ch.name,
            appearance=ch.appearance,
            personality=ch.personality,
            costume=ch.costume,
        )
        db.add(new_ch)
        await db.flush()
        char_id_map[ch.id] = new_ch.id

    # 复制场景（保留文本内容，清除生成状态）
    source_scenes = (await db.execute(
        select(Scene).where(Scene.project_id == source.id).order_by(Scene.sequence_order)
    )).scalars().all()
    for sc in source_scenes:
        new_scene = Scene(
            project_id=new_project.id,
            sequence_order=sc.sequence_order,
            title=sc.title,
            description=sc.description,
            video_prompt=sc.video_prompt,
            negative_prompt=sc.negative_prompt,
            camera_movement=sc.camera_movement,
            setting=sc.setting,
            style_keywords=sc.style_keywords,
            dialogue=sc.dialogue,
            duration_seconds=sc.duration_seconds,
            transition_hint=sc.transition_hint,
            status="pending",
        )
        db.add(new_scene)
        await db.flush()

        # 复制场景-角色关联
        source_links = (await db.execute(
            select(SceneCharacter).where(SceneCharacter.scene_id == sc.id)
        )).scalars().all()
        for link in source_links:
            new_char_id = char_id_map.get(link.character_id)
            if new_char_id:
                db.add(SceneCharacter(
                    scene_id=new_scene.id,
                    character_id=new_char_id,
                    action=link.action,
                    emotion=link.emotion,
                ))

    await db.commit()
    await db.refresh(new_project)

    scene_count, character_count = await _count_relations(new_project.id, db)
    return ApiResponse(data=_to_response(new_project, scene_count=scene_count, character_count=character_count))


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
