from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Character
from app.schemas.character import CharacterResponse, CharacterUpdate
from app.schemas.common import ApiResponse

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
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(character, key, value)
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
