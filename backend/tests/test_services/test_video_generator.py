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


@pytest.mark.asyncio
async def test_generate_scene_should_clear_old_clips_and_keep_consistency_data(
    db_session: AsyncSession,
    tmp_path: Path,
):
    project = Project(name="测试项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    character = Character(
        project_id=project.id,
        name="主角",
        appearance="黑发",
        personality="冷静",
        costume="风衣",
        reference_image_url="https://example.com/ref.png",
    )
    db_session.add(character)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="第一场",
        video_prompt="A cinematic scene with the lead character",
        duration_seconds=12.0,
        status="pending",
    )
    db_session.add(scene)
    await db_session.flush()

    db_session.add(SceneCharacter(scene_id=scene.id, character_id=character.id, action="走向镜头"))
    db_session.add(VideoClip(scene_id=scene.id, clip_order=0, file_path=str(tmp_path / "old.mp4"), status="completed"))
    await db_session.commit()

    provider = FakeVideoProvider()
    service = VideoGeneratorService(
        provider=provider,
        output_dir=tmp_path,
        poll_interval_seconds=0.01,
        task_timeout_seconds=5.0,
    )

    await service.generate_scene(scene, db_session)
    await db_session.commit()

    clips = (await db_session.execute(
        select(VideoClip).where(VideoClip.scene_id == scene.id).order_by(VideoClip.clip_order)
    )).scalars().all()
    assert len(clips) == 3
    assert all(c.status == "completed" for c in clips)
    assert all(c.file_path and Path(c.file_path).exists() for c in clips)

    # 12 秒场景按 provider 最大 5 秒拆分后，应为 3 段。
    assert len(provider.requests) == 3
    assert all(req.reference_image_url == "https://example.com/ref.png" for req in provider.requests)
    assert len({req.seed for req in provider.requests}) == 3

    refreshed_scene = (await db_session.execute(select(Scene).where(Scene.id == scene.id))).scalar_one()
    assert refreshed_scene.status == "generated"
