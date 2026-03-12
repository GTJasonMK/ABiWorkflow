from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import time
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clip_status import CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED
from app.config import resolve_runtime_path, settings
from app.models import Panel, VideoClip
from app.panel_status import (
    PANEL_REGENERATABLE_STATUSES,
    PANEL_STATUS_COMPLETED,
    PANEL_STATUS_FAILED,
    PANEL_STATUS_PROCESSING,
)
from app.progress_payload import (
    PROGRESS_KEY_MESSAGE,
    PROGRESS_KEY_PANEL_ORDER,
    PROGRESS_KEY_PERCENT,
)
from app.services.panel_generation import (
    list_project_panels_ordered,
    resolve_panel_generation_request,
    reset_panel_generation_state,
)
from app.services.progress import publish_progress
from app.services.script_asset_compiler import get_panel_effective_binding
from app.video_providers.base import VideoGenerateRequest, VideoProvider

logger = logging.getLogger(__name__)


class VideoGeneratorService:
    """视频生成服务：管理批量生成、时长拆分。"""

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
        total_duration = max(0.1, total_duration)
        max_duration = max(0.1, max_duration)
        if total_duration <= max_duration:
            return [total_duration]

        clip_count = math.ceil(total_duration / max_duration)
        clip_duration = total_duration / clip_count
        return [clip_duration] * clip_count

    @staticmethod
    def _seed_for(panel: Panel, clip_order: int, candidate_index: int = 0) -> int:
        raw = f"{panel.project_id}:{panel.id}:{clip_order}:{candidate_index}"
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return int(digest[:8], 16)

    @staticmethod
    def _build_request(
        panel: Panel,
        *,
        prompt: str,
        negative_prompt: str | None,
        reference_image_url: str | None,
        duration: float,
        clip_order: int,
        candidate_index: int = 0,
    ) -> VideoGenerateRequest:
        return VideoGenerateRequest(
            prompt=prompt,
            duration_seconds=duration,
            negative_prompt=negative_prompt,
            reference_image_url=reference_image_url,
            seed=VideoGeneratorService._seed_for(panel, clip_order, candidate_index),
        )

    def _build_clip_requests(
        self,
        panel: Panel,
        *,
        prompt: str,
        negative_prompt: str | None,
        reference_image_url: str | None,
        candidate_index: int = 0,
    ) -> list[tuple[int, VideoGenerateRequest]]:
        durations = self._split_durations(panel.duration_seconds, self._provider.max_duration_seconds)
        return [
            (
                clip_order,
                self._build_request(
                    panel,
                    prompt=prompt,
                    negative_prompt=negative_prompt,
                    reference_image_url=reference_image_url,
                    duration=duration,
                    clip_order=clip_order,
                    candidate_index=candidate_index,
                ),
            )
            for clip_order, duration in enumerate(durations)
        ]

    def split_by_duration(
        self,
        panel: Panel,
        *,
        prompt: str,
        negative_prompt: str | None,
        reference_image_url: str | None,
    ) -> list[VideoGenerateRequest]:
        return [
            request
            for _, request in self._build_clip_requests(
                panel,
                prompt=prompt,
                negative_prompt=negative_prompt,
                reference_image_url=reference_image_url,
            )
        ]

    async def _wait_for_completion(self, task_id: str):
        start = time.monotonic()
        while True:
            status = await self._provider.poll_status(task_id)
            normalized = status.status.lower()
            if normalized in {CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED, "error", "canceled", "cancelled"}:
                return status

            if (time.monotonic() - start) >= self._task_timeout_seconds:
                raise TimeoutError(f"任务 {task_id} 轮询超时（>{self._task_timeout_seconds}s）")

            await asyncio.sleep(self._poll_interval_seconds)

    async def _load_panel_generation_context(
        self,
        panel_id: str,
        db: AsyncSession,
    ) -> tuple[Panel, dict[str, str | None]]:
        panel = (await db.execute(select(Panel).where(Panel.id == panel_id))).scalar_one()
        effective_binding = await get_panel_effective_binding(panel.id, db, auto_compile=True)
        resolved = resolve_panel_generation_request(panel, effective_binding)
        prompt = str(resolved.get("prompt") or "").strip()
        if not prompt:
            raise ValueError(f"分镜 {panel.title} 缺少视频提示词，无法生成")
        return panel, resolved

    @staticmethod
    def _apply_panel_generation_status(panel: Panel, clips: list[VideoClip]) -> None:
        panel.status = (
            PANEL_STATUS_COMPLETED
            if clips and all(item.status == CLIP_STATUS_COMPLETED for item in clips)
            else PANEL_STATUS_FAILED
        )

    def _build_output_path(
        self,
        panel: Panel,
        clip_order: int,
        task_id: str,
        *,
        candidate_index: int | None = None,
    ) -> Path:
        project_dir = self._output_dir / panel.project_id
        project_dir.mkdir(parents=True, exist_ok=True)
        if candidate_index is None:
            filename = f"{panel.id}_{clip_order}_{task_id}.mp4"
        else:
            filename = f"{panel.id}_{clip_order}_c{candidate_index}_{task_id}.mp4"
        return project_dir / filename

    @staticmethod
    def _build_clip_record(
        panel: Panel,
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
            panel_id=panel.id,
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
        panel: Panel,
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
                    panel,
                    clip_order,
                    task_id,
                    candidate_index=candidate_index,
                )
                local_file = await self._provider.download(task_id, output_path)
                return self._build_clip_record(
                    panel,
                    request,
                    clip_order=clip_order,
                    candidate_index=candidate_index,
                    is_selected=is_selected,
                    provider_task_id=task_id,
                    file_path=str(local_file),
                    status=CLIP_STATUS_COMPLETED,
                )

            return self._build_clip_record(
                panel,
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
                "分镜 %s 候选 %s 片段 %d 生成失败: %s",
                panel.id,
                candidate_index if candidate_index is not None else "default",
                clip_order,
                err,
            )
            return self._build_clip_record(
                panel,
                request,
                clip_order=clip_order,
                candidate_index=candidate_index,
                is_selected=is_selected,
                status=CLIP_STATUS_FAILED,
                error_message=str(err),
            )

    async def _generate_request_batch(
        self,
        panel: Panel,
        db: AsyncSession,
        clip_requests: list[tuple[int, VideoGenerateRequest]],
        *,
        candidate_index: int | None = None,
        is_selected: bool = False,
    ) -> list[VideoClip]:
        clips: list[VideoClip] = []
        for clip_order, request in clip_requests:
            clip = await self._generate_clip(
                panel,
                request,
                clip_order=clip_order,
                candidate_index=candidate_index,
                is_selected=is_selected,
            )
            db.add(clip)
            clips.append(clip)
        return clips

    async def generate_panel(self, panel: Panel, db: AsyncSession) -> list[VideoClip]:
        panel_with_context, request_fields = await self._load_panel_generation_context(panel.id, db)

        await db.execute(delete(VideoClip).where(VideoClip.panel_id == panel_with_context.id))
        reset_panel_generation_state(panel_with_context, clear_lipsync=True)
        panel_with_context.status = PANEL_STATUS_PROCESSING
        await db.flush()

        clips = await self._generate_request_batch(
            panel_with_context,
            db,
            self._build_clip_requests(
                panel_with_context,
                prompt=str(request_fields["prompt"]),
                negative_prompt=request_fields["negative_prompt"],
                reference_image_url=request_fields["reference_image_url"],
            ),
        )

        self._apply_panel_generation_status(panel_with_context, clips)
        await db.flush()
        return clips

    async def generate_candidates(
        self,
        panel: Panel,
        candidate_count: int,
        db: AsyncSession,
    ) -> list[VideoClip]:
        panel_with_context, request_fields = await self._load_panel_generation_context(panel.id, db)
        existing_clips = (await db.execute(
            select(VideoClip).where(VideoClip.panel_id == panel_with_context.id)
        )).scalars().all()
        has_existing = len(existing_clips) > 0
        max_candidate = max((item.candidate_index for item in existing_clips), default=-1)

        all_new_clips: list[VideoClip] = []
        for candidate_offset in range(candidate_count):
            candidate_idx = max_candidate + 1 + candidate_offset
            auto_select = (not has_existing) and candidate_offset == 0
            clip_requests = self._build_clip_requests(
                panel_with_context,
                prompt=str(request_fields["prompt"]),
                negative_prompt=request_fields["negative_prompt"],
                reference_image_url=request_fields["reference_image_url"],
                candidate_index=candidate_idx,
            )
            all_new_clips.extend(
                await self._generate_request_batch(
                    panel_with_context,
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
        panel_ids: set[str] | None = None,
    ) -> None:
        panels = await list_project_panels_ordered(project_id, db)
        if panel_ids is not None:
            panels = [panel for panel in panels if panel.id in panel_ids]
        panels = [panel for panel in panels if panel.status in PANEL_REGENERATABLE_STATUSES]
        total = len(panels)

        if total == 0:
            publish_progress(project_id, "generate_complete", {
                PROGRESS_KEY_MESSAGE: "没有需要生成的分镜",
                PROGRESS_KEY_PERCENT: 100,
            })
            return

        for idx, panel in enumerate(panels):
            publish_progress(project_id, "generate_progress", {
                PROGRESS_KEY_MESSAGE: f"正在生成分镜 {idx + 1}/{total}: {panel.title}",
                PROGRESS_KEY_PERCENT: round((idx / total) * 100),
                PROGRESS_KEY_PANEL_ORDER: idx + 1,
            })
            await self.generate_panel(panel, db)

        await db.commit()
        publish_progress(project_id, "generate_complete", {
            PROGRESS_KEY_MESSAGE: f"全部 {total} 个分镜生成完成",
            PROGRESS_KEY_PERCENT: 100,
        })
