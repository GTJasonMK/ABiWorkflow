from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import httpx

DEFAULT_GGK_PORTS: tuple[int, ...] = (8000, 8001)


def normalize_ggk_base_url(raw_base_url: str) -> str:
    value = (raw_base_url or "").strip().rstrip("/")
    if not value:
        return value
    if value.endswith("/v1"):
        return value
    return f"{value}/v1"


def parse_dotenv_file(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    result: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def _candidate_ggk_paths(explicit_path: str | None = None) -> list[Path]:
    candidates: list[Path] = []
    if explicit_path and explicit_path.strip():
        candidates.append(Path(explicit_path.strip()))

    env_path = os.getenv("GGK_PROJECT_PATH", "").strip()
    if env_path:
        candidates.append(Path(env_path))

    repo_root = Path(__file__).resolve().parents[3]
    candidates.append((repo_root.parent / "GGK").resolve())
    candidates.append((repo_root.parent / "GGK - 副本").resolve())
    candidates.append(Path("E:/Code/GGK"))

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()) if candidate.exists() else str(candidate)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def find_ggk_project_path(explicit_path: str | None = None) -> Path | None:
    for candidate in _candidate_ggk_paths(explicit_path):
        if not candidate.exists() or not candidate.is_dir():
            continue
        if (candidate / "main.py").exists():
            return candidate
    return None


def _read_ggk_db_settings(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {}

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT value FROM kv_settings WHERE key = 'settings'").fetchone()
    if not row:
        return {}

    try:
        payload = json.loads(str(row["value"]))
    except json.JSONDecodeError:
        return {}

    if isinstance(payload, dict):
        return payload
    return {}


def _read_ggk_api_key(db_path: Path, *, prefer_internal_key: bool = False) -> tuple[str | None, str]:
    if not db_path.exists():
        return None, "missing"

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row

        if not prefer_internal_key:
            row = conn.execute(
                """
                SELECT key
                FROM api_keys
                WHERE is_active = 1 AND key IS NOT NULL AND key != ''
                ORDER BY COALESCE(updated_at, 0) DESC, COALESCE(created_at, 0) DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if row and str(row["key"]).strip():
                return str(row["key"]).strip(), "api_keys"

        settings_row = conn.execute("SELECT value FROM kv_settings WHERE key = 'settings'").fetchone()
        if settings_row:
            try:
                data = json.loads(str(settings_row["value"]))
            except json.JSONDecodeError:
                data = {}
            internal_key = str((data or {}).get("internal_api_key", "")).strip()
            if internal_key:
                return internal_key, "kv_settings.internal_api_key"

        if prefer_internal_key:
            row = conn.execute(
                """
                SELECT key
                FROM api_keys
                WHERE is_active = 1 AND key IS NOT NULL AND key != ''
                ORDER BY COALESCE(updated_at, 0) DESC, COALESCE(created_at, 0) DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
            if row and str(row["key"]).strip():
                return str(row["key"]).strip(), "api_keys"

    return None, "missing"


def _build_base_url_candidates(
    *,
    explicit_base_url: str | None,
    env_entries: dict[str, str],
) -> list[str]:
    candidates: list[str] = []

    if explicit_base_url and explicit_base_url.strip():
        candidates.append(normalize_ggk_base_url(explicit_base_url))

    env_base_url = env_entries.get("GGK_BASE_URL", "").strip()
    if env_base_url:
        candidates.append(normalize_ggk_base_url(env_base_url))

    env_host = env_entries.get("HOST", "").strip() or "127.0.0.1"
    env_port = env_entries.get("PORT", "").strip()
    if env_port.isdigit():
        candidates.append(normalize_ggk_base_url(f"http://{env_host}:{env_port}"))
        if env_host in {"0.0.0.0", "localhost"}:
            candidates.append(normalize_ggk_base_url(f"http://127.0.0.1:{env_port}"))

    for port in DEFAULT_GGK_PORTS:
        candidates.append(normalize_ggk_base_url(f"http://127.0.0.1:{port}"))
        candidates.append(normalize_ggk_base_url(f"http://localhost:{port}"))

    deduped: list[str] = []
    seen: set[str] = set()
    for item in candidates:
        value = item.strip()
        if not value or value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


async def _pick_reachable_base_url(candidates: list[str], api_key: str | None) -> tuple[str | None, bool]:
    if not candidates:
        return None, False

    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    async with httpx.AsyncClient(timeout=1.2) as client:
        for base_url in candidates:
            try:
                response = await client.get(f"{base_url}/models", headers=headers)
            except Exception:  # noqa: BLE001
                continue
            if response.status_code < 500:
                return base_url, True

    return candidates[0], False


async def discover_ggk_runtime_config(
    *,
    explicit_project_path: str | None = None,
    explicit_base_url: str | None = None,
    prefer_internal_key: bool = False,
) -> dict[str, Any]:
    project_path = find_ggk_project_path(explicit_project_path)
    if not project_path:
        return {
            "found": False,
            "reason": "未找到 GGK 项目目录",
            "candidates": [str(path) for path in _candidate_ggk_paths(explicit_project_path)],
        }

    env_path = project_path / ".env"
    db_path = project_path / "data" / "data.db"
    env_entries = parse_dotenv_file(env_path)
    db_settings = _read_ggk_db_settings(db_path)
    api_key, api_key_source = _read_ggk_api_key(db_path, prefer_internal_key=prefer_internal_key)

    candidates = _build_base_url_candidates(explicit_base_url=explicit_base_url, env_entries=env_entries)
    base_url, base_url_reachable = await _pick_reachable_base_url(candidates, api_key)

    return {
        "found": True,
        "project_path": str(project_path),
        "env_path": str(env_path),
        "db_path": str(db_path),
        "base_url": base_url,
        "base_url_reachable": base_url_reachable,
        "base_url_candidates": candidates,
        "api_key": api_key,
        "api_key_source": api_key_source,
        "ggk_text_model": env_entries.get("GGK_TEXT_MODEL", "").strip(),
        "ggk_video_model": env_entries.get("GGK_VIDEO_MODEL", "").strip(),
        "ggk_video_aspect_ratio": env_entries.get("GGK_VIDEO_ASPECT_RATIO", "").strip(),
        "ggk_video_resolution": env_entries.get("GGK_VIDEO_RESOLUTION", "").strip(),
        "ggk_video_preset": env_entries.get("GGK_VIDEO_PRESET", "").strip(),
        "ggk_video_model_duration_profiles": env_entries.get("GGK_VIDEO_MODEL_DURATION_PROFILES", "").strip(),
        "proxy_url": str(db_settings.get("proxy_url", "")).strip(),
        "cf_clearance_configured": bool(str(db_settings.get("cf_clearance", "")).strip()),
    }
