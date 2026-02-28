from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, TypedDict

from moviepy import CompositeVideoClip, TextClip, VideoFileClip, concatenate_videoclips
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clip_status import CLIP_STATUS_COMPLETED
from app.config import resolve_runtime_path
from app.models import Scene, VideoClip
from app.services.video_editor_types import TransitionType

logger = logging.getLogger(__name__)


class SceneAsset(TypedDict):
    scene_id: str
    scene_title: str
    clip_paths: list[Path]
    duration: float
    dialogue: str | None
    transition_hint: str | None


def resolve_media_path(path_value: str | Path) -> Path:
    """解析媒体文件路径，优先运行时稳定路径，兼容历史 cwd 相对路径。"""
    raw = Path(path_value)
    if raw.is_absolute():
        return raw.resolve()

    runtime_based = resolve_runtime_path(raw)
    cwd_based = (Path.cwd() / raw).resolve()
    if runtime_based.exists():
        return runtime_based
    if cwd_based.exists():
        return cwd_based
    return runtime_based


def resolve_transition(scene_hint: str | None, default_transition: TransitionType) -> TransitionType:
    """解析场景级转场提示，默认回落到全局配置。"""
    if default_transition == TransitionType.NONE:
        return TransitionType.NONE

    if not scene_hint:
        return default_transition

    normalized = scene_hint.strip().lower()
    if normalized in {"cut", "none"}:
        return TransitionType.NONE
    if normalized == "fade_black":
        return TransitionType.FADE_BLACK
    if normalized == "crossfade":
        return TransitionType.CROSSFADE

    logger.warning("未知的 transition_hint=%s，回落到全局配置 %s", scene_hint, default_transition.value)
    return default_transition


def load_video_clip(path: Path) -> VideoFileClip:
    """加载并验证单个视频片段，确保可用于后续合成。"""
    clip = VideoFileClip(str(path))
    if clip.duration is None or clip.duration <= 0:
        clip.close()
        raise ValueError(f"视频文件无效（时长为空或为零）: {path}")
    if clip.size is None or clip.w <= 0 or clip.h <= 0:
        clip.close()
        raise ValueError(f"视频文件无效（尺寸异常）: {path}")
    return clip


def load_scene_clip(clip_paths: list[Path]) -> VideoFileClip | CompositeVideoClip:
    """加载场景内部的多个片段并拼接（不含转场）。"""
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


async def collect_scene_assets(
    scenes: list[Scene],
    db: AsyncSession,
) -> tuple[list[SceneAsset], list[str]]:
    """收集场景可用片段，返回场景素材列表与缺失场景标题。"""
    scene_assets: list[SceneAsset] = []
    missing_scenes: list[str] = []

    for scene in scenes:
        clips = (await db.execute(
            select(VideoClip)
            .where(
                VideoClip.scene_id == scene.id,
                VideoClip.status == CLIP_STATUS_COMPLETED,
                VideoClip.is_selected == True,  # noqa: E712
            )
            .order_by(VideoClip.clip_order)
        )).scalars().all()

        scene_clip_paths: list[Path] = []
        scene_duration = 0.0
        for clip in clips:
            if clip.file_path:
                clip_path = resolve_media_path(clip.file_path)
                if clip_path.exists():
                    scene_clip_paths.append(clip_path)
                    scene_duration += float(clip.duration_seconds or 0.0)

        if not scene_clip_paths:
            missing_scenes.append(scene.title)
            continue

        scene_assets.append({
            "scene_id": scene.id,
            "scene_title": scene.title,
            "clip_paths": scene_clip_paths,
            "duration": max(scene_duration, 0.1),
            "dialogue": scene.dialogue,
            "transition_hint": scene.transition_hint,
        })

    return scene_assets, missing_scenes


def build_subtitles_timeline(
    scene_assets: list[SceneAsset],
    transition_type: TransitionType,
    transition_duration: float,
) -> tuple[list[dict[str, Any]], float]:
    """按场景时间轴构建字幕和总时长。"""
    subtitles: list[dict[str, Any]] = []
    current_start = 0.0

    for idx, asset in enumerate(scene_assets):
        if asset["dialogue"]:
            subtitles.append({
                "scene_id": asset["scene_id"],
                "text": asset["dialogue"],
                "duration": asset["duration"],
                "start": current_start,
            })

        current_start += asset["duration"]
        if idx < len(scene_assets) - 1 and transition_duration > 0:
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
