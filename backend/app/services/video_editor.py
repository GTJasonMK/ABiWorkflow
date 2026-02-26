from __future__ import annotations

import logging
import traceback
import uuid
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
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import resolve_runtime_path, settings
from app.models import CompositionTask, Scene, VideoClip
from app.services.progress import publish_progress
from app.services.tts_service import TTSService

logger = logging.getLogger(__name__)
READY_SCENE_STATUSES = {"generated", "completed"}


class TransitionType(str, Enum):
    NONE = "none"
    CROSSFADE = "crossfade"
    FADE_BLACK = "fade_black"


class CompositionOptions(BaseModel):
    """合成选项"""

    transition_type: TransitionType = TransitionType.CROSSFADE
    transition_duration: float = Field(default=0.5, ge=0.0, le=5.0)
    include_subtitles: bool = True
    include_tts: bool = True


class VideoEditorService:
    """视频剪辑合成服务"""

    def __init__(self):
        self._tts = TTSService()

    @staticmethod
    def _resolve_media_path(path_value: str | Path) -> Path:
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

    @staticmethod
    def _safe_crossfade_overlap(left_duration: float, right_duration: float, requested: float) -> float:
        """计算安全可用的交叉淡入淡出时长，避免超过任一片段时长。"""
        requested_duration = max(0.0, float(requested))
        left = max(0.0, float(left_duration))
        right = max(0.0, float(right_duration))
        max_overlap = min(left, right)
        return min(requested_duration, max_overlap)

    @staticmethod
    def _load_video_clip(path: Path) -> VideoFileClip:
        """加载并验证单个视频片段，确保可用于后续合成。"""
        clip = VideoFileClip(str(path))
        if clip.duration is None or clip.duration <= 0:
            clip.close()
            raise ValueError(f"视频文件无效（时长为空或为零）: {path}")
        if clip.size is None or clip.w <= 0 or clip.h <= 0:
            clip.close()
            raise ValueError(f"视频文件无效（尺寸异常）: {path}")
        return clip

    def _load_scene_clip(self, clip_paths: list[Path]) -> VideoFileClip | CompositeVideoClip:
        """加载场景内部的多个片段并拼接（不含转场）。"""
        clips = [self._load_video_clip(p) for p in clip_paths]

        if not clips:
            raise ValueError("没有可用的视频片段")

        if len(clips) == 1:
            return clips[0]

        return concatenate_videoclips(clips, method="compose")

    def _add_subtitles(
        self,
        video: VideoFileClip | CompositeVideoClip,
        subtitles: list[dict],
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
                except Exception as e:
                    logger.warning("字幕渲染失败: %s", e)

        if subtitle_clips:
            return CompositeVideoClip([video] + subtitle_clips)
        return video

    async def compose(
        self,
        project_id: str,
        options: CompositionOptions,
        db: AsyncSession,
    ) -> str:
        """完整合成流程（单次编码写入）"""
        import asyncio

        output_dir = resolve_runtime_path(settings.composition_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        composition_id = str(uuid.uuid4())
        project_compose_dir = output_dir / project_id
        project_compose_dir.mkdir(parents=True, exist_ok=True)
        output_path = project_compose_dir / f"{composition_id}.mp4"

        # 获取所有场景和视频片段
        scenes = (await db.execute(
            select(Scene)
            .where(Scene.project_id == project_id)
            .order_by(Scene.sequence_order)
        )).scalars().all()
        if not scenes:
            raise ValueError("没有可合成的场景")

        non_generated_scenes = [scene.title for scene in scenes if scene.status not in READY_SCENE_STATUSES]
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
                .where(
                    VideoClip.scene_id == scene.id,
                    VideoClip.status == "completed",
                    VideoClip.is_selected == True,  # noqa: E712
                )
                .order_by(VideoClip.clip_order)
            )).scalars().all()

            scene_clip_paths: list[Path] = []
            scene_duration = 0.0
            for clip in clips:
                if clip.file_path:
                    clip_path = self._resolve_media_path(clip.file_path)
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

        # 按场景时间轴计算字幕/TTS 起始时间，与 concatenate_videoclips(chain) 时间线对齐
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
            # fade_black 转场会插入黑场片段，字幕起始需跳过该时长
            if idx < len(scene_assets) - 1 and options.transition_duration > 0:
                transition = self._resolve_transition(asset["transition_hint"], options.transition_type)
                if transition == TransitionType.FADE_BLACK:
                    current_start += options.transition_duration

        total_duration = max(0.1, current_start)

        # 先并行生成 TTS 配音（在视频编码之前完成，避免二次编码）
        tts_audio_map: dict[str, Any] = {}
        if options.include_tts:
            publish_progress(project_id, "compose_progress", {"message": "生成配音...", "percent": 20})
            tts_dir = output_dir / f"{project_id}_tts"
            scene_data = [{"id": s.id, "dialogue": s.dialogue} for s in scenes]
            tts_audio_map = await self._tts.generate_for_scenes(scene_data, tts_dir)

        publish_progress(project_id, "compose_progress", {"message": "拼接视频与音频...", "percent": 40})

        # 单次编码写入：视频 + 字幕 + TTS 音频一次性合成输出
        def _do_compose():
            # 加载场景内部片段（场景内无转场，直接拼接）
            scene_videos: list[VideoFileClip | CompositeVideoClip] = []
            for asset in scene_assets:
                try:
                    scene_video = self._load_scene_clip(asset["clip_paths"])
                except Exception as e:
                    raise ValueError(f"加载场景 [{asset['scene_title']}] 的视频失败: {e}") from e
                logger.info(
                    "已加载场景 [%s]: duration=%.2f, size=%dx%d, audio=%s",
                    asset["scene_title"], scene_video.duration,
                    scene_video.w, scene_video.h,
                    "有" if scene_video.audio is not None else "无",
                )
                scene_videos.append(scene_video)

            # 构建顺序时间线片段列表（chain 模式按序播放，不需要手动设定 start）
            timeline_clips: list[VideoFileClip | CompositeVideoClip | ColorClip] = []
            ref_w = int(scene_videos[0].w)
            ref_h = int(scene_videos[0].h)

            for idx, scene_video in enumerate(scene_videos):
                timeline_clips.append(scene_video)

                # fade_black 转场：在相邻场景之间插入黑场片段
                if idx < len(scene_videos) - 1:
                    asset = scene_assets[idx]
                    transition = self._resolve_transition(asset["transition_hint"], options.transition_type)

                    if transition == TransitionType.FADE_BLACK and options.transition_duration > 0:
                        black = ColorClip(
                            size=(ref_w, ref_h), color=(0, 0, 0),
                            duration=options.transition_duration,
                        )
                        timeline_clips.append(black)

            total_clip_duration = sum(c.duration for c in timeline_clips if hasattr(c, "duration"))
            logger.info(
                "时间线构建完成: %d 个片段, 预估总时长=%.2f, 参考尺寸=%dx%d",
                len(timeline_clips), total_clip_duration, ref_w, ref_h,
            )

            # 使用 concatenate_videoclips 替代手动 CompositeVideoClip —— 更稳定可靠
            # 先按顺序拼接所有视频片段（含黑场转场），再叠加字幕和音频
            merged_video = concatenate_videoclips(timeline_clips, method="chain")

            render_video: VideoFileClip | CompositeVideoClip = merged_video

            # tts_audio_layers: 参与 CompositeAudioClip 合成的音频轨道
            # tts_keepalive: subclipped 后需要保活的原始 AudioFileClip（共享读取器）
            tts_audio_layers: list[AudioFileClip] = []
            tts_keepalive: list[AudioFileClip] = []
            try:
                # 叠加字幕
                if options.include_subtitles and subtitles:
                    render_video = self._add_subtitles(merged_video, subtitles)

                # 叠加 TTS 音频（与视频一起单次写入，避免二次编码）
                if tts_audio_map:
                    for subtitle in subtitles:
                        scene_id = subtitle.get("scene_id")
                        if scene_id not in tts_audio_map:
                            continue

                        start_time = max(0.0, float(subtitle.get("start", 0.0)))
                        scene_duration = max(0.1, float(subtitle.get("duration", 0.1)))
                        raw_audio_clip = AudioFileClip(str(tts_audio_map[scene_id].path))
                        if raw_audio_clip.duration > scene_duration:
                            audio_clip = raw_audio_clip.subclipped(0, scene_duration)
                            # subclipped 返回的子片段通过闭包引用原始 clip 的 reader，
                            # 不能关闭原始 clip，否则 reader=None 导致 NoneType get_frame。
                            # 放入 keepalive 列表，在 finally 中统一关闭。
                            tts_keepalive.append(raw_audio_clip)
                        else:
                            audio_clip = raw_audio_clip
                        tts_audio_layers.append(audio_clip.with_start(start_time))

                    if tts_audio_layers:
                        audio_layers = [
                            track for track in [render_video.audio, *tts_audio_layers]
                            if track is not None
                        ]
                        if audio_layers:
                            composed_audio = CompositeAudioClip(audio_layers).with_duration(
                                render_video.duration
                            )
                            render_video = render_video.with_audio(composed_audio)

                # 检查最终视频是否包含音频轨道
                has_audio = render_video.audio is not None
                logger.info(
                    "开始写入视频: duration=%.2f, audio=%s, output=%s",
                    render_video.duration, "有" if has_audio else "无", output_path,
                )

                render_video.write_videofile(
                    str(output_path),
                    fps=24,
                    codec="libx264",
                    audio=has_audio,
                    audio_codec="aac" if has_audio else None,
                    logger=None,
                )
            except Exception:
                logger.error("视频合成写入失败，完整调用栈:\n%s", traceback.format_exc())
                raise
            finally:
                for clip in tts_keepalive:
                    clip.close()
                for clip in tts_audio_layers:
                    clip.close()
                render_video.close()
                if render_video is not merged_video:
                    merged_video.close()
            return output_path

        await asyncio.to_thread(_do_compose)

        publish_progress(project_id, "compose_complete", {"message": "合成完成", "percent": 100})

        # 创建合成任务记录
        task = CompositionTask(
            id=composition_id,
            project_id=project_id,
            output_path=str(output_path),
            duration_seconds=total_duration,
            transition_type=options.transition_type.value,
            include_subtitles=options.include_subtitles,
            include_tts=options.include_tts,
            status="completed",
        )
        db.add(task)
        await db.commit()

        return task.id

    async def trim(
        self,
        composition_id: str,
        start_time: float,
        end_time: float,
        db: AsyncSession,
    ) -> str:
        """裁剪已有合成视频，返回新合成记录 ID。

        使用 moviepy subclipped 提取指定时间段，输出为新文件，
        原始合成记录不受影响。
        """
        import asyncio as _asyncio

        original = (await db.execute(
            select(CompositionTask).where(CompositionTask.id == composition_id)
        )).scalar_one_or_none()
        if original is None:
            raise ValueError("合成任务不存在")
        if not original.output_path:
            raise ValueError("原始视频文件路径为空")

        source_path = self._resolve_media_path(original.output_path)
        if not source_path.exists():
            raise ValueError(f"源视频文件不存在: {source_path}")

        new_id = str(uuid.uuid4())
        output_dir = resolve_runtime_path(settings.composition_output_dir) / original.project_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{new_id}.mp4"

        def _do_trim() -> float:
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

        actual_duration = await _asyncio.to_thread(_do_trim)

        new_task = CompositionTask(
            id=new_id,
            project_id=original.project_id,
            output_path=str(output_path),
            duration_seconds=actual_duration,
            transition_type=original.transition_type,
            include_subtitles=original.include_subtitles,
            include_tts=original.include_tts,
            status="completed",
        )
        db.add(new_task)

        from app.services.composition_state import mark_completed_compositions_stale
        await mark_completed_compositions_stale(db, original.project_id, exclude_composition_id=new_id)
        await db.commit()

        logger.info(
            "视频裁剪完成: source=%s, range=[%.2f, %.2f], new=%s, duration=%.2f",
            composition_id, start_time, end_time, new_id, actual_duration,
        )
        return new_id
