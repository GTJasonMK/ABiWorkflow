from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.video_providers.http_provider import HttpVideoProvider


def _patch_http_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "video_http_base_url", "http://provider.local")
    monkeypatch.setattr(settings, "video_http_api_key", "")
    monkeypatch.setattr(settings, "video_http_generate_path", "/v1/video/generations")
    monkeypatch.setattr(settings, "video_http_status_path", "/v1/video/generations/{task_id}")
    monkeypatch.setattr(settings, "video_http_task_id_path", "task_id")
    monkeypatch.setattr(settings, "video_http_status_value_path", "status")
    monkeypatch.setattr(settings, "video_http_progress_path", "progress")
    monkeypatch.setattr(settings, "video_http_result_url_path", "result_url")
    monkeypatch.setattr(settings, "video_http_error_path", "error_message")
    monkeypatch.setattr(settings, "video_http_request_timeout_seconds", 30)


@pytest.mark.asyncio
async def test_http_provider_should_normalize_status_and_progress(tmp_path, monkeypatch):
    _patch_http_settings(monkeypatch)
    calls = {"status": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/video/generations/task-1":
            calls["status"] += 1
            if calls["status"] == 1:
                return httpx.Response(
                    status_code=200,
                    json={"status": "In_Progress", "progress": 0.42},
                )
            return httpx.Response(
                status_code=200,
                json={
                    "status": "Succeeded",
                    "progress": 1.0,
                    "result_url": "http://provider.local/files/result.mp4",
                },
            )

        if request.url.path == "/files/result.mp4":
            return httpx.Response(
                status_code=200,
                content=b"video-bytes",
                headers={"content-type": "video/mp4"},
            )

        return httpx.Response(status_code=404)

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.video_providers.http_provider.httpx.AsyncClient", _Client)

    provider = HttpVideoProvider(output_dir=str(tmp_path))
    first_status = await provider.poll_status("task-1")
    assert first_status.status == "processing"
    assert first_status.progress_percent == 42.0

    second_status = await provider.poll_status("task-1")
    assert second_status.status == "completed"
    assert second_status.progress_percent == 100.0

    out_file = await provider.download("task-1", Path(tmp_path) / "result.mp4")
    assert out_file.exists()
    assert out_file.read_bytes() == b"video-bytes"


@pytest.mark.asyncio
async def test_http_provider_should_map_error_states_to_failed(tmp_path, monkeypatch):
    _patch_http_settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/video/generations/task-2":
            return httpx.Response(
                status_code=200,
                json={"status": "ERROR", "error_message": "upstream timeout"},
            )
        return httpx.Response(status_code=404)

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.video_providers.http_provider.httpx.AsyncClient", _Client)

    provider = HttpVideoProvider(output_dir=str(tmp_path))
    status = await provider.poll_status("task-2")
    assert status.status == "failed"
    assert status.error_message == "upstream timeout"


@pytest.mark.asyncio
async def test_http_provider_should_not_forward_api_key_to_third_party_result_url(tmp_path, monkeypatch):
    _patch_http_settings(monkeypatch)
    monkeypatch.setattr(settings, "video_http_api_key", "sk-http-secret")
    download_authorization: str | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal download_authorization
        if request.url.path == "/v1/video/generations/task-3":
            return httpx.Response(
                status_code=200,
                json={
                    "status": "completed",
                    "progress": 100,
                    "result_url": "http://cdn.third-party.local/files/result.mp4",
                },
            )
        if request.url.host == "cdn.third-party.local" and request.url.path == "/files/result.mp4":
            download_authorization = request.headers.get("Authorization")
            return httpx.Response(status_code=200, content=b"from-cdn")
        return httpx.Response(status_code=404)

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.video_providers.http_provider.httpx.AsyncClient", _Client)

    provider = HttpVideoProvider(output_dir=str(tmp_path))
    out_file = await provider.download("task-3", Path(tmp_path) / "cdn-result.mp4")

    assert out_file.exists()
    assert out_file.read_bytes() == b"from-cdn"
    assert download_authorization is None
