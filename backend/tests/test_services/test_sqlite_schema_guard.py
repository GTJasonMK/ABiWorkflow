from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from app.services.sqlite_schema_guard import validate_sqlite_schema


@pytest.mark.asyncio
async def test_validate_sqlite_schema_should_reject_legacy_scene_tables(tmp_path):
    database_path = tmp_path / "legacy-scene.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE TABLE scenes (id VARCHAR(36) PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE scene_characters (id VARCHAR(36) PRIMARY KEY)")

            with pytest.raises(RuntimeError, match="旧版 Scene 兼容表"):
                await validate_sqlite_schema(conn)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_validate_sqlite_schema_should_reject_missing_required_columns(tmp_path):
    database_path = tmp_path / "legacy-columns.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    try:
        async with engine.begin() as conn:
            await conn.exec_driver_sql("CREATE TABLE panels (id VARCHAR(36) PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE episodes (id VARCHAR(36) PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)")
            await conn.exec_driver_sql("CREATE TABLE video_clips (id VARCHAR(36) PRIMARY KEY)")

            with pytest.raises(RuntimeError, match="缺列"):
                await validate_sqlite_schema(conn)
    finally:
        await engine.dispose()
