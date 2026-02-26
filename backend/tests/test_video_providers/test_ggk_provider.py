from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.config import settings
from app.video_providers.base import VideoGenerateRequest
from app.video_providers.ggk_provider import GgkVideoProvider


def _patch_ggk_settings(monkeypatch: pytest.MonkeyPatch, *, duration_profiles: str = "") -> None:
    monkeypatch.setattr(settings, "ggk_base_url", "http://ggk.local/v1")
    monkeypatch.setattr(settings, "ggk_api_key", "sk-ggk-test")
    monkeypatch.setattr(settings, "ggk_video_model", "grok-imagine-1.0-video")
    monkeypatch.setattr(settings, "ggk_video_aspect_ratio", "16:9")
    monkeypatch.setattr(settings, "ggk_video_resolution", "SD")
    monkeypatch.setattr(settings, "ggk_video_preset", "normal")
    monkeypatch.setattr(settings, "ggk_request_timeout_seconds", 30)
    monkeypatch.setattr(settings, "ggk_video_model_duration_profiles", duration_profiles)
    # max_duration_seconds 属性会取 min(profile_max, 全局上限)，需确保全局上限不截断 profile 配置
    monkeypatch.setattr(settings, "video_provider_max_duration_seconds", 600.0)


@pytest.mark.asyncio
async def test_ggk_provider_should_generate_and_download_video(tmp_path, monkeypatch):
    _patch_ggk_settings(
        monkeypatch,
        duration_profiles=json.dumps({
            "grok-imagine-1.0-video": {
                "min_seconds": 5,
                "max_seconds": 15,
                "allowed_seconds": [5, 6, 8, 10, 15],
                "prompt_hint_template": "请将时长控制在约 {seconds} 秒，节奏完整。",
            }
        }),
    )
    captured_request_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            captured_request_payload.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                status_code=200,
                json={
                    "id": "chatcmpl-ggk-001",
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '<video id="video" controls="" preload="none">'
                                    '<source id="mp4" src="/v1/files/video/demo.mp4" type="video/mp4">'
                                    "</video>"
                                ),
                            }
                        }
                    ],
                },
            )
        if request.url.path == "/v1/files/video/demo.mp4":
            return httpx.Response(
                status_code=200,
                content=b"fake-mp4-bytes",
                headers={"content-type": "video/mp4"},
            )
        return httpx.Response(status_code=404)

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.video_providers.ggk_provider.httpx.AsyncClient", _Client)

    provider = GgkVideoProvider(output_dir=str(tmp_path))
    task_id = await provider.generate(VideoGenerateRequest(prompt="一只猫在花园里奔跑", duration_seconds=7))
    assert task_id == "chatcmpl-ggk-001"
    assert captured_request_payload["video_config"]["video_length"] == 6
    assert "时长控制在约 6 秒" in captured_request_payload["messages"][0]["content"]

    status = await provider.poll_status(task_id)
    assert status.status == "completed"
    assert status.result_url == "http://ggk.local/v1/files/video/demo.mp4"

    out_file = await provider.download(task_id, Path(tmp_path) / "result.mp4")
    assert out_file.exists()
    assert out_file.read_bytes() == b"fake-mp4-bytes"


@pytest.mark.asyncio
async def test_ggk_provider_should_fail_when_video_url_missing(tmp_path, monkeypatch):
    _patch_ggk_settings(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(
                status_code=200,
                json={"id": "chatcmpl-ggk-002", "choices": [{"message": {"content": "仅返回文本，没有视频标签"}}]},
            )
        return httpx.Response(status_code=404)

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.video_providers.ggk_provider.httpx.AsyncClient", _Client)

    provider = GgkVideoProvider(output_dir=str(tmp_path))
    with pytest.raises(ValueError, match="未找到视频地址"):
        await provider.generate(VideoGenerateRequest(prompt="测试视频", duration_seconds=5))


@pytest.mark.asyncio
async def test_ggk_provider_should_apply_custom_duration_profile(tmp_path, monkeypatch):
    _patch_ggk_settings(
        monkeypatch,
        duration_profiles=json.dumps({
            "grok-imagine-1.0-video": {
                "min_seconds": 4,
                "max_seconds": 9,
                "prompt_hint_template": "目标时长 {seconds}s，请保证镜头起承转合。",
            }
        }),
    )
    captured_request_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/chat/completions":
            captured_request_payload.update(json.loads(request.content.decode("utf-8")))
            return httpx.Response(
                status_code=200,
                json={
                    "id": "chatcmpl-ggk-003",
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '<video id="video" controls="" preload="none">'
                                    '<source id="mp4" src="/v1/files/video/custom.mp4" type="video/mp4">'
                                    "</video>"
                                ),
                            }
                        }
                    ],
                },
            )
        return httpx.Response(status_code=404)

    transport = httpx.MockTransport(handler)

    class _Client(httpx.AsyncClient):
        def __init__(self, *args, **kwargs):
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    monkeypatch.setattr("app.video_providers.ggk_provider.httpx.AsyncClient", _Client)

    provider = GgkVideoProvider(output_dir=str(tmp_path))
    await provider.generate(VideoGenerateRequest(prompt="城市夜景延时镜头", duration_seconds=20))

    assert provider.max_duration_seconds == 9
    assert captured_request_payload["video_config"]["video_length"] == 9
    assert "目标时长 9s" in captured_request_payload["messages"][0]["content"]
