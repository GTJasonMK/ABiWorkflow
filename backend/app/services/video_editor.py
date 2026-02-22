from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    TextClip,
    VideoFileClip,
    concatenate_videoclips,
)
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import CompositionTask, Scene, VideoClip
from app.services.progress import publish_progress
from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)


class TransitionType(str, Enum):
    NONE = "none"
    CROSSFADE = "crossfade"
    FADE_BLACK = "fade_black"


class CompositionOptions(BaseModel):
    """合成选项"""

    transition_type: TransitionType = TransitionType.CROSSFADE
    transition_duration: float = 0.5
    include_subtitles: bool = True
    include_tts: bool = True


class VideoEditorService:
    """视频剪辑合成服务"""

    def __init__(self):
        self._tts = TTSService()

    @staticmethod
    def _resolve_transition(scene_hint: str | None, default_transition: TransitionType) -> TransitionType:
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

    def _load_and_transition(
        self,
        clip_paths: list[Path],
        transition: TransitionType,
        transition_duration: float,
    ) -> VideoFileClip | CompositeVideoClip:
        """加载视频片段并应用转场效果"""
        clips = []
        for p in clip_paths:
            clip = VideoFileClip(str(p))
            clips.append(clip)

        if not clips:
            raise ValueError("没有可用的视频片段")

        if len(clips) == 1:
            return clips[0]

        transition_duration = max(0.0, transition_duration)

        if transition == TransitionType.CROSSFADE:
            padding = -transition_duration if transition_duration > 0 else 0
            return concatenate_videoclips(clips, method="compose", padding=padding)
        elif transition == TransitionType.FADE_BLACK:
            if transition_duration <= 0:
                return concatenate_videoclips(clips, method="compose")

            timeline_clips: list[VideoFileClip | ColorClip] = []
            for idx, clip in enumerate(clips):
                timeline_clips.append(clip)
                if idx < len(clips) - 1:
                    timeline_clips.append(
                        ColorClip(size=(clip.w, clip.h), color=(0, 0, 0), duration=transition_duration)
                    )
            return concatenate_videoclips(timeline_clips, method="compose")
        else:
            return concatenate_videoclips(clips, method="compose")

    def _add_subtitles(
        self,
        video: VideoFileClip | CompositeVideoClip,
        subtitles: list[dict],
    ) -> CompositeVideoClip:
        """叠加字幕"""
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
                except Exception as e:
                    logger.warning("字幕渲染失败: %s", e)

        if subtitle_clips:
            return CompositeVideoClip([video] + subtitle_clips)
        return CompositeVideoClip([video])

    async def compose(
        self,
        project_id: str,
        options: CompositionOptions,
        db: AsyncSession,
    ) -> str:
        """完整合成流程"""
        import asyncio

        output_dir = Path(settings.composition_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{project_id}.mp4"

        # 获取所有场景和视频片段
        scenes = (await db.execute(
            select(Scene)
            .where(Scene.project_id == project_id)
            .order_by(Scene.sequence_order)
        )).scalars().all()
        if not scenes:
            raise ValueError("没有可合成的场景")

        non_generated_scenes = [scene.title for scene in scenes if scene.status != "generated"]
        if non_generated_scenes:
            title_preview = "、".join(non_generated_scenes[:5])
            raise ValueError(f"以下场景尚未生成完成: {title_preview}")

        publish_progress(project_id, "compose_progress", {"message": "收集视频片段...", "percent": 10})

        # 收集场景素材
        scene_assets: list[dict[str, Any]] = []
        subtitles: list[dict[str, Any]] = []
        missing_scenes: list[str] = []

        for scene in scenes:
            clips = (await db.execute(
                select(VideoClip)
                .where(VideoClip.scene_id == scene.id, VideoClip.status == "completed")
                .order_by(VideoClip.clip_order)
            )).scalars().all()

            scene_clip_paths: list[Path] = []
            scene_duration = 0.0
            for clip in clips:
                if clip.file_path:
                    clip_path = Path(clip.file_path)
                    if clip_path.exists():
                        scene_clip_paths.append(clip_path)
                        scene_duration += float(clip.duration_seconds or 0.0)

            if not scene_clip_paths:
                missing_scenes.append(scene.title)
                continue

            scene_duration = max(scene_duration, 0.1)
            scene_assets.append({
                "scene_id": scene.id,
                "scene_title": scene.title,
                "clip_paths": scene_clip_paths,
                "duration": scene_duration,
                "dialogue": scene.dialogue,
                "transition_hint": scene.transition_hint,
            })

        if missing_scenes:
            missing_preview = "、".join(missing_scenes[:5])
            raise ValueError(f"以下场景缺少可用视频片段: {missing_preview}")

        # 按场景时间轴计算字幕/TTS 起始时间，考虑场景间转场对时间线的影响
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
            if idx < len(scene_assets) - 1 and options.transition_duration > 0:
                transition = self._resolve_transition(asset["transition_hint"], options.transition_type)
                if transition == TransitionType.CROSSFADE:
                    current_start = max(0.0, current_start - options.transition_duration)
                elif transition == TransitionType.FADE_BLACK:
                    current_start += options.transition_duration

        publish_progress(project_id, "compose_progress", {"message": "拼接视频...", "percent": 30})

        # 在线程中执行 moviepy 操作
        def _do_compose():
            # 先在场景内部拼接（不做转场），再按场景边界应用转场
            scene_videos: list[VideoFileClip | CompositeVideoClip] = []
            for asset in scene_assets:
                scene_video = self._load_and_transition(
                    asset["clip_paths"],
                    TransitionType.NONE,
                    0.0,
                )
                scene_videos.append(scene_video)

            merged_video = scene_videos[0]
            for idx in range(1, len(scene_videos)):
                previous_asset = scene_assets[idx - 1]
                next_video = scene_videos[idx]
                transition = self._resolve_transition(previous_asset["transition_hint"], options.transition_type)

                if transition == TransitionType.CROSSFADE and options.transition_duration > 0:
                    merged_video = concatenate_videoclips(
                        [merged_video, next_video],
                        method="compose",
                        padding=-options.transition_duration,
                    )
                elif transition == TransitionType.FADE_BLACK and options.transition_duration > 0:
                    black = ColorClip(
                        size=(int(merged_video.w), int(merged_video.h)),
                        color=(0, 0, 0),
                        duration=options.transition_duration,
                    )
                    merged_video = concatenate_videoclips([merged_video, black, next_video], method="compose")
                else:
                    merged_video = concatenate_videoclips([merged_video, next_video], method="compose")

            render_video: VideoFileClip | CompositeVideoClip = merged_video

            try:
                # 叠加字幕
                if options.include_subtitles and subtitles:
                    render_video = self._add_subtitles(merged_video, subtitles)

                # 输出
                render_video.write_videofile(
                    str(output_path),
                    fps=24,
                    codec="libx264",
                    audio_codec="aac",
                    logger=None,
                )
            finally:
                render_video.close()
                if render_video is not merged_video:
                    merged_video.close()
            return output_path

        await asyncio.to_thread(_do_compose)

        publish_progress(project_id, "compose_progress", {"message": "处理音频...", "percent": 70})

        # TTS 配音
        if options.include_tts:
            tts_dir = output_dir / f"{project_id}_tts"
            scene_data = [{"id": s.id, "dialogue": s.dialogue} for s in scenes]
            audio_results = await self._tts.generate_for_scenes(scene_data, tts_dir)

            if audio_results:
                # 合并 TTS 音频到视频
                def _merge_audio():
                    video_with_audio = VideoFileClip(str(output_path))
                    tts_tracks: list[AudioFileClip] = []
                    composed_audio: CompositeAudioClip | None = None
                    final = None

                    try:
                        for subtitle in subtitles:
                            scene_id = subtitle.get("scene_id")
                            if scene_id not in audio_results:
                                continue

                            start_time = max(0.0, float(subtitle.get("start", 0.0)))
                            scene_duration = max(0.1, float(subtitle.get("duration", 0.1)))
                            audio_clip = AudioFileClip(str(audio_results[scene_id].path))
                            if audio_clip.duration > scene_duration:
                                audio_clip = audio_clip.subclipped(0, scene_duration)
                            audio_clip = audio_clip.with_start(start_time)
                            tts_tracks.append(audio_clip)

                        audio_layers = [track for track in [video_with_audio.audio, *tts_tracks] if track is not None]
                        if not audio_layers:
                            return

                        composed_audio = CompositeAudioClip(audio_layers).with_duration(video_with_audio.duration)
                        final = video_with_audio.with_audio(composed_audio)

                        final_path = output_dir / f"{project_id}_final.mp4"
                        final.write_videofile(str(final_path), fps=24, codec="libx264", audio_codec="aac", logger=None)

                        # 替换为最终版本
                        import shutil
                        shutil.move(str(final_path), str(output_path))
                    finally:
                        if final is not None:
                            final.close()
                        if composed_audio is not None:
                            composed_audio.close()
                        for track in tts_tracks:
                            track.close()
                        video_with_audio.close()

                await asyncio.to_thread(_merge_audio)

        publish_progress(project_id, "compose_complete", {"message": "合成完成", "percent": 100})

        # 创建合成任务记录
        task = CompositionTask(
            project_id=project_id,
            output_path=str(output_path),
            transition_type=options.transition_type.value,
            include_subtitles=options.include_subtitles,
            include_tts=options.include_tts,
            status="completed",
        )
        db.add(task)
        await db.commit()

        return task.id
