from __future__ import annotations

import pytest

from app.config import settings
from app.services import runtime_settings


def test_validate_runtime_updates_should_reject_unknown_field():
    with pytest.raises(runtime_settings.RuntimeSettingsValidationError, match="不支持的配置项"):
        runtime_settings.validate_runtime_updates({"not_exists_field": "value"})


def test_validate_runtime_updates_should_reject_invalid_type():
    with pytest.raises(runtime_settings.RuntimeSettingsValidationError, match="配置校验失败"):
        runtime_settings.validate_runtime_updates({"video_poll_interval_seconds": "not-a-float"})


def test_validate_runtime_business_rules_should_require_ggk_video_provider_credentials():
    """video_provider=ggk 时必须配置 GGK_BASE_URL 和 GGK_API_KEY。"""
    with pytest.raises(runtime_settings.RuntimeSettingsValidationError, match="video_provider=ggk 时必须配置 GGK_BASE_URL"):
        runtime_settings.validate_runtime_business_rules({
            "video_provider": "ggk",
            "ggk_base_url": "",
            "ggk_api_key": "",
        })


def test_validate_runtime_business_rules_should_reject_empty_video_provider():
    with pytest.raises(runtime_settings.RuntimeSettingsValidationError, match="video_provider 不能为空"):
        runtime_settings.validate_runtime_business_rules({"video_provider": "   "})


def test_validate_runtime_business_rules_should_accept_valid_ggk_video_provider_setup():
    """video_provider=ggk + 有效的 ggk 凭证应通过校验。"""
    runtime_settings.validate_runtime_business_rules({
        "video_provider": "ggk",
        "ggk_base_url": "http://127.0.0.1:8000/v1",
        "ggk_api_key": "sk-ggk-demo",
    })


def test_validate_runtime_business_rules_should_reject_invalid_model_bindings_json():
    with pytest.raises(runtime_settings.RuntimeSettingsValidationError, match="default_model_bindings 必须是合法 JSON 对象"):
        runtime_settings.validate_runtime_business_rules({"default_model_bindings": "{not-json}"})


def test_validate_runtime_business_rules_should_reject_invalid_capability_profiles_type():
    with pytest.raises(runtime_settings.RuntimeSettingsValidationError, match="model_capability_profiles 必须是 JSON 对象"):
        runtime_settings.validate_runtime_business_rules({"model_capability_profiles": "[]"})


def test_apply_runtime_updates_should_skip_empty_override_for_non_empty_default(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# keep comments\nLLM_MODEL=gpt-4o\nVIDEO_OUTPUT_DIR=./outputs/videos\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_settings, "_resolve_env_file_path", lambda: env_file)

    snapshot = {
        "llm_model": settings.llm_model,
        "video_output_dir": settings.video_output_dir,
    }
    try:
        runtime_settings.apply_runtime_updates({
            "llm_model": "claude-sonnet-4-20250514",
            "video_output_dir": "",
        })

        content = env_file.read_text(encoding="utf-8")
        assert "LLM_MODEL=claude-sonnet-4-20250514" in content
        # video_output_dir 的空字符串更新应被跳过，避免覆盖默认输出目录。
        assert "VIDEO_OUTPUT_DIR=./outputs/videos" in content
        assert settings.llm_model == "claude-sonnet-4-20250514"
        assert settings.video_output_dir == snapshot["video_output_dir"]
    finally:
        for field_name, value in snapshot.items():
            setattr(settings, field_name, value)
