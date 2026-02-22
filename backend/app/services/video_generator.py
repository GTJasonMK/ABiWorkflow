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

from app.config import settings
from app.models import Scene, SceneCharacter, VideoClip
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
        self._output_dir = Path(output_dir or settings.video_output_dir)
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
        """优先使用场景关联角色中的参考图，提升跨场景一致性。"""
        for scene_character in scene.characters:
            character = scene_character.character
            if character and character.reference_image_url:
                return character.reference_image_url
        return None

    @staticmethod
    def _seed_for(scene: Scene, clip_order: int) -> int:
        """为场景片段生成稳定随机种子，降低多次生成结果漂移。"""
        raw = f"{scene.project_id}:{scene.id}:{clip_order}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    def split_by_duration(self, scene: Scene, reference_image_url: str | None = None) -> list[VideoGenerateRequest]:
        """将超长场景拆分为多个子请求"""
        durations = self._split_durations(scene.duration_seconds, self._provider.max_duration_seconds)
        requests: list[VideoGenerateRequest] = []
        for clip_order, duration in enumerate(durations):
            requests.append(
                VideoGenerateRequest(
                    prompt=scene.video_prompt or "",
                    duration_seconds=duration,
                    negative_prompt=scene.negative_prompt,
                    reference_image_url=reference_image_url,
                    seed=self._seed_for(scene, clip_order),
                )
            )
        return requests

    async def _wait_for_completion(self, task_id: str):
        """轮询任务直到完成/失败/超时。"""
        start = time.monotonic()
        while True:
            status = await self._provider.poll_status(task_id)
            normalized = status.status.lower()
            if normalized in {"completed", "failed", "error", "canceled", "cancelled"}:
                return status

            if (time.monotonic() - start) >= self._task_timeout_seconds:
                raise TimeoutError(f"任务 {task_id} 轮询超时（>{self._task_timeout_seconds}s）")

            await asyncio.sleep(self._poll_interval_seconds)

    async def generate_scene(self, scene: Scene, db: AsyncSession) -> list[VideoClip]:
        """为单个场景生成视频（重试时会先清理旧片段）。"""
        # 重新加载场景与角色关联，确保参考图可用
        stmt = (
            select(Scene)
            .where(Scene.id == scene.id)
            .options(selectinload(Scene.characters).selectinload(SceneCharacter.character))
        )
        scene_with_relations = (await db.execute(stmt)).scalar_one()

        # 重试前清理旧片段，避免重复拼接
        await db.execute(delete(VideoClip).where(VideoClip.scene_id == scene_with_relations.id))
        await db.flush()

        reference_image_url = self._pick_reference_image(scene_with_relations)
        requests = self.split_by_duration(scene_with_relations, reference_image_url=reference_image_url)
        clips: list[VideoClip] = []

        for idx, req in enumerate(requests):
            try:
                task_id = await self._provider.generate(req)
                status = await self._wait_for_completion(task_id)

                if status.status.lower() == "completed":
                    output_path = self._output_dir / f"{scene_with_relations.id}_{idx}_{task_id}.mp4"
                    local_file = await self._provider.download(task_id, output_path)
                    clip = VideoClip(
                        scene_id=scene_with_relations.id,
                        clip_order=idx,
                        file_path=str(local_file),
                        duration_seconds=req.duration_seconds,
                        provider_task_id=task_id,
                        status="completed",
                    )
                else:
                    clip = VideoClip(
                        scene_id=scene_with_relations.id,
                        clip_order=idx,
                        duration_seconds=req.duration_seconds,
                        provider_task_id=task_id,
                        status="failed",
                        error_message=status.error_message or f"任务状态: {status.status}",
                    )
            except Exception as e:
                logger.error("场景 %s 片段 %d 生成失败: %s", scene_with_relations.id, idx, e)
                clip = VideoClip(
                    scene_id=scene_with_relations.id,
                    clip_order=idx,
                    duration_seconds=req.duration_seconds,
                    status="failed",
                    error_message=str(e),
                )

            db.add(clip)
            clips.append(clip)

        # 更新场景状态
        all_completed = all(c.status == "completed" for c in clips)
        scene_with_relations.status = "generated" if all_completed else "failed"
        await db.flush()

        return clips

    async def generate_all(self, project_id: str, db: AsyncSession) -> None:
        """批量生成项目所有场景的视频"""
        stmt = (
            select(Scene)
            .where(Scene.project_id == project_id, Scene.status.in_(["pending", "failed"]))
            .options(selectinload(Scene.characters).selectinload(SceneCharacter.character))
            .order_by(Scene.sequence_order)
        )
        scenes = (await db.execute(stmt)).scalars().all()
        total = len(scenes)

        if total == 0:
            publish_progress(project_id, "generate_complete", {
                "message": "没有需要生成的场景",
                "percent": 100,
            })
            return

        for idx, scene in enumerate(scenes):
            publish_progress(project_id, "generate_progress", {
                "message": f"正在生成场景 {idx + 1}/{total}: {scene.title}",
                "percent": round((idx / total) * 100),
                "scene_id": scene.id,
            })

            await self.generate_scene(scene, db)

        await db.commit()
        publish_progress(project_id, "generate_complete", {
            "message": f"全部 {total} 个场景生成完成",
            "percent": 100,
        })
