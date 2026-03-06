from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.response_utils import isoformat_or_none
from app.database import get_db
from app.models import ProviderConfig
from app.schemas.common import ApiResponse
from app.services.json_codec import from_json_text, to_json_text
from app.services.provider_gateway import test_provider_connectivity

router = APIRouter(prefix="/system/providers", tags=["Provider 配置"])


class ProviderConfigUpsert(BaseModel):
    provider_type: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    submit_path: str = "/submit"
    status_path: str = "/status/{task_id}"
    result_path: str = "/result/{task_id}"
    auth_scheme: str = "bearer"
    api_key: str | None = None
    api_key_header: str = "Authorization"
    extra_headers: dict[str, Any] = Field(default_factory=dict)
    request_template: dict[str, Any] = Field(default_factory=dict)
    response_mapping: dict[str, Any] = Field(default_factory=dict)
    status_mapping: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=60.0, ge=1.0, le=3600.0)
    enabled: bool = True


def _provider_payload(item: ProviderConfig) -> dict[str, Any]:
    return {
        "id": item.id,
        "provider_key": item.provider_key,
        "provider_type": item.provider_type,
        "name": item.name,
        "base_url": item.base_url,
        "submit_path": item.submit_path,
        "status_path": item.status_path,
        "result_path": item.result_path,
        "auth_scheme": item.auth_scheme,
        "api_key_configured": bool(item.api_key),
        "api_key_preview": (
            item.api_key[:3] + "***" + item.api_key[-2:]
            if item.api_key and len(item.api_key) > 5
            else ("***" if item.api_key else None)
        ),
        "api_key_header": item.api_key_header,
        "extra_headers": from_json_text(item.extra_headers_json, {}),
        "request_template": from_json_text(item.request_template_json, {}),
        "response_mapping": from_json_text(item.response_mapping_json, {}),
        "status_mapping": from_json_text(item.status_mapping_json, {}),
        "timeout_seconds": float(item.timeout_seconds or 0.0),
        "enabled": item.enabled,
        "created_at": isoformat_or_none(item.created_at),
        "updated_at": isoformat_or_none(item.updated_at),
    }


@router.get("", response_model=ApiResponse[list[dict]])
async def list_provider_configs(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(ProviderConfig).order_by(ProviderConfig.provider_type, ProviderConfig.provider_key)
    )).scalars().all()
    return ApiResponse(data=[_provider_payload(item) for item in rows])


@router.put("/{provider_key}", response_model=ApiResponse[dict])
async def upsert_provider_config(provider_key: str, body: ProviderConfigUpsert, db: AsyncSession = Depends(get_db)):
    key = provider_key.strip()
    if not key:
        raise HTTPException(status_code=400, detail="provider_key 不能为空")

    entity = (await db.execute(
        select(ProviderConfig).where(ProviderConfig.provider_key == key)
    )).scalar_one_or_none()

    if entity is None:
        entity = ProviderConfig(
            provider_key=key,
            provider_type=body.provider_type.strip(),
            name=body.name.strip(),
            base_url=body.base_url.strip(),
            submit_path=body.submit_path.strip() or "/submit",
            status_path=body.status_path.strip() or "/status/{task_id}",
            result_path=body.result_path.strip() or "/result/{task_id}",
            auth_scheme=body.auth_scheme.strip() or "bearer",
            api_key=(body.api_key or "").strip() or None,
            api_key_header=body.api_key_header.strip() or "Authorization",
            extra_headers_json=to_json_text(body.extra_headers),
            request_template_json=to_json_text(body.request_template),
            response_mapping_json=to_json_text(body.response_mapping),
            status_mapping_json=to_json_text(body.status_mapping),
            timeout_seconds=body.timeout_seconds,
            enabled=body.enabled,
        )
        db.add(entity)
    else:
        entity.provider_type = body.provider_type.strip()
        entity.name = body.name.strip()
        entity.base_url = body.base_url.strip()
        entity.submit_path = body.submit_path.strip() or "/submit"
        entity.status_path = body.status_path.strip() or "/status/{task_id}"
        entity.result_path = body.result_path.strip() or "/result/{task_id}"
        entity.auth_scheme = body.auth_scheme.strip() or "bearer"
        if body.api_key is not None:
            entity.api_key = body.api_key.strip() or None
        entity.api_key_header = body.api_key_header.strip() or "Authorization"
        entity.extra_headers_json = to_json_text(body.extra_headers)
        entity.request_template_json = to_json_text(body.request_template)
        entity.response_mapping_json = to_json_text(body.response_mapping)
        entity.status_mapping_json = to_json_text(body.status_mapping)
        entity.timeout_seconds = body.timeout_seconds
        entity.enabled = body.enabled

    await db.commit()
    await db.refresh(entity)
    return ApiResponse(data=_provider_payload(entity))


@router.post("/{provider_key}/test", response_model=ApiResponse[dict])
async def test_provider(provider_key: str, db: AsyncSession = Depends(get_db)):
    try:
        result = await test_provider_connectivity(db, provider_key.strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"连通性测试失败: {exc}") from exc
    return ApiResponse(data=result)
