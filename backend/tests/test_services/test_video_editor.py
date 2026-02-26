from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.video_editor as video_editor_module
from app.models import Project, Scene
from app.services.video_editor import CompositionOptions, VideoEditorService


@pytest.mark.asyncio
async def test_compose_should_fail_when_scene_has_no_clip(db_session: AsyncSession):
    project = Project(name="合成测试项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    db_session.add(Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="prompt-1",
        duration_seconds=5.0,
        status="generated",
    ))
    db_session.add(Scene(
        project_id=project.id,
        sequence_order=1,
        title="场景二",
        video_prompt="prompt-2",
        duration_seconds=5.0,
        status="generated",
    ))
    await db_session.commit()

    editor = VideoEditorService()

    with pytest.raises(ValueError, match="缺少可用视频片段"):
        await editor.compose(
            project.id,
            CompositionOptions(include_subtitles=False, include_tts=False),
            db_session,
        )


def test_resolve_media_path_should_prefer_runtime_path_when_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runtime_file = tmp_path / "runtime" / "outputs" / "videos" / "clip.mp4"
    runtime_file.parent.mkdir(parents=True, exist_ok=True)
    runtime_file.write_bytes(b"runtime")

    cwd_dir = tmp_path / "cwd"
    cwd_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(cwd_dir)
    monkeypatch.setattr(video_editor_module, "resolve_runtime_path", lambda _value: runtime_file)

    resolved = VideoEditorService._resolve_media_path("./outputs/videos/clip.mp4")
    assert resolved == runtime_file.resolve()


def test_resolve_media_path_should_fallback_to_cwd_when_runtime_path_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    runtime_file = tmp_path / "runtime-missing" / "outputs" / "videos" / "clip.mp4"

    cwd_dir = tmp_path / "cwd"
    cwd_file = cwd_dir / "outputs" / "videos" / "clip.mp4"
    cwd_file.parent.mkdir(parents=True, exist_ok=True)
    cwd_file.write_bytes(b"cwd")
    monkeypatch.chdir(cwd_dir)
    monkeypatch.setattr(video_editor_module, "resolve_runtime_path", lambda _value: runtime_file)

    resolved = VideoEditorService._resolve_media_path("./outputs/videos/clip.mp4")
    assert resolved == cwd_file.resolve()


def test_safe_crossfade_overlap_should_clamp_to_shorter_clip_duration():
    overlap = VideoEditorService._safe_crossfade_overlap(left_duration=2.0, right_duration=1.2, requested=3.0)
    assert overlap == pytest.approx(1.2)


def test_safe_crossfade_overlap_should_never_be_negative():
    overlap = VideoEditorService._safe_crossfade_overlap(left_duration=2.0, right_duration=2.0, requested=-1.0)
    assert overlap == pytest.approx(0.0)
