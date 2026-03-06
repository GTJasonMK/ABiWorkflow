from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import time
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.clip_status import CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED
from app.config import resolve_runtime_path, settings
from app.models import Scene, SceneCharacter, VideoClip
from app.progress_payload import (
    PROGRESS_KEY_MESSAGE,
    PROGRESS_KEY_PANEL_ORDER,
    PROGRESS_KEY_PERCENT,
)
from app.scene_status import (
    REGENERATABLE_SCENE_STATUSES,
    SCENE_STATUS_FAILED,
    SCENE_STATUS_GENERATED,
    SCENE_STATUS_GENERATING,
)
from app.services.progress import publish_progress
from app.video_providers.base import VideoGenerateRequest, VideoProvider

logger = logging.getLogger(__name__)


class VideoGeneratorService:
    """视频生成服务：管理批量生成、时长拆分"""

    def __init__(
        self,
        provider: VideoProvider,
        output_dir: str | Path | None = None,
        poll_interval_seconds: float | None = None,
        task_timeout_seconds: float | None = None,
    ):
        self._provider = provider
        self._output_dir = resolve_runtime_path(output_dir or settings.video_output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self._poll_interval_seconds = max(0.1, poll_interval_seconds or settings.video_poll_interval_seconds)
        self._task_timeout_seconds = max(1.0, task_timeout_seconds or settings.video_task_timeout_seconds)

    @staticmethod
    def _split_durations(total_duration: float, max_duration: float) -> list[float]:
        """按 provider 最大时长拆分，返回每段时长列表。"""
        total_duration = max(0.1, total_duration)
        max_duration = max(0.1, max_duration)

        if total_duration <= max_duration:
            return [total_duration]

        clip_count = math.ceil(total_duration / max_duration)
        clip_duration = total_duration / clip_count
        return [clip_duration] * clip_count

    @staticmethod
    def _pick_reference_image(scene: Scene) -> str | None:
        """优先使用分镜映射场景关联角色中的参考图，提升跨分镜一致性。"""
        for scene_character in scene.characters:
            character = scene_character.character
            if character and character.reference_image_url:
                return character.reference_image_url
        # Panel->Scene 桥接场景会复用 setting 传递参考图 URL。
        setting = (scene.setting or "").strip()
        if setting.startswith("http://") or setting.startswith("https://"):
            return setting
        return None

    @staticmethod
    def _seed_for(scene: Scene, clip_order: int, candidate_index: int = 0) -> int:
        """为分镜映射片段生成稳定随机种子，降低多次生成结果漂移。"""
        raw = f"{scene.project_id}:{scene.id}:{clip_order}:{candidate_index}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    @staticmethod
    def _build_request(
        scene: Scene,
        duration: float,
        clip_order: int,
        reference_image_url: str | None,
        *,
        candidate_index: int = 0,
    ) -> VideoGenerateRequest:
        return VideoGenerateRequest(
            prompt=scene.video_prompt or "",
            duration_seconds=duration,
            negative_prompt=scene.negative_prompt,
            reference_image_url=reference_image_url,
            seed=VideoGeneratorService._seed_for(scene, clip_order, candidate_index),
        )

    def _build_clip_requests(
        self,
        scene: Scene,
        reference_image_url: str | None,
        *,
        candidate_index: int = 0,
    ) -> list[tuple[int, VideoGenerateRequest]]:
        durations = self._split_durations(scene.duration_seconds, self._provider.max_duration_seconds)
        return [
            (
                clip_order,
                self._build_request(
                    scene,
                    duration,
                    clip_order,
                    reference_image_url,
                    candidate_index=candidate_index,
                ),
            )
            for clip_order, duration in enumerate(durations)
        ]

    def split_by_duration(self, scene: Scene, reference_image_url: str | None = None) -> list[VideoGenerateRequest]:
        """将超长分镜映射拆分为多个子请求。"""
        return [request for _, request in self._build_clip_requests(scene, reference_image_url)]

    async def _wait_for_completion(self, task_id: str):
        """轮询任务直到完成/失败/超时。"""
        start = time.monotonic()
        while True:
            status = await self._provider.poll_status(task_id)
            normalized = status.status.lower()
            if normalized in {CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED, "error", "canceled", "cancelled"}:
                return status

            if (time.monotonic() - start) >= self._task_timeout_seconds:
                raise TimeoutError(f"任务 {task_id} 轮询超时（>{self._task_timeout_seconds}s）")

            await asyncio.sleep(self._poll_interval_seconds)

    async def _load_scene_with_relations(self, scene_id: str, db: AsyncSession) -> Scene:
        stmt = (
            select(Scene)
            .where(Scene.id == scene_id)
            .options(selectinload(Scene.characters).selectinload(SceneCharacter.character))
        )
        return (await db.execute(stmt)).scalar_one()

    def _build_output_path(
        self,
        scene: Scene,
        clip_order: int,
        task_id: str,
        *,
        candidate_index: int | None = None,
    ) -> Path:
        project_dir = self._output_dir / scene.project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        if candidate_index is None:
            filename = f"{scene.id}_{clip_order}_{task_id}.mp4"
        else:
            filename = f"{scene.id}_{clip_order}_c{candidate_index}_{task_id}.mp4"
        return project_dir / filename

    @staticmethod
    def _build_clip_record(
        scene: Scene,
        request: VideoGenerateRequest,
        *,
        clip_order: int,
        candidate_index: int | None = None,
        is_selected: bool = False,
        status: str,
        provider_task_id: str | None = None,
        file_path: str | None = None,
        error_message: str | None = None,
    ) -> VideoClip:
        return VideoClip(
            scene_id=scene.id,
            clip_order=clip_order,
            candidate_index=candidate_index or 0,
            is_selected=is_selected,
            file_path=file_path,
            duration_seconds=request.duration_seconds,
            provider_task_id=provider_task_id,
            status=status,
            error_message=error_message,
        )

    async def _generate_clip(
        self,
        scene: Scene,
        request: VideoGenerateRequest,
        *,
        clip_order: int,
        candidate_index: int | None = None,
        is_selected: bool = False,
    ) -> VideoClip:
        try:
            task_id = await self._provider.generate(request)
            status = await self._wait_for_completion(task_id)

            if status.status.lower() == CLIP_STATUS_COMPLETED:
                output_path = self._build_output_path(
                    scene,
                    clip_order,
                    task_id,
                    candidate_index=candidate_index,
                )
                local_file = await self._provider.download(task_id, output_path)
                return self._build_clip_record(
                    scene,
                    request,
                    clip_order=clip_order,
                    candidate_index=candidate_index,
                    is_selected=is_selected,
                    provider_task_id=task_id,
                    file_path=str(local_file),
                    status=CLIP_STATUS_COMPLETED,
                )

            return self._build_clip_record(
                scene,
                request,
                clip_order=clip_order,
                candidate_index=candidate_index,
                is_selected=is_selected,
                provider_task_id=task_id,
                status=CLIP_STATUS_FAILED,
                error_message=status.error_message or f"任务状态: {status.status}",
            )
        except Exception as err:
            logger.error(
                "分镜映射 %s 候选 %s 片段 %d 生成失败: %s",
                scene.id,
                candidate_index if candidate_index is not None else "default",
                clip_order,
                err,
            )
            return self._build_clip_record(
                scene,
                request,
                clip_order=clip_order,
                candidate_index=candidate_index,
                is_selected=is_selected,
                status=CLIP_STATUS_FAILED,
                error_message=str(err),
            )

    async def _generate_request_batch(
        self,
        scene: Scene,
        db: AsyncSession,
        clip_requests: list[tuple[int, VideoGenerateRequest]],
        *,
        candidate_index: int | None = None,
        is_selected: bool = False,
    ) -> list[VideoClip]:
        clips: list[VideoClip] = []
        for clip_order, request in clip_requests:
            clip = await self._generate_clip(
                scene,
                request,
                clip_order=clip_order,
                candidate_index=candidate_index,
                is_selected=is_selected,
            )
            db.add(clip)
            clips.append(clip)
        return clips

    async def generate_scene(self, scene: Scene, db: AsyncSession) -> list[VideoClip]:
        """为单个分镜映射生成视频（重试时会先清理旧片段）。"""
        scene_with_relations = await self._load_scene_with_relations(scene.id, db)

        # 重试前清理旧片段，避免重复拼接
        await db.execute(delete(VideoClip).where(VideoClip.scene_id == scene_with_relations.id))
        scene_with_relations.status = SCENE_STATUS_GENERATING
        await db.flush()

        reference_image_url = self._pick_reference_image(scene_with_relations)
        clips = await self._generate_request_batch(
            scene_with_relations,
            db,
            self._build_clip_requests(scene_with_relations, reference_image_url),
        )

        all_completed = all(c.status == CLIP_STATUS_COMPLETED for c in clips)
        scene_with_relations.status = SCENE_STATUS_GENERATED if all_completed else SCENE_STATUS_FAILED
        await db.flush()

        return clips

    async def generate_candidates(
        self,
        scene: Scene,
        candidate_count: int,
        db: AsyncSession,
    ) -> list[VideoClip]:
        """为分镜映射生成多个候选视频（不清理旧片段，追加新候选）。"""
        scene_with_relations = await self._load_scene_with_relations(scene.id, db)

        existing_clips = (await db.execute(
            select(VideoClip).where(VideoClip.scene_id == scene_with_relations.id)
        )).scalars().all()
        has_existing = len(existing_clips) > 0
        max_candidate = max((c.candidate_index for c in existing_clips), default=-1)

        reference_image_url = self._pick_reference_image(scene_with_relations)
        all_new_clips: list[VideoClip] = []

        for candidate_offset in range(candidate_count):
            candidate_idx = max_candidate + 1 + candidate_offset
            auto_select = (not has_existing) and (candidate_offset == 0)
            clip_requests = self._build_clip_requests(
                scene_with_relations,
                reference_image_url,
                candidate_index=candidate_idx,
            )
            all_new_clips.extend(
                await self._generate_request_batch(
                    scene_with_relations,
                    db,
                    clip_requests,
                    candidate_index=candidate_idx,
                    is_selected=auto_select,
                )
            )

        await db.flush()
        return all_new_clips

    async def generate_all(
        self,
        project_id: str,
        db: AsyncSession,
        *,
        scene_ids: set[str] | None = None,
    ) -> None:
        """批量生成项目所有分镜映射的视频。"""
        stmt = (
            select(Scene)
            # 兼容异常中断后遗留的 generating 状态，允许后续重跑恢复。
            .where(Scene.project_id == project_id, Scene.status.in_(list(REGENERATABLE_SCENE_STATUSES)))
            .options(selectinload(Scene.characters).selectinload(SceneCharacter.character))
            .order_by(Scene.sequence_order)
        )
        if scene_ids:
            stmt = stmt.where(Scene.id.in_(list(scene_ids)))
        scenes = (await db.execute(stmt)).scalars().all()
        total = len(scenes)

        if total == 0:
            publish_progress(project_id, "generate_complete", {
                PROGRESS_KEY_MESSAGE: "没有需要生成的分镜",
                PROGRESS_KEY_PERCENT: 100,
            })
            return

        for idx, scene in enumerate(scenes):
            publish_progress(project_id, "generate_progress", {
                PROGRESS_KEY_MESSAGE: f"正在生成分镜 {idx + 1}/{total}: {scene.title}",
                PROGRESS_KEY_PERCENT: round((idx / total) * 100),
                PROGRESS_KEY_PANEL_ORDER: idx + 1,
            })

            await self.generate_scene(scene, db)

        await db.commit()
        publish_progress(project_id, "generate_complete", {
            PROGRESS_KEY_MESSAGE: f"全部 {total} 个分镜生成完成",
            PROGRESS_KEY_PERCENT: 100,
        })
