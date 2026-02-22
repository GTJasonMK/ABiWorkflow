from __future__ import annotations

from app.config import settings
from app.video_providers.base import VideoProvider

_registry: dict[str, type[VideoProvider]] = {}


def register_provider(name: str, provider_cls: type[VideoProvider]) -> None:
    """注册视频提供者"""
    _registry[name] = provider_cls


def get_provider(name: str | None = None) -> VideoProvider:
    """根据名称获取视频提供者实例"""
    provider_name = name or settings.video_provider

    if provider_name == "mock":
        from app.video_providers.mock_provider import MockVideoProvider
        return MockVideoProvider(output_dir=settings.video_output_dir)

    if provider_name == "http":
        from app.video_providers.http_provider import HttpVideoProvider
        return HttpVideoProvider(output_dir=settings.video_output_dir)

    if provider_name in _registry:
        return _registry[provider_name]()

    raise ValueError(f"未知的视频提供者: {provider_name}")
