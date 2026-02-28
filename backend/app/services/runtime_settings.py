from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings, settings
from app.services.ggk_autoconfig import discover_ggk_runtime_config

_RUNTIME_UPDATE_FIELD_SET = set(Settings.model_fields.keys())
_ggk_auto_import_attempted = False


class RuntimeSettingsValidationError(ValueError):
    """运行时配置校验失败。"""


def _serialize_env_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _resolve_env_file_path() -> Path:
    return Path(__file__).resolve().parents[3] / ".env"


def _merge_env_updates(env_file: Path, updates: dict[str, object]) -> None:
    """增量写入 .env：保留注释与现有顺序，仅覆盖/追加目标键。"""
    if env_file.exists():
        lines = env_file.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    key_to_index: dict[str, int] = {}
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key:
            key_to_index[key] = index

    for env_key, value in updates.items():
        rendered = f"{env_key}={_serialize_env_value(value)}"
        if env_key in key_to_index:
            lines[key_to_index[env_key]] = rendered
        else:
            lines.append(rendered)

    env_file.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def validate_runtime_updates(raw_updates: dict[str, object]) -> dict[str, object]:
    """基于 Settings 单一配置真源校验并标准化更新项。"""
    unknown_fields = sorted(set(raw_updates) - _RUNTIME_UPDATE_FIELD_SET)
    if unknown_fields:
        raise RuntimeSettingsValidationError(f"存在不支持的配置项: {', '.join(unknown_fields)}")

    current_values = {name: getattr(settings, name) for name in Settings.model_fields}
    merged_values = {**current_values, **raw_updates}
    try:
        validated = Settings.model_validate(merged_values).model_dump()
    except ValidationError as exc:
        details: list[str] = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", []))
            msg = str(err.get("msg", "非法值"))
            details.append(f"{loc}: {msg}" if loc else msg)
        raise RuntimeSettingsValidationError(f"配置校验失败: {'; '.join(details)}") from exc

    return {key: validated[key] for key in raw_updates}


def _effective_value(updates: Mapping[str, object], field_name: str) -> object:
    if field_name in updates:
        return updates[field_name]
    return getattr(settings, field_name)


def validate_runtime_business_rules(updates: Mapping[str, object]) -> None:
    """校验运行时配置的业务规则（跨字段约束）。"""
    if "llm_provider" in updates and updates["llm_provider"] not in {"openai", "anthropic", "deepseek", "ggk"}:
        raise RuntimeSettingsValidationError("llm_provider 必须是 openai / anthropic / deepseek / ggk")

    if "video_provider" in updates and not str(updates["video_provider"]).strip():
        raise RuntimeSettingsValidationError("video_provider 不能为空")

    if _effective_value(updates, "llm_provider") == "ggk":
        if not str(_effective_value(updates, "ggk_base_url") or "").strip():
            raise RuntimeSettingsValidationError("llm_provider=ggk 时必须配置 GGK_BASE_URL")
        if not str(_effective_value(updates, "ggk_api_key") or "").strip():
            raise RuntimeSettingsValidationError("llm_provider=ggk 时必须配置 GGK_API_KEY")

    if _effective_value(updates, "video_provider") == "ggk":
        if not str(_effective_value(updates, "ggk_base_url") or "").strip():
            raise RuntimeSettingsValidationError("video_provider=ggk 时必须配置 GGK_BASE_URL")
        if not str(_effective_value(updates, "ggk_api_key") or "").strip():
            raise RuntimeSettingsValidationError("video_provider=ggk 时必须配置 GGK_API_KEY")

    if "ggk_video_model_duration_profiles" in updates:
        try:
            from app.video_providers.ggk_provider import parse_model_duration_profiles

            parse_model_duration_profiles(str(updates["ggk_video_model_duration_profiles"] or ""))
        except ValueError as exc:
            raise RuntimeSettingsValidationError(f"ggk_video_model_duration_profiles 配置非法: {exc}") from exc


def apply_runtime_updates(updates: dict[str, object]) -> None:
    """同步更新 settings 单例并持久化到 .env。"""
    env_updates: dict[str, object] = {}
    for field_name, value in updates.items():
        # 空字符串不覆盖有非空默认值的字段，避免把系统默认目录等配置写坏。
        if isinstance(value, str) and not value.strip():
            field_info = Settings.model_fields.get(field_name)
            if field_info is not None:
                default = field_info.default
                if isinstance(default, str) and default.strip():
                    continue

        env_key = field_name.upper()
        env_updates[env_key] = value
        setattr(settings, field_name, value)

    _merge_env_updates(_resolve_env_file_path(), env_updates)


def collect_ggk_updates_from_discovery(discovery: Mapping[str, object]) -> dict[str, object]:
    """从 GGK 探测结果中提取可写入的配置项。"""
    updates: dict[str, object] = {}

    base_url = str(discovery.get("base_url") or "").strip()
    if base_url:
        updates["ggk_base_url"] = base_url

    api_key = str(discovery.get("api_key") or "").strip()
    if api_key:
        updates["ggk_api_key"] = api_key

    optional_field_map = {
        "ggk_text_model": "ggk_text_model",
        "ggk_video_model": "ggk_video_model",
        "ggk_video_aspect_ratio": "ggk_video_aspect_ratio",
        "ggk_video_resolution": "ggk_video_resolution",
        "ggk_video_preset": "ggk_video_preset",
        "ggk_video_model_duration_profiles": "ggk_video_model_duration_profiles",
    }
    for field_name, source_key in optional_field_map.items():
        value = str(discovery.get(source_key) or "").strip()
        if value:
            updates[field_name] = value

    return updates


async def auto_import_ggk_if_needed() -> None:
    """当 GGK 关键配置缺失时，尝试从同级 GGK 项目自动导入。"""
    global _ggk_auto_import_attempted
    if _ggk_auto_import_attempted:
        return
    _ggk_auto_import_attempted = True

    if os.getenv("ABI_DISABLE_GGK_AUTO_IMPORT", "").strip().lower() in {"1", "true", "yes"}:
        return

    has_ggk_base = bool(str(settings.ggk_base_url).strip())
    has_ggk_key = bool(str(settings.ggk_api_key).strip())
    if has_ggk_base and has_ggk_key:
        return

    try:
        discovery = await discover_ggk_runtime_config()
    except Exception:  # noqa: BLE001
        return

    updates = collect_ggk_updates_from_discovery(discovery)
    if not discovery.get("found"):
        return
    if not str(updates.get("ggk_base_url") or "").strip():
        return
    if not str(updates.get("ggk_api_key") or "").strip():
        return

    if has_ggk_base:
        updates.pop("ggk_base_url", None)
    if has_ggk_key:
        updates.pop("ggk_api_key", None)

    if settings.llm_provider == "openai" and not str(settings.openai_api_key).strip():
        updates["llm_provider"] = "ggk"
    if settings.video_provider == "mock":
        updates["video_provider"] = "ggk"

    if not updates:
        return

    try:
        apply_runtime_updates(validate_runtime_updates(updates))
    except RuntimeSettingsValidationError:
        # 启动自动导入不应阻断主流程，校验失败时静默跳过。
        return
