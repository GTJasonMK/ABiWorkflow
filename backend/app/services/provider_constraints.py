from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ProviderConfig
from app.services.json_codec import from_json_text
from app.services.provider_gateway import get_provider_config_or_404


@dataclass(frozen=True, slots=True)
class VideoProviderDurationConstraints:
    """视频 Provider 的时长约束（用于分镜提示词生成与 UI 展示）。

    约定来源：ProviderConfig.request_template_json 内的 `_allowed_video_lengths`。
    设计目标：
    - 让“分镜提示词生成”严格受 provider 能力约束（例如 GGK 仅支持 6/10/15 秒）。
    - 避免依赖全局 settings.video_provider_max_duration_seconds 导致的错配。
    """

    provider_key: str
    allowed_seconds: list[int]

    @property
    def max_scene_seconds(self) -> int:
        return max(self.allowed_seconds) if self.allowed_seconds else 1

    def allowed_seconds_text(self) -> str:
        return ", ".join(str(value) for value in self.allowed_seconds)


def _parse_allowed_video_lengths(raw_template: Any) -> list[int]:
    if not isinstance(raw_template, dict):
        return []

    raw_allowed = raw_template.get("_allowed_video_lengths")
    if not isinstance(raw_allowed, list):
        return []

    items: set[int] = set()
    for raw in raw_allowed:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            items.add(value)

    return sorted(items)


async def resolve_video_duration_constraints(
    db: AsyncSession,
    *,
    provider_key: str,
) -> VideoProviderDurationConstraints:
    """解析指定 provider_key 的离散时长约束。

    严格模式：
    - provider_type 必须为 video
    - request_template_json 必须显式提供 `_allowed_video_lengths`
    """
    key = provider_key.strip()
    if not key:
        raise ValueError("video_provider_key 不能为空")

    config: ProviderConfig = await get_provider_config_or_404(db, key)
    if config.provider_type != "video":
        raise ValueError(f"provider_key={key} 不是视频 Provider（provider_type={config.provider_type}）")

    template = from_json_text(config.request_template_json, {})
    allowed = _parse_allowed_video_lengths(template)
    if not allowed:
        raise ValueError(
            f"provider_key={key} 未配置 _allowed_video_lengths，无法用于分镜提示词生成。"
            "请在 ProviderConfig.request_template_json 中显式配置，例如: "
            "{\"_allowed_video_lengths\":[6,10,15]}"
        )

    return VideoProviderDurationConstraints(provider_key=key, allowed_seconds=allowed)

