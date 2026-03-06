from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Character, Project, Scene, SceneCharacter, VideoClip
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


async def _create_scene_fixture(
    db_session: AsyncSession,
    tmp_path: Path,
    *,
    duration_seconds: float,
    reference_image_url: str | None = "https://example.com/ref.png",
    scene_setting: str | None = None,
    with_old_clip: bool = False,
) -> Scene:
    project = Project(name="测试项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    character: Character | None = None
    if reference_image_url is not None:
        character = Character(
            project_id=project.id,
            name="主角",
            appearance="黑发",
            personality="冷静",
            costume="风衣",
            reference_image_url=reference_image_url,
        )
        db_session.add(character)
        await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="第一场",
        video_prompt="A cinematic scene with the lead character",
        duration_seconds=duration_seconds,
        status="pending",
        setting=scene_setting,
    )
    db_session.add(scene)
    await db_session.flush()

    if character is not None:
        db_session.add(SceneCharacter(scene_id=scene.id, character_id=character.id, action="走向镜头"))
    if with_old_clip:
        db_session.add(
            VideoClip(
                scene_id=scene.id,
                clip_order=0,
                file_path=str(tmp_path / "old.mp4"),
                status="completed",
            )
        )
    await db_session.commit()
    return scene


def _build_service(tmp_path: Path, provider: VideoProvider | None = None) -> VideoGeneratorService:
    return VideoGeneratorService(
        provider=provider or FakeVideoProvider(),
        output_dir=tmp_path,
        poll_interval_seconds=0.01,
        task_timeout_seconds=5.0,
    )


@pytest.mark.asyncio
async def test_generate_scene_should_clear_old_clips_and_keep_consistency_data(
    db_session: AsyncSession,
    tmp_path: Path,
):
    scene = await _create_scene_fixture(
        db_session,
        tmp_path,
        duration_seconds=12.0,
        with_old_clip=True,
    )
    provider = FakeVideoProvider()
    service = _build_service(tmp_path, provider)

    await service.generate_scene(scene, db_session)
    await db_session.commit()

    clips = (
        await db_session.execute(
            select(VideoClip).where(VideoClip.scene_id == scene.id).order_by(VideoClip.clip_order)
        )
    ).scalars().all()
    assert len(clips) == 3
    assert all(c.status == "completed" for c in clips)
    assert all(c.file_path and Path(c.file_path).exists() for c in clips)

    # 12 秒场景按 provider 最大 5 秒拆分后，应为 3 段。
    assert len(provider.requests) == 3
    assert all(req.reference_image_url == "https://example.com/ref.png" for req in provider.requests)
    assert len({req.seed for req in provider.requests}) == 3

    refreshed_scene = (await db_session.execute(select(Scene).where(Scene.id == scene.id))).scalar_one()
    assert refreshed_scene.status == "generated"


@pytest.mark.asyncio
async def test_generate_candidates_should_append_new_candidates_and_auto_select_first_batch(
    db_session: AsyncSession,
    tmp_path: Path,
):
    fallback_reference = "https://example.com/scene-ref.png"
    scene = await _create_scene_fixture(
        db_session,
        tmp_path,
        duration_seconds=9.0,
        reference_image_url=None,
        scene_setting=fallback_reference,
    )
    provider = FakeVideoProvider()
    service = _build_service(tmp_path, provider)

    first_batch = await service.generate_candidates(scene, 2, db_session)
    second_batch = await service.generate_candidates(scene, 1, db_session)
    await db_session.commit()

    assert len(first_batch) == 4
    assert len(second_batch) == 2
    assert len(provider.requests) == 6
    assert all(req.reference_image_url == fallback_reference for req in provider.requests)
    assert len({req.seed for req in provider.requests}) == 6

    clips = (
        await db_session.execute(
            select(VideoClip)
            .where(VideoClip.scene_id == scene.id)
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
