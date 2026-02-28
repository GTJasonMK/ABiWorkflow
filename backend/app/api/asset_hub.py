from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import GlobalAssetFolder, GlobalCharacter, GlobalLocation, GlobalVoice
from app.schemas.common import ApiResponse
from app.services.json_codec import from_json_text, to_json_text

router = APIRouter(prefix="/asset-hub", tags=["全局资产中心"])


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    folder_type: str = "generic"
    storage_path: str | None = None
    description: str | None = None


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    folder_type: str | None = None
    storage_path: str | None = None
    description: str | None = None
    sort_order: int | None = None
    is_active: bool | None = None


class VoiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = "edge-tts"
    voice_code: str = Field(min_length=1, max_length=200)
    language: str | None = None
    gender: str | None = None
    sample_audio_url: str | None = None
    style_prompt: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class VoiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    provider: str | None = None
    voice_code: str | None = Field(default=None, min_length=1, max_length=200)
    language: str | None = None
    gender: str | None = None
    sample_audio_url: str | None = None
    style_prompt: str | None = None
    meta: dict[str, Any] | None = None
    is_active: bool | None = None


class GlobalCharacterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    alias: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    reference_image_url: str | None = None
    default_voice_id: str | None = None
    tags: list[str] = Field(default_factory=list)


class GlobalCharacterUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    alias: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    reference_image_url: str | None = None
    default_voice_id: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


class GlobalLocationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    prompt_template: str | None = None
    reference_image_url: str | None = None
    tags: list[str] = Field(default_factory=list)


class GlobalLocationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    prompt_template: str | None = None
    reference_image_url: str | None = None
    tags: list[str] | None = None
    is_active: bool | None = None


def _folder_payload(item: GlobalAssetFolder) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "folder_type": item.folder_type,
        "storage_path": item.storage_path,
        "description": item.description,
        "sort_order": item.sort_order,
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _voice_payload(item: GlobalVoice) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "provider": item.provider,
        "voice_code": item.voice_code,
        "language": item.language,
        "gender": item.gender,
        "sample_audio_url": item.sample_audio_url,
        "style_prompt": item.style_prompt,
        "meta": from_json_text(item.meta_json, {}),
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _character_payload(item: GlobalCharacter) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "alias": item.alias,
        "description": item.description,
        "prompt_template": item.prompt_template,
        "reference_image_url": item.reference_image_url,
        "default_voice_id": item.default_voice_id,
        "tags": from_json_text(item.tags_json, []),
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _location_payload(item: GlobalLocation) -> dict[str, Any]:
    return {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "prompt_template": item.prompt_template,
        "reference_image_url": item.reference_image_url,
        "tags": from_json_text(item.tags_json, []),
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("/overview", response_model=ApiResponse[dict])
async def get_asset_hub_overview(db: AsyncSession = Depends(get_db)):
    folders = (await db.execute(select(GlobalAssetFolder).order_by(GlobalAssetFolder.sort_order, GlobalAssetFolder.created_at))).scalars().all()
    characters = (await db.execute(select(GlobalCharacter).order_by(GlobalCharacter.created_at))).scalars().all()
    locations = (await db.execute(select(GlobalLocation).order_by(GlobalLocation.created_at))).scalars().all()
    voices = (await db.execute(select(GlobalVoice).order_by(GlobalVoice.created_at))).scalars().all()
    return ApiResponse(data={
        "folders": [_folder_payload(item) for item in folders],
        "characters": [_character_payload(item) for item in characters],
        "locations": [_location_payload(item) for item in locations],
        "voices": [_voice_payload(item) for item in voices],
    })


@router.get("/folders", response_model=ApiResponse[list[dict]])
async def list_asset_folders(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(GlobalAssetFolder).order_by(GlobalAssetFolder.sort_order, GlobalAssetFolder.created_at)
    )).scalars().all()
    return ApiResponse(data=[_folder_payload(item) for item in rows])


@router.post("/folders", response_model=ApiResponse[dict])
async def create_asset_folder(body: FolderCreate, db: AsyncSession = Depends(get_db)):
    entity = GlobalAssetFolder(
        name=body.name.strip(),
        folder_type=(body.folder_type or "generic").strip() or "generic",
        storage_path=(body.storage_path or "").strip() or None,
        description=(body.description or "").strip() or None,
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    return ApiResponse(data=_folder_payload(entity))


@router.put("/folders/{folder_id}", response_model=ApiResponse[dict])
async def update_asset_folder(folder_id: str, body: FolderUpdate, db: AsyncSession = Depends(get_db)):
    entity = (await db.execute(select(GlobalAssetFolder).where(GlobalAssetFolder.id == folder_id))).scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="资产目录不存在")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key in {"name", "folder_type", "storage_path", "description"} and isinstance(value, str):
            setattr(entity, key, value.strip() or None)
        else:
            setattr(entity, key, value)
    if not entity.name:
        raise HTTPException(status_code=400, detail="资产目录名称不能为空")
    await db.commit()
    await db.refresh(entity)
    return ApiResponse(data=_folder_payload(entity))


@router.delete("/folders/{folder_id}", response_model=ApiResponse[None])
async def delete_asset_folder(folder_id: str, db: AsyncSession = Depends(get_db)):
    entity = (await db.execute(select(GlobalAssetFolder).where(GlobalAssetFolder.id == folder_id))).scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="资产目录不存在")
    await db.delete(entity)
    await db.commit()
    return ApiResponse(data=None)


@router.get("/voices", response_model=ApiResponse[list[dict]])
async def list_global_voices(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(GlobalVoice).order_by(GlobalVoice.created_at))).scalars().all()
    return ApiResponse(data=[_voice_payload(item) for item in rows])


@router.post("/voices", response_model=ApiResponse[dict])
async def create_global_voice(body: VoiceCreate, db: AsyncSession = Depends(get_db)):
    voice = GlobalVoice(
        name=body.name.strip(),
        provider=(body.provider or "edge-tts").strip() or "edge-tts",
        voice_code=body.voice_code.strip(),
        language=(body.language or "").strip() or None,
        gender=(body.gender or "").strip() or None,
        sample_audio_url=(body.sample_audio_url or "").strip() or None,
        style_prompt=(body.style_prompt or "").strip() or None,
        meta_json=to_json_text(body.meta),
    )
    db.add(voice)
    await db.commit()
    await db.refresh(voice)
    return ApiResponse(data=_voice_payload(voice))


@router.put("/voices/{voice_id}", response_model=ApiResponse[dict])
async def update_global_voice(voice_id: str, body: VoiceUpdate, db: AsyncSession = Depends(get_db)):
    voice = (await db.execute(select(GlobalVoice).where(GlobalVoice.id == voice_id))).scalar_one_or_none()
    if voice is None:
        raise HTTPException(status_code=404, detail="语音不存在")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "meta":
            voice.meta_json = to_json_text(value)
        elif isinstance(value, str):
            setattr(voice, key, value.strip() or None)
        else:
            setattr(voice, key, value)
    if not voice.name:
        raise HTTPException(status_code=400, detail="语音名称不能为空")
    if not voice.voice_code:
        raise HTTPException(status_code=400, detail="voice_code 不能为空")
    await db.commit()
    await db.refresh(voice)
    return ApiResponse(data=_voice_payload(voice))


@router.delete("/voices/{voice_id}", response_model=ApiResponse[None])
async def delete_global_voice(voice_id: str, db: AsyncSession = Depends(get_db)):
    voice = (await db.execute(select(GlobalVoice).where(GlobalVoice.id == voice_id))).scalar_one_or_none()
    if voice is None:
        raise HTTPException(status_code=404, detail="语音不存在")
    await db.delete(voice)
    await db.commit()
    return ApiResponse(data=None)


@router.get("/characters", response_model=ApiResponse[list[dict]])
async def list_global_characters(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(GlobalCharacter).order_by(GlobalCharacter.created_at))).scalars().all()
    return ApiResponse(data=[_character_payload(item) for item in rows])


@router.post("/characters", response_model=ApiResponse[dict])
async def create_global_character(body: GlobalCharacterCreate, db: AsyncSession = Depends(get_db)):
    item = GlobalCharacter(
        name=body.name.strip(),
        alias=(body.alias or "").strip() or None,
        description=(body.description or "").strip() or None,
        prompt_template=(body.prompt_template or "").strip() or None,
        reference_image_url=(body.reference_image_url or "").strip() or None,
        default_voice_id=body.default_voice_id,
        tags_json=to_json_text(body.tags),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return ApiResponse(data=_character_payload(item))


@router.put("/characters/{character_id}", response_model=ApiResponse[dict])
async def update_global_character(character_id: str, body: GlobalCharacterUpdate, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(GlobalCharacter).where(GlobalCharacter.id == character_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="全局角色不存在")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "tags":
            item.tags_json = to_json_text(value or [])
        elif isinstance(value, str):
            setattr(item, key, value.strip() or None)
        else:
            setattr(item, key, value)
    if not item.name:
        raise HTTPException(status_code=400, detail="角色名称不能为空")
    await db.commit()
    await db.refresh(item)
    return ApiResponse(data=_character_payload(item))


@router.delete("/characters/{character_id}", response_model=ApiResponse[None])
async def delete_global_character(character_id: str, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(GlobalCharacter).where(GlobalCharacter.id == character_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="全局角色不存在")
    await db.delete(item)
    await db.commit()
    return ApiResponse(data=None)


@router.get("/locations", response_model=ApiResponse[list[dict]])
async def list_global_locations(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(GlobalLocation).order_by(GlobalLocation.created_at))).scalars().all()
    return ApiResponse(data=[_location_payload(item) for item in rows])


@router.post("/locations", response_model=ApiResponse[dict])
async def create_global_location(body: GlobalLocationCreate, db: AsyncSession = Depends(get_db)):
    item = GlobalLocation(
        name=body.name.strip(),
        description=(body.description or "").strip() or None,
        prompt_template=(body.prompt_template or "").strip() or None,
        reference_image_url=(body.reference_image_url or "").strip() or None,
        tags_json=to_json_text(body.tags),
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return ApiResponse(data=_location_payload(item))


@router.put("/locations/{location_id}", response_model=ApiResponse[dict])
async def update_global_location(location_id: str, body: GlobalLocationUpdate, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(GlobalLocation).where(GlobalLocation.id == location_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="全局地点不存在")
    updates = body.model_dump(exclude_unset=True)
    for key, value in updates.items():
        if key == "tags":
            item.tags_json = to_json_text(value or [])
        elif isinstance(value, str):
            setattr(item, key, value.strip() or None)
        else:
            setattr(item, key, value)
    if not item.name:
        raise HTTPException(status_code=400, detail="地点名称不能为空")
    await db.commit()
    await db.refresh(item)
    return ApiResponse(data=_location_payload(item))


@router.delete("/locations/{location_id}", response_model=ApiResponse[None])
async def delete_global_location(location_id: str, db: AsyncSession = Depends(get_db)):
    item = (await db.execute(select(GlobalLocation).where(GlobalLocation.id == location_id))).scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="全局地点不存在")
    await db.delete(item)
    await db.commit()
    return ApiResponse(data=None)
