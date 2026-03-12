from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path

from pydantic import ValidationError

from app.config import Settings, settings

_RUNTIME_UPDATE_FIELD_SET = set(Settings.model_fields.keys())


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


def _validate_json_object_field(value: object, *, field_name: str) -> None:
    if value is None:
        return
    raw = str(value).strip()
    if not raw:
        return
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeSettingsValidationError(f"{field_name} 必须是合法 JSON 对象") from exc
    if not isinstance(parsed, dict):
        raise RuntimeSettingsValidationError(f"{field_name} 必须是 JSON 对象")


def validate_runtime_business_rules(updates: Mapping[str, object]) -> None:
    """校验运行时配置的业务规则（跨字段约束）。"""
    if "video_provider" in updates and not str(updates["video_provider"]).strip():
        raise RuntimeSettingsValidationError("video_provider 不能为空")

    # LLM：严格校验 base_url，不做自动补全/兼容修复。
    provider = str(_effective_value(updates, "llm_provider") or "openai").strip().lower()
    base_url = str(_effective_value(updates, "llm_base_url") or "").strip()
    if base_url:
        if not (base_url.startswith("http://") or base_url.startswith("https://")):
            raise RuntimeSettingsValidationError("llm_base_url 必须以 http:// 或 https:// 开头")
        if base_url.endswith("/"):
            raise RuntimeSettingsValidationError("llm_base_url 不能以 / 结尾")
        if provider == "openai" and not base_url.endswith("/v1"):
            raise RuntimeSettingsValidationError("llm_provider=openai 时 llm_base_url 必须以 /v1 结尾")
        if provider == "anthropic" and (base_url.endswith("/v1") or "/v1/" in base_url):
            raise RuntimeSettingsValidationError("llm_provider=anthropic 时 llm_base_url 不应包含 /v1")

    if _effective_value(updates, "video_provider") == "ggk":
        ggk_base_url = str(_effective_value(updates, "ggk_base_url") or "").strip()
        if not ggk_base_url:
            raise RuntimeSettingsValidationError("video_provider=ggk 时必须配置 GGK_BASE_URL")
        if not (ggk_base_url.startswith("http://") or ggk_base_url.startswith("https://")):
            raise RuntimeSettingsValidationError("GGK_BASE_URL 必须以 http:// 或 https:// 开头")
        if ggk_base_url.endswith("/"):
            raise RuntimeSettingsValidationError("GGK_BASE_URL 不能以 / 结尾，请填写 .../v1")
        if not ggk_base_url.endswith("/v1"):
            raise RuntimeSettingsValidationError("GGK_BASE_URL 必须以 /v1 结尾，例如 https://glk.jia4u.de/v1")
        if not str(_effective_value(updates, "ggk_api_key") or "").strip():
            raise RuntimeSettingsValidationError("video_provider=ggk 时必须配置 GGK_API_KEY")

    if "ggk_video_model_duration_profiles" in updates:
        try:
            from app.video_providers.ggk_provider import parse_model_duration_profiles

            parse_model_duration_profiles(str(updates["ggk_video_model_duration_profiles"] or ""))
        except ValueError as exc:
            raise RuntimeSettingsValidationError(f"ggk_video_model_duration_profiles 配置非法: {exc}") from exc

    if "portrait_api_base_url" in updates:
        portrait_base_url = str(updates["portrait_api_base_url"] or "").strip()
        if portrait_base_url:
            if not (portrait_base_url.startswith("http://") or portrait_base_url.startswith("https://")):
                raise RuntimeSettingsValidationError("PORTRAIT_API_BASE_URL 必须以 http:// 或 https:// 开头")
            if portrait_base_url.endswith("/"):
                raise RuntimeSettingsValidationError("PORTRAIT_API_BASE_URL 不能以 / 结尾，请填写 .../v1")
            if not portrait_base_url.endswith("/v1"):
                raise RuntimeSettingsValidationError("PORTRAIT_API_BASE_URL 必须以 /v1 结尾，例如 https://glk.jia4u.de/v1")

    if "default_model_bindings" in updates:
        _validate_json_object_field(updates["default_model_bindings"], field_name="default_model_bindings")
    if "model_capability_profiles" in updates:
        _validate_json_object_field(updates["model_capability_profiles"], field_name="model_capability_profiles")


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

    # 连接串更新后立即刷新队列与进度推送能力，避免重启前后行为不一致。
    from app.services.progress import reset_redis_client
    from app.services.queue_runtime import ensure_queue_backend_ready

    reset_redis_client()
    ensure_queue_backend_ready(force_refresh=True)
