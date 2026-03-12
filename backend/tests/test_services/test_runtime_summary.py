from __future__ import annotations

from app.config import settings
from app.services.runtime_summary import build_runtime_summary


def test_build_runtime_summary_should_return_structured_sections():
    summary = build_runtime_summary(celery_worker_online=False)

    assert set(summary.keys()) == {"app", "llm", "queue", "video", "models"}
    assert "name" in summary["app"]
    assert "model" in summary["llm"]
    assert "celery_worker_online" in summary["queue"]
    assert "queue_mode" in summary["queue"]
    assert "http_provider" in summary["video"]
    assert "ggk_provider" in summary["video"]
    assert "project_asset_publish_global_default" in summary["video"]
    assert isinstance(summary["video"]["project_asset_publish_global_default"], bool)


def test_build_runtime_summary_should_mask_database_credentials():
    snapshot_database_url = settings.database_url
    try:
        settings.database_url = "postgresql://user:pass@localhost:5432/demo"
        summary = build_runtime_summary(celery_worker_online=True)
        assert summary["app"]["database_url"] == "postgresql://***:***@localhost:5432/demo"
    finally:
        settings.database_url = snapshot_database_url
