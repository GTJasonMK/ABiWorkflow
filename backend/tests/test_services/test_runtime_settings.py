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


def test_validate_runtime_business_rules_should_reject_invalid_llm_provider():
    with pytest.raises(runtime_settings.RuntimeSettingsValidationError, match="llm_provider 必须是"):
        runtime_settings.validate_runtime_business_rules({"llm_provider": "invalid-provider"})


def test_validate_runtime_business_rules_should_require_ggk_base_url_and_api_key():
    with pytest.raises(runtime_settings.RuntimeSettingsValidationError, match="llm_provider=ggk 时必须配置 GGK_BASE_URL"):
        runtime_settings.validate_runtime_business_rules({
            "llm_provider": "ggk",
            "ggk_base_url": "",
            "ggk_api_key": "",
        })


def test_validate_runtime_business_rules_should_reject_empty_video_provider():
    with pytest.raises(runtime_settings.RuntimeSettingsValidationError, match="video_provider 不能为空"):
        runtime_settings.validate_runtime_business_rules({"video_provider": "   "})


def test_validate_runtime_business_rules_should_accept_valid_ggk_provider_setup():
    runtime_settings.validate_runtime_business_rules({
        "llm_provider": "ggk",
        "video_provider": "ggk",
        "ggk_base_url": "http://127.0.0.1:8000/v1",
        "ggk_api_key": "sk-ggk-demo",
    })


def test_collect_ggk_updates_from_discovery_should_filter_blank_values():
    discovery = {
        "base_url": "http://127.0.0.1:8000/v1",
        "api_key": "sk-ggk-demo",
        "ggk_text_model": "grok-3",
        "ggk_video_model": "grok-imagine-1.0-video",
        "ggk_video_aspect_ratio": "",
        "ggk_video_resolution": "SD",
        "ggk_video_preset": "normal",
        "ggk_video_model_duration_profiles": "grok-imagine-1.0-video:5,6,8",
    }

    updates = runtime_settings.collect_ggk_updates_from_discovery(discovery)

    assert updates["ggk_base_url"] == "http://127.0.0.1:8000/v1"
    assert updates["ggk_api_key"] == "sk-ggk-demo"
    assert updates["ggk_text_model"] == "grok-3"
    assert updates["ggk_video_model"] == "grok-imagine-1.0-video"
    assert updates["ggk_video_resolution"] == "SD"
    assert updates["ggk_video_preset"] == "normal"
    assert updates["ggk_video_model_duration_profiles"] == "grok-imagine-1.0-video:5,6,8"
    assert "ggk_video_aspect_ratio" not in updates


def test_apply_runtime_updates_should_skip_empty_override_for_non_empty_default(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# keep comments\nLLM_PROVIDER=openai\nVIDEO_OUTPUT_DIR=./outputs/videos\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(runtime_settings, "_resolve_env_file_path", lambda: env_file)

    snapshot = {
        "llm_provider": settings.llm_provider,
        "video_output_dir": settings.video_output_dir,
    }
    try:
        runtime_settings.apply_runtime_updates({
            "llm_provider": "deepseek",
            "video_output_dir": "",
        })

        content = env_file.read_text(encoding="utf-8")
        assert "LLM_PROVIDER=deepseek" in content
        # video_output_dir 的空字符串更新应被跳过，避免覆盖默认输出目录。
        assert "VIDEO_OUTPUT_DIR=./outputs/videos" in content
        assert settings.llm_provider == "deepseek"
        assert settings.video_output_dir == snapshot["video_output_dir"]
    finally:
        for field_name, value in snapshot.items():
            setattr(settings, field_name, value)
