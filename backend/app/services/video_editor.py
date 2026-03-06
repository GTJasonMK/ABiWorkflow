from __future__ import annotations

import logging
import traceback
import uuid
from pathlib import Path
from typing import Any

from moviepy import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    VideoFileClip,
    concatenate_videoclips,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.composition_status import COMPOSITION_STATUS_COMPLETED
from app.config import resolve_runtime_path, settings
from app.models import CompositionTask, Episode, Panel
from app.panel_status import PANEL_STATUS_COMPLETED
from app.progress_payload import PROGRESS_KEY_MESSAGE, PROGRESS_KEY_PERCENT
from app.services.progress import publish_progress
from app.services.tts_service import TTSService
from app.services.video_editor_media import (
    add_subtitles,
    build_subtitles_timeline,
    collect_panel_assets,
    load_panel_clip,
    resolve_media_path,
    resolve_transition,
    trim_video_file,
)
from app.services.video_editor_types import CompositionOptions, TransitionType

logger = logging.getLogger(__name__)


async def load_panels_for_composition(
    project_id: str,
    db: AsyncSession,
    *,
    episode_id: str | None = None,
) -> list[Panel]:
    panel_stmt = (
        select(Panel)
        .join(Episode, Panel.episode_id == Episode.id)
        .where(Panel.project_id == project_id)
        .order_by(Episode.episode_order, Panel.panel_order, Panel.created_at)
    )
    if episode_id:
        panel_stmt = panel_stmt.where(Panel.episode_id == episode_id)
    panels = (await db.execute(panel_stmt)).scalars().all()
    if not panels:
        raise ValueError("没有可合成的分镜")

    unready_panels = [panel.title for panel in panels if panel.status != PANEL_STATUS_COMPLETED]
    if unready_panels:
        title_preview = "、".join(unready_panels[:5])
        raise ValueError(f"以下分镜尚未生成完成: {title_preview}")
    return panels


class VideoEditorService:
    """视频剪辑合成服务"""

    def __init__(self):
        self._tts = TTSService()

    @staticmethod
    def _publish_compose_progress(
        project_id: str,
        message: str,
        percent: int,
        *,
        event: str = "compose_progress",
    ) -> None:
        publish_progress(project_id, event, {
            PROGRESS_KEY_MESSAGE: message,
            PROGRESS_KEY_PERCENT: percent,
        })

    @staticmethod
    def _ensure_project_output_dir(project_id: str) -> Path:
        output_dir = resolve_runtime_path(settings.composition_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        project_output_dir = output_dir / project_id
        project_output_dir.mkdir(parents=True, exist_ok=True)
        return project_output_dir

    @staticmethod
    def _build_composition_task(
        composition_id: str,
        project_id: str,
        output_path: Path,
        duration_seconds: float,
        *,
        episode_id: str | None,
        transition_type: str,
        include_subtitles: bool,
        include_tts: bool,
    ) -> CompositionTask:
        return CompositionTask(
            id=composition_id,
            project_id=project_id,
            episode_id=episode_id,
            output_path=str(output_path),
            duration_seconds=duration_seconds,
            transition_type=transition_type,
            include_subtitles=include_subtitles,
            include_tts=include_tts,
            status=COMPOSITION_STATUS_COMPLETED,
        )

    async def compose(
        self,
        project_id: str,
        options: CompositionOptions,
        db: AsyncSession,
        episode_id: str | None = None,
    ) -> str:
        """完整合成流程（单次编码写入）"""
        import asyncio

        project_compose_dir = self._ensure_project_output_dir(project_id)
        composition_id = str(uuid.uuid4())
        output_path = project_compose_dir / f"{composition_id}.mp4"

        panels = await load_panels_for_composition(project_id, db, episode_id=episode_id)

        self._publish_compose_progress(project_id, "收集视频片段...", 10)

        panel_assets, missing_panels = await collect_panel_assets(panels)

        if missing_panels:
            missing_preview = "、".join(missing_panels[:5])
            raise ValueError(f"以下分镜缺少可用视频片段: {missing_preview}")

        subtitles, total_duration = build_subtitles_timeline(
            panel_assets,
            options.transition_type,
            options.transition_duration,
        )

        # 先并行生成 TTS 配音（在视频编码之前完成，避免二次编码）
        tts_audio_map: dict[str, str] = {}
        if options.include_tts:
            self._publish_compose_progress(project_id, "生成配音...", 20)
            tts_dir = project_compose_dir.parent / f"{project_id}_tts"

            # 优先复用分镜已绑定的语音素材。
            for asset in panel_assets:
                panel_audio_source = asset.get("tts_audio_source")
                if panel_audio_source:
                    tts_audio_map[asset["panel_id"]] = panel_audio_source

            # 对缺少语音素材但有文本的分镜，再进行兜底 TTS 生成。
            tts_pending = [
                {"id": asset["panel_id"], "dialogue": asset["dialogue"]}
                for asset in panel_assets
                if asset["panel_id"] not in tts_audio_map
            ]
            generated_audio = await self._tts.generate_for_panels(tts_pending, tts_dir)
            for key, item in generated_audio.items():
                tts_audio_map[key] = str(item.path)

        self._publish_compose_progress(project_id, "拼接视频与音频...", 40)

        audio_timeline: list[dict[str, Any]] = []
        current_audio_start = 0.0
        for idx, asset in enumerate(panel_assets):
            audio_timeline.append({
                "panel_id": asset["panel_id"],
                "start": current_audio_start,
                "duration": asset["duration"],
            })
            current_audio_start += asset["duration"]
            if idx < len(panel_assets) - 1 and options.transition_duration > 0:
                transition = resolve_transition(asset["transition_hint"], options.transition_type)
                if transition == TransitionType.FADE_BLACK:
                    current_audio_start += options.transition_duration

        # 单次编码写入：视频 + 字幕 + TTS 音频一次性合成输出
        def _do_compose():
            # 加载分镜片段（分镜内按单片段处理）
            scene_videos: list[VideoFileClip | CompositeVideoClip] = []
            for asset in panel_assets:
                try:
                    scene_video = load_panel_clip(asset["clip_paths"])
                except Exception as e:
                    raise ValueError(f"加载分镜 [{asset['panel_title']}] 的视频失败: {e}") from e
                logger.info(
                    "已加载分镜 [%s]: duration=%.2f, size=%dx%d, audio=%s",
                    asset["panel_title"], scene_video.duration,
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
                    asset = panel_assets[idx]
                    transition = resolve_transition(asset["transition_hint"], options.transition_type)

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
                    render_video = add_subtitles(merged_video, subtitles)

                # 叠加 TTS 音频（与视频一起单次写入，避免二次编码）
                if tts_audio_map:
                    for segment in audio_timeline:
                        panel_id = str(segment.get("panel_id", ""))
                        if panel_id not in tts_audio_map:
                            continue

                        start_time = max(0.0, float(segment.get("start", 0.0)))
                        scene_duration = max(0.1, float(segment.get("duration", 0.1)))
                        raw_audio_clip = AudioFileClip(tts_audio_map[panel_id])
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

        self._publish_compose_progress(project_id, "合成完成", 100, event="compose_complete")

        task = self._build_composition_task(
            composition_id,
            project_id,
            output_path,
            total_duration,
            episode_id=episode_id,
            transition_type=options.transition_type.value,
            include_subtitles=options.include_subtitles,
            include_tts=options.include_tts,
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

        source_path = resolve_media_path(original.output_path)
        if not source_path.exists():
            raise ValueError(f"源视频文件不存在: {source_path}")

        new_id = str(uuid.uuid4())
        output_dir = self._ensure_project_output_dir(original.project_id)
        output_path = output_dir / f"{new_id}.mp4"

        actual_duration = await _asyncio.to_thread(trim_video_file, source_path, output_path, start_time, end_time)

        new_task = self._build_composition_task(
            new_id,
            original.project_id,
            output_path,
            actual_duration,
            episode_id=original.episode_id,
            transition_type=original.transition_type,
            include_subtitles=original.include_subtitles,
            include_tts=original.include_tts,
        )
        db.add(new_task)

        from app.services.composition_state import mark_completed_compositions_stale
        await mark_completed_compositions_stale(
            db,
            original.project_id,
            episode_id=original.episode_id,
            exclude_composition_id=new_id,
        )
        await db.commit()

        logger.info(
            "视频裁剪完成: source=%s, range=[%.2f, %.2f], new=%s, duration=%.2f",
            composition_id, start_time, end_time, new_id, actual_duration,
        )
        return new_id
