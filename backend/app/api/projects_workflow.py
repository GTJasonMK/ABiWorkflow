from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import count_project_relations, get_project_or_404, to_project_response
from app.api.project_status import claim_project_status_or_409, try_restore_project_status
from app.api.task_mode import resolve_async_mode
from app.database import get_db
from app.models import Character, Project, Scene, SceneCharacter
from app.project_status import (
    PROJECT_BUSY_STATUSES,
    PROJECT_PARSE_ALLOWED_FROM,
    PROJECT_STATUS_DRAFT,
    PROJECT_STATUS_PARSING,
    resolve_parse_recover_status,
)
from app.scene_status import SCENE_STATUS_PENDING
from app.schemas.common import ApiResponse
from app.schemas.project import ProjectResponse
from app.services.progress import publish_progress
from app.services.task_records import create_task_record

workflow_router = APIRouter()
logger = logging.getLogger(__name__)


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
        has_scene = (await db.execute(
            select(Scene.id).where(Scene.project_id == project_id).limit(1)
        )).scalar_one_or_none() is not None
        has_character = (await db.execute(
            select(Character.id).where(Character.project_id == project_id).limit(1)
        )).scalar_one_or_none() is not None
        project.status = resolve_parse_recover_status(has_scene or has_character)
        await db.commit()
        await db.refresh(project)

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
            await try_restore_project_status(db, project_id, previous_status)
            raise HTTPException(status_code=500, detail=f"解析任务提交失败: {exc}")

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
    except Exception as exc:  # noqa: BLE001
        # 回滚解析过程中的中间写入，再恢复到解析前状态。
        await db.rollback()
        project = await get_project_or_404(project_id, db)
        project.status = previous_status
        await db.commit()
        publish_progress(project_id, "parse_failed", {"message": f"解析失败: {exc}", "percent": 100})
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
    has_scene = (await db.execute(
        select(Scene.id).where(Scene.project_id == project_id).limit(1)
    )).scalar_one_or_none() is not None

    if has_scene:
        project.status = resolve_parse_recover_status(True)
    else:
        project.status = PROJECT_STATUS_DRAFT

    await db.commit()
    return ApiResponse(data={
        "aborted": True,
        "previous_status": previous_busy,
        "status": project.status,
        "message": f"已从 {previous_busy} 恢复为 {project.status}",
    })


@workflow_router.post("/{project_id}/duplicate", response_model=ApiResponse[ProjectResponse])
async def duplicate_project(project_id: str, db: AsyncSession = Depends(get_db)):
    """复制项目（含角色和场景文本，不含生成产物）"""
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
    char_id_map: dict[str, str] = {}
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
        char_id_map[character.id] = copied_character.id

    source_scenes = (await db.execute(
        select(Scene).where(Scene.project_id == source.id).order_by(Scene.sequence_order)
    )).scalars().all()
    for scene in source_scenes:
        copied_scene = Scene(
            project_id=new_project.id,
            sequence_order=scene.sequence_order,
            title=scene.title,
            description=scene.description,
            video_prompt=scene.video_prompt,
            negative_prompt=scene.negative_prompt,
            camera_movement=scene.camera_movement,
            setting=scene.setting,
            style_keywords=scene.style_keywords,
            dialogue=scene.dialogue,
            duration_seconds=scene.duration_seconds,
            transition_hint=scene.transition_hint,
            status=SCENE_STATUS_PENDING,
        )
        db.add(copied_scene)
        await db.flush()

        source_links = (await db.execute(
            select(SceneCharacter).where(SceneCharacter.scene_id == scene.id)
        )).scalars().all()
        for link in source_links:
            mapped_character_id = char_id_map.get(link.character_id)
            if mapped_character_id:
                db.add(SceneCharacter(
                    scene_id=copied_scene.id,
                    character_id=mapped_character_id,
                    action=link.action,
                    emotion=link.emotion,
                ))

    await db.commit()
    await db.refresh(new_project)

    scene_count, character_count = await count_project_relations(new_project.id, db)
    return ApiResponse(data=to_project_response(
        new_project,
        scene_count=scene_count,
        character_count=character_count,
    ))
