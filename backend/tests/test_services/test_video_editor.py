from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.services.video_editor_media as video_editor_media
from app.episode_status import EPISODE_STATUS_DRAFT
from app.models import Episode, Panel, Project
from app.panel_status import PANEL_STATUS_COMPLETED
from app.services.video_editor import CompositionOptions, VideoEditorService, load_panels_for_composition
from app.services.video_editor_types import TransitionType


async def _create_episode(
    db_session: AsyncSession,
    project: Project,
    *,
    episode_order: int = 0,
    title: str = "第1集",
) -> Episode:
    episode = Episode(
        project_id=project.id,
        episode_order=episode_order,
        title=title,
        summary=None,
        script_text=None,
        status=EPISODE_STATUS_DRAFT,
    )
    db_session.add(episode)
    await db_session.flush()
    return episode


@pytest.mark.asyncio
async def test_load_panels_for_composition_should_filter_by_episode(db_session: AsyncSession):
    project = Project(name="合成测试项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    first_episode = await _create_episode(db_session, project, episode_order=0, title="第1集")
    second_episode = await _create_episode(db_session, project, episode_order=1, title="第2集")

    db_session.add_all([
        Panel(
            project_id=project.id,
            episode_id=first_episode.id,
            panel_order=0,
            title="第一集分镜",
            duration_seconds=5.0,
            video_url="https://example.com/ep1.mp4",
            status=PANEL_STATUS_COMPLETED,
        ),
        Panel(
            project_id=project.id,
            episode_id=second_episode.id,
            panel_order=0,
            title="第二集分镜",
            duration_seconds=5.0,
            video_url="https://example.com/ep2.mp4",
            status=PANEL_STATUS_COMPLETED,
        ),
    ])
    await db_session.commit()

    panels = await load_panels_for_composition(project.id, db_session, episode_id=second_episode.id)
    assert [panel.title for panel in panels] == ["第二集分镜"]


@pytest.mark.asyncio
async def test_compose_should_fail_when_panel_has_no_video_source(db_session: AsyncSession):
    project = Project(name="合成测试项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = await _create_episode(db_session, project)
    db_session.add(
        Panel(
            project_id=project.id,
            episode_id=episode.id,
            panel_order=0,
            title="无视频分镜",
            script_text="这里只写了台词，没有视频",
            duration_seconds=5.0,
            status=PANEL_STATUS_COMPLETED,
        )
    )
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
    monkeypatch.setattr(video_editor_media, "resolve_runtime_path", lambda _value: runtime_file)

    resolved = video_editor_media.resolve_media_path("./outputs/videos/clip.mp4")
    assert resolved == runtime_file.resolve()


def test_resolve_media_path_should_fallback_to_cwd_when_runtime_path_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    runtime_file = tmp_path / "runtime-missing" / "outputs" / "videos" / "clip.mp4"

    cwd_dir = tmp_path / "cwd"
    cwd_file = cwd_dir / "outputs" / "videos" / "clip.mp4"
    cwd_file.parent.mkdir(parents=True, exist_ok=True)
    cwd_file.write_bytes(b"cwd")
    monkeypatch.chdir(cwd_dir)
    monkeypatch.setattr(video_editor_media, "resolve_runtime_path", lambda _value: runtime_file)

    resolved = video_editor_media.resolve_media_path("./outputs/videos/clip.mp4")
    assert resolved == cwd_file.resolve()


def test_resolve_transition_should_map_known_and_unknown_hints():
    assert video_editor_media.resolve_transition("fade_black", TransitionType.CROSSFADE) == TransitionType.FADE_BLACK
    assert video_editor_media.resolve_transition("cut", TransitionType.CROSSFADE) == TransitionType.NONE
    assert video_editor_media.resolve_transition("unexpected", TransitionType.CROSSFADE) == TransitionType.CROSSFADE
