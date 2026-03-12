from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.episode_status import EPISODE_STATUS_DRAFT
from app.models import Episode, Panel, Project, VideoClip
from app.services.video_generator import VideoGeneratorService
from app.video_providers.base import VideoGenerateRequest, VideoProvider, VideoTaskStatus


class FakeVideoProvider(VideoProvider):
    def __init__(self):
        self.requests: list[VideoGenerateRequest] = []
        self._poll_counts: dict[str, int] = {}

    @property
    def name(self) -> str:
        return "fake"

    @property
    def max_duration_seconds(self) -> float:
        return 5.0

    async def generate(self, request: VideoGenerateRequest) -> str:
        self.requests.append(request)
        task_id = f"task-{len(self.requests)}"
        self._poll_counts[task_id] = 0
        return task_id

    async def poll_status(self, task_id: str) -> VideoTaskStatus:
        count = self._poll_counts[task_id]
        self._poll_counts[task_id] = count + 1
        if count == 0:
            return VideoTaskStatus(task_id=task_id, status="processing", progress_percent=50)
        return VideoTaskStatus(task_id=task_id, status="completed", progress_percent=100)

    async def download(self, task_id: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-video")
        return output_path


async def _create_panel_fixture(
    db_session: AsyncSession,
    tmp_path: Path,
    *,
    duration_seconds: float,
    reference_image_url: str | None = "https://example.com/ref.png",
    with_old_clip: bool = False,
) -> Panel:
    project = Project(name="测试项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(
        project_id=project.id,
        episode_order=0,
        title="第1集",
        status=EPISODE_STATUS_DRAFT,
    )
    db_session.add(episode)
    await db_session.flush()

    panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="第一镜",
        script_text="主角走向镜头",
        visual_prompt="A cinematic scene with the lead character",
        reference_image_url=reference_image_url,
        duration_seconds=duration_seconds,
        status="pending",
    )
    db_session.add(panel)
    await db_session.flush()

    if with_old_clip:
        db_session.add(
            VideoClip(
                panel_id=panel.id,
                clip_order=0,
                file_path=str(tmp_path / "old.mp4"),
                status="completed",
            )
        )
    await db_session.commit()
    return panel


def _build_service(tmp_path: Path, provider: VideoProvider | None = None) -> VideoGeneratorService:
    return VideoGeneratorService(
        provider=provider or FakeVideoProvider(),
        output_dir=tmp_path,
        poll_interval_seconds=0.01,
        task_timeout_seconds=5.0,
    )


@pytest.mark.asyncio
async def test_generate_panel_should_clear_old_clips_and_keep_consistency_data(
    db_session: AsyncSession,
    tmp_path: Path,
):
    panel = await _create_panel_fixture(
        db_session,
        tmp_path,
        duration_seconds=12.0,
        with_old_clip=True,
    )
    provider = FakeVideoProvider()
    service = _build_service(tmp_path, provider)

    await service.generate_panel(panel, db_session)
    await db_session.commit()

    clips = (
        await db_session.execute(
            select(VideoClip).where(VideoClip.panel_id == panel.id).order_by(VideoClip.clip_order)
        )
    ).scalars().all()
    assert len(clips) == 3
    assert all(item.status == "completed" for item in clips)
    assert all(item.file_path and Path(item.file_path).exists() for item in clips)

    assert len(provider.requests) == 3
    assert all(req.reference_image_url == "https://example.com/ref.png" for req in provider.requests)
    assert len({req.seed for req in provider.requests}) == 3

    refreshed_panel = (await db_session.execute(select(Panel).where(Panel.id == panel.id))).scalar_one()
    assert refreshed_panel.status == "completed"


@pytest.mark.asyncio
async def test_generate_candidates_should_append_new_candidates_and_auto_select_first_batch(
    db_session: AsyncSession,
    tmp_path: Path,
):
    fallback_reference = "https://example.com/scene-ref.png"
    panel = await _create_panel_fixture(
        db_session,
        tmp_path,
        duration_seconds=9.0,
        reference_image_url=fallback_reference,
    )
    provider = FakeVideoProvider()
    service = _build_service(tmp_path, provider)

    first_batch = await service.generate_candidates(panel, 2, db_session)
    second_batch = await service.generate_candidates(panel, 1, db_session)
    await db_session.commit()

    assert len(first_batch) == 4
    assert len(second_batch) == 2
    assert len(provider.requests) == 6
    assert all(req.reference_image_url == fallback_reference for req in provider.requests)
    assert len({req.seed for req in provider.requests}) == 6

    clips = (
        await db_session.execute(
            select(VideoClip)
            .where(VideoClip.panel_id == panel.id)
            .order_by(VideoClip.candidate_index, VideoClip.clip_order)
        )
    ).scalars().all()
    assert len(clips) == 6
    assert [clip.candidate_index for clip in clips] == [0, 0, 1, 1, 2, 2]
    assert [clip.clip_order for clip in clips] == [0, 1, 0, 1, 0, 1]
    assert all(clip.status == "completed" for clip in clips)
    assert all(clip.file_path and Path(clip.file_path).exists() for clip in clips)

    selected_pairs = [(clip.candidate_index, clip.clip_order) for clip in clips if clip.is_selected]
    assert selected_pairs == [(0, 0), (0, 1)]
