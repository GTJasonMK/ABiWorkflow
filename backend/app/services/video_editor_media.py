from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from moviepy import CompositeVideoClip, TextClip, VideoFileClip, concatenate_videoclips

from app.config import resolve_runtime_path, settings
from app.models import Panel
from app.services.video_editor_types import TransitionType

logger = logging.getLogger(__name__)


class PanelAsset(TypedDict):
    panel_id: str
    panel_title: str
    clip_paths: list[str]
    duration: float
    dialogue: str | None
    transition_hint: str | None
    tts_audio_source: NotRequired[str | None]


def resolve_media_path(path_value: str | Path) -> Path:
    """解析媒体文件路径，统一按运行时根目录解析。"""
    raw = Path(path_value)
    if raw.is_absolute():
        return raw.resolve()

    return resolve_runtime_path(raw)


def resolve_panel_media_source(media_value: str | None) -> str | None:
    """解析分镜媒体来源，支持 /media 路径、本地路径与远程 URL。"""
    if not media_value:
        return None

    raw = media_value.strip()
    if not raw:
        return None

    if raw.startswith(("http://", "https://")):
        return raw

    if raw.startswith("/media/videos/"):
        relative = raw.removeprefix("/media/videos/").lstrip("/")
        candidate = resolve_runtime_path(settings.video_output_dir) / relative
        if candidate.exists():
            return str(candidate)
        return None

    if raw.startswith("/media/compositions/"):
        relative = raw.removeprefix("/media/compositions/").lstrip("/")
        candidate = resolve_runtime_path(settings.composition_output_dir) / relative
        if candidate.exists():
            return str(candidate)
        return None

    local = resolve_media_path(raw)
    if local.exists():
        return str(local)
    return None


def resolve_transition(panel_hint: str | None, default_transition: TransitionType) -> TransitionType:
    """解析分镜级转场提示，默认回落到全局配置。"""
    if default_transition == TransitionType.NONE:
        return TransitionType.NONE

    if not panel_hint:
        return default_transition

    normalized = panel_hint.strip().lower()
    if normalized in {"cut", "none"}:
        return TransitionType.NONE
    if normalized == "fade_black":
        return TransitionType.FADE_BLACK
    if normalized == "crossfade":
        return TransitionType.CROSSFADE

    logger.warning("未知的 transition_hint=%s，回落到全局配置 %s", panel_hint, default_transition.value)
    return default_transition


def load_video_clip(source: str) -> VideoFileClip:
    """加载并验证单个视频片段，确保可用于后续合成。"""
    clip = VideoFileClip(source)
    if clip.duration is None or clip.duration <= 0:
        clip.close()
        raise ValueError(f"视频文件无效（时长为空或为零）: {source}")
    if clip.size is None or clip.w <= 0 or clip.h <= 0:
        clip.close()
        raise ValueError(f"视频文件无效（尺寸异常）: {source}")
    return clip


def load_panel_clip(clip_paths: list[str]) -> VideoFileClip | CompositeVideoClip:
    """加载分镜内部的多个片段并拼接（不含转场）。"""
    clips = [load_video_clip(p) for p in clip_paths]

    if not clips:
        raise ValueError("没有可用的视频片段")

    if len(clips) == 1:
        return clips[0]

    return concatenate_videoclips(clips, method="compose")


def add_subtitles(
    video: VideoFileClip | CompositeVideoClip,
    subtitles: list[dict[str, Any]],
) -> VideoFileClip | CompositeVideoClip:
    """叠加字幕，无有效字幕时直接返回原视频（避免不必要的 CompositeVideoClip 嵌套）。"""
    subtitle_clips = []

    for sub in subtitles:
        text = sub.get("text", "")
        duration = max(0.1, float(sub.get("duration", 5.0)))
        start = max(0.0, float(sub.get("start", 0.0)))

        if text.strip():
            try:
                txt_clip = TextClip(
                    text=text,
                    font_size=28,
                    color="white",
                    stroke_color="black",
                    stroke_width=1,
                    size=(video.w - 80, None),
                    method="caption",
                    duration=duration,
                )
                txt_clip = txt_clip.with_start(start).with_position(("center", video.h - 80))
                subtitle_clips.append(txt_clip)
            except Exception as exc:  # noqa: BLE001
                logger.warning("字幕渲染失败: %s", exc)

    if subtitle_clips:
        return CompositeVideoClip([video] + subtitle_clips)
    return video


async def collect_panel_assets(
    panels: list[Panel],
) -> tuple[list[PanelAsset], list[str]]:
    """收集分镜可用素材，输出统一的分镜素材结构。"""
    panel_assets: list[PanelAsset] = []
    missing_panels: list[str] = []

    for panel in panels:
        video_source = resolve_panel_media_source(panel.lipsync_video_url or panel.video_url)
        if not video_source:
            missing_panels.append(panel.title)
            continue

        audio_source = resolve_panel_media_source(panel.tts_audio_url)
        panel_assets.append({
            "panel_id": panel.id,
            "panel_title": panel.title,
            "clip_paths": [video_source],
            "duration": max(0.1, float(panel.duration_seconds or 0.1)),
            "dialogue": (panel.tts_text or panel.script_text or "").strip() or None,
            "transition_hint": None,
            "tts_audio_source": audio_source,
        })

    return panel_assets, missing_panels


def build_subtitles_timeline(
    panel_assets: list[PanelAsset],
    transition_type: TransitionType,
    transition_duration: float,
) -> tuple[list[dict[str, Any]], float]:
    """按分镜时间轴构建字幕和总时长。"""
    subtitles: list[dict[str, Any]] = []
    current_start = 0.0

    for idx, asset in enumerate(panel_assets):
        if asset["dialogue"]:
            subtitles.append({
                "panel_id": asset["panel_id"],
                "text": asset["dialogue"],
                "duration": asset["duration"],
                "start": current_start,
            })

        current_start += asset["duration"]
        if idx < len(panel_assets) - 1 and transition_duration > 0:
            transition = resolve_transition(asset["transition_hint"], transition_type)
            if transition == TransitionType.FADE_BLACK:
                current_start += transition_duration

    return subtitles, max(0.1, current_start)


def trim_video_file(source_path: Path, output_path: Path, start_time: float, end_time: float) -> float:
    """裁剪视频并返回实际输出时长。"""
    clip = VideoFileClip(str(source_path))
    try:
        actual_end = min(end_time, clip.duration)
        trimmed = clip.subclipped(start_time, actual_end)
        has_audio = trimmed.audio is not None
        trimmed.write_videofile(
            str(output_path),
            fps=24,
            codec="libx264",
            audio=has_audio,
            audio_codec="aac" if has_audio else None,
            logger=None,
        )
        return trimmed.duration
    finally:
        clip.close()
