from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_REQUIRED_COLUMNS_BY_TABLE: dict[str, set[str]] = {
    "panels": {
        "video_provider_task_id",
        "tts_provider_task_id",
        "lipsync_provider_task_id",
        "video_status",
        "tts_status",
        "lipsync_status",
    },
    "episodes": {
        "video_provider_key",
        "tts_provider_key",
        "lipsync_provider_key",
        "provider_payload_defaults_json",
        "skipped_checks_json",
    },
    "projects": {
        "default_video_provider_key",
        "default_tts_provider_key",
        "default_lipsync_provider_key",
        "default_provider_payload_defaults_json",
    },
    "video_clips": {
        "panel_id",
    },
}

_LEGACY_SCENE_TABLES = {"scenes", "scene_characters"}


async def _sqlite_table_exists(conn: Any, table_name: str) -> bool:
    result = await conn.exec_driver_sql(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    )
    return result.first() is not None


async def validate_sqlite_schema(conn: Any) -> None:
    """启动期 SQLite 结构校验。

    约束：
    - 运行期不做自动迁移。
    - 检测到旧 Scene 兼容表或关键字段缺失时，直接阻止启动。
    """
    if conn.dialect.name != "sqlite":
        return

    existing_legacy_tables: list[str] = []
    for table_name in sorted(_LEGACY_SCENE_TABLES):
        if await _sqlite_table_exists(conn, table_name):
            existing_legacy_tables.append(table_name)
    if existing_legacy_tables:
        legacy_table_text = ", ".join(existing_legacy_tables)
        raise RuntimeError(
            "检测到旧版 Scene 兼容表："
            f"{legacy_table_text}。请删除 backend/abi_workflow.db 或切换到全新 DATABASE_URL。"
        )

    missing_by_table: dict[str, list[str]] = {}
    for table_name, required_columns in _REQUIRED_COLUMNS_BY_TABLE.items():
        try:
            result = await conn.exec_driver_sql(f"PRAGMA table_info({table_name})")
            columns = {row[1] for row in result}
        except Exception as exc:  # noqa: BLE001 - 启动期错误需要更明确
            raise RuntimeError(f"SQLite 表结构检查失败: {exc}") from exc

        missing = sorted(required_columns - columns)
        if missing:
            missing_by_table[table_name] = missing

    if not missing_by_table:
        return

    lines: list[str] = ["检测到旧版 SQLite 数据库结构不匹配（缺列）。"]
    for table_name, missing in sorted(missing_by_table.items()):
        missing_text = ", ".join(missing)
        logger.error("检测到旧版数据库 %s 缺少字段: %s", table_name, missing_text)
        lines.append(f"- {table_name} 缺少字段: {missing_text}")
    lines.append("请删除 backend/abi_workflow.db（或切换到全新 DATABASE_URL）后重新启动后端。")
    raise RuntimeError("\n".join(lines))
