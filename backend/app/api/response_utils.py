from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.json_codec import from_json_text


def isoformat_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def isoformat_or_empty(value: datetime | None) -> str:
    return value.isoformat() if value else ""


def json_dict_or_none(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    value = from_json_text(raw, None)
    return value if isinstance(value, dict) else None


def json_dict_or_empty(raw: str | None) -> dict[str, Any]:
    return json_dict_or_none(raw) or {}
