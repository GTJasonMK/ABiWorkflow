from __future__ import annotations

from pathlib import Path

from sqlalchemy import inspect, text

from app.config import resolve_runtime_path


def _drop_legacy_panel_voice_binding_column_for_sqlite(connection) -> None:
    """SQLite 下删除 legacy 列的兜底：重建 panels 表。"""
    from app.models.panel import Panel

    keep_columns = [col.name for col in Panel.__table__.columns]
    keep_columns_sql = ", ".join(keep_columns)

    connection.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        connection.execute(text(f"CREATE TABLE panels__tmp_data AS SELECT {keep_columns_sql} FROM panels"))
        connection.execute(text("DROP TABLE panels"))
        Panel.__table__.create(bind=connection, checkfirst=False)
        connection.execute(text(f"INSERT INTO panels ({keep_columns_sql}) SELECT {keep_columns_sql} FROM panels__tmp_data"))
        connection.execute(text("DROP TABLE panels__tmp_data"))
    finally:
        connection.execute(text("PRAGMA foreign_keys=ON"))


def cleanup_deprecated_single_track_schema(connection, *, force: bool = False) -> dict[str, bool]:
    """清理单轨化后的 legacy 表/列，返回本次是否执行了删表/删列。"""
    marker_file: Path = resolve_runtime_path("./outputs/.cleaned_single_track_schema")
    if marker_file.exists() and not force:
        return {"dropped_table": False, "dropped_column": False, "skipped_by_marker": True}

    inspector = inspect(connection)
    dropped_table = False
    dropped_column = False

    if inspector.has_table("panel_asset_links"):
        connection.execute(text("DROP TABLE IF EXISTS panel_asset_links"))
        dropped_table = True

    inspector = inspect(connection)
    if inspector.has_table("panels"):
        panel_columns = {column["name"] for column in inspector.get_columns("panels")}
        if "voice_binding_json" in panel_columns:
            if connection.dialect.name == "sqlite":
                try:
                    connection.execute(text("ALTER TABLE panels DROP COLUMN voice_binding_json"))
                except Exception:  # noqa: BLE001
                    _drop_legacy_panel_voice_binding_column_for_sqlite(connection)
            else:
                connection.execute(text("ALTER TABLE panels DROP COLUMN voice_binding_json"))
            dropped_column = True

    marker_file.parent.mkdir(parents=True, exist_ok=True)
    marker_file.write_text(
        f"dropped_table={dropped_table},dropped_column={dropped_column}",
        encoding="utf-8",
    )
    return {"dropped_table": dropped_table, "dropped_column": dropped_column, "skipped_by_marker": False}
