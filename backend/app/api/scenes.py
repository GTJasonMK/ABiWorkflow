from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models import Scene, SceneCharacter
from app.schemas.common import ApiResponse
from app.schemas.scene import SceneCharacterResponse, SceneReorderRequest, SceneResponse, SceneUpdate

router = APIRouter(prefix="/scenes", tags=["场景管理"])


@router.get("/project/{project_id}", response_model=ApiResponse[list[SceneResponse]])
async def list_scenes(project_id: str, db: AsyncSession = Depends(get_db)):
    """获取项目的所有场景"""
    stmt = (
        select(Scene)
        .where(Scene.project_id == project_id)
        .options(selectinload(Scene.characters).selectinload(SceneCharacter.character))
        .order_by(Scene.sequence_order)
    )
    result = await db.execute(stmt)
    scenes = result.scalars().all()
    return ApiResponse(data=[_to_response(s) for s in scenes])


@router.get("/{scene_id}", response_model=ApiResponse[SceneResponse])
async def get_scene(scene_id: str, db: AsyncSession = Depends(get_db)):
    """获取单个场景详情"""
    scene = await _get_scene_or_404(scene_id, db)
    return ApiResponse(data=_to_response(scene))


@router.put("/{scene_id}", response_model=ApiResponse[SceneResponse])
async def update_scene(scene_id: str, body: SceneUpdate, db: AsyncSession = Depends(get_db)):
    """更新场景信息"""
    scene = await _get_scene_or_404(scene_id, db)
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(scene, key, value)
    await db.commit()
    await db.refresh(scene)
    # 重新加载关联
    scene = await _get_scene_or_404(scene_id, db)
    return ApiResponse(data=_to_response(scene))


@router.delete("/{scene_id}", response_model=ApiResponse[None])
async def delete_scene(scene_id: str, db: AsyncSession = Depends(get_db)):
    """删除场景"""
    scene = await _get_scene_or_404(scene_id, db)
    await db.delete(scene)
    await db.commit()
    return ApiResponse(data=None)


@router.put("/project/{project_id}/reorder", response_model=ApiResponse[None])
async def reorder_scenes(project_id: str, body: SceneReorderRequest, db: AsyncSession = Depends(get_db)):
    """重新排序场景"""
    for idx, scene_id in enumerate(body.scene_ids):
        stmt = select(Scene).where(Scene.id == scene_id, Scene.project_id == project_id)
        result = await db.execute(stmt)
        scene = result.scalar_one_or_none()
        if scene is None:
            raise HTTPException(status_code=404, detail=f"场景 {scene_id} 不存在")
        scene.sequence_order = idx
    await db.commit()
    return ApiResponse(data=None)


async def _get_scene_or_404(scene_id: str, db: AsyncSession) -> Scene:
    """按 ID 查询场景，不存在时抛出 404"""
    stmt = (
        select(Scene)
        .where(Scene.id == scene_id)
        .options(selectinload(Scene.characters).selectinload(SceneCharacter.character))
    )
    result = await db.execute(stmt)
    scene = result.scalar_one_or_none()
    if scene is None:
        raise HTTPException(status_code=404, detail="场景不存在")
    return scene


def _to_response(scene: Scene) -> SceneResponse:
    """将 ORM 模型转为响应"""
    characters = []
    for sc in scene.characters:
        characters.append(SceneCharacterResponse(
            character_id=sc.character_id,
            character_name=sc.character.name if sc.character else "",
            action=sc.action,
            emotion=sc.emotion,
        ))
    return SceneResponse(
        id=scene.id,
        project_id=scene.project_id,
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
        status=scene.status,
        characters=characters,
        created_at=scene.created_at,
        updated_at=scene.updated_at,
    )
