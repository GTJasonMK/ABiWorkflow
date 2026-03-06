from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_invalidation import (
    downgrade_project_after_generation_input_change,
    invalidate_scene_outputs_for_regeneration,
)
from app.database import get_db
from app.models import Character, Project, SceneCharacter
from app.project_status import PROJECT_BUSY_STATUSES
from app.schemas.character import CharacterResponse, CharacterUpdate
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/characters", tags=["角色管理"])


@router.get("/project/{project_id}", response_model=ApiResponse[list[CharacterResponse]])
async def list_characters(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目的所有角色"""
    stmt = select(Character).where(Character.project_id == project_id).order_by(Character.created_at)
    result = await db.execute(stmt)
    characters = result.scalars().all()
    return ApiResponse(data=[CharacterResponse.model_validate(c) for c in characters])


@router.get("/{character_id}", response_model=ApiResponse[CharacterResponse])
async def get_character(character_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个角色详情"""
    character = await _get_character_or_404(character_id, db)
    return ApiResponse(data=CharacterResponse.model_validate(character))


@router.put("/{character_id}", response_model=ApiResponse[CharacterResponse])
async def update_character(character_id: str, body: CharacterUpdate, db: AsyncSession = Depends(get_db)):
    """更新角色信息"""
    character = await _get_character_or_404(character_id, db)
    project = (await db.execute(select(Project).where(Project.id == character.project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.status in PROJECT_BUSY_STATUSES:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许编辑角色")

    update_data = body.model_dump(exclude_unset=True)
    if "name" in update_data and update_data["name"] is not None:
        normalized_name = update_data["name"].strip()
        if not normalized_name:
            raise HTTPException(status_code=400, detail="角色名称不能为空")
        duplicated = (await db.execute(
            select(Character.id).where(
                Character.project_id == character.project_id,
                Character.name == normalized_name,
                Character.id != character.id,
            )
        )).scalar_one_or_none()
        if duplicated is not None:
            raise HTTPException(status_code=400, detail="角色名称已存在，请使用不同名称")
        update_data["name"] = normalized_name

    if "reference_image_url" in update_data and update_data["reference_image_url"] is not None:
        normalized_reference = update_data["reference_image_url"].strip()
        update_data["reference_image_url"] = normalized_reference or None

    changed_fields: set[str] = set()
    for key, value in update_data.items():
        if getattr(character, key) != value:
            changed_fields.add(key)
        setattr(character, key, value)

    if "reference_image_url" in changed_fields:
        # 角色参考图会直接影响视频生成输入，必须让关联场景失效并重新生成。
        scene_ids = list((await db.execute(
            select(SceneCharacter.scene_id).where(SceneCharacter.character_id == character.id)
        )).scalars().all())
        if scene_ids:
            await invalidate_scene_outputs_for_regeneration(db, scene_ids)
            await downgrade_project_after_generation_input_change(db, project)

    await db.commit()
    await db.refresh(character)
    return ApiResponse(data=CharacterResponse.model_validate(character))


async def _get_character_or_404(character_id: str, db: AsyncSession) -> Character:
    """按 ID 查询角色，不存在时抛出 404"""
    stmt = select(Character).where(Character.id == character_id)
    result = await db.execute(stmt)
    character = result.scalar_one_or_none()
    if character is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return character


@router.post("/{character_id}/portrait", response_model=ApiResponse[CharacterResponse])
async def generate_character_portrait(character_id: str, db: AsyncSession = Depends(get_db)):
    """为角色生成立绘图片"""
    logger.info("收到立绘生成请求: character_id=%s", character_id)
    character = await _get_character_or_404(character_id, db)
    project = (await db.execute(select(Project).where(Project.id == character.project_id))).scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    if project.status in PROJECT_BUSY_STATUSES:
        raise HTTPException(status_code=409, detail=f"项目状态 {project.status} 下不允许生成立绘")

    from app.services.portrait_generator import generate_portrait

    try:
        portrait_url = await generate_portrait(
            character_id=character.id,
            name=character.name,
            appearance=character.appearance,
            costume=character.costume,
            personality=character.personality,
        )
    except ValueError as e:
        logger.warning("立绘生成失败（参数错误）: %s", e)
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("立绘生成失败: character_id=%s", character_id)
        raise HTTPException(status_code=500, detail=f"立绘生成失败: {e}")

    character.portrait_url = portrait_url
    character.reference_image_url = portrait_url
    await db.commit()
    await db.refresh(character)
    logger.info("立绘生成成功: character_id=%s, url=%s", character_id, portrait_url)
    return ApiResponse(data=CharacterResponse.model_validate(character))
