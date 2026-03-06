"""端到端测试：验证当前 Panel 合成链路的稳定性。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.episode_status import EPISODE_STATUS_DRAFT
from app.models import Episode, Panel, Project
from app.panel_status import PANEL_STATUS_COMPLETED
from app.services.video_editor import CompositionOptions, VideoEditorService
from app.video_providers.base import VideoGenerateRequest
from app.video_providers.mock_provider import MockVideoProvider


async def _create_test_project_with_videos(
    db_session: AsyncSession,
    tmp_path: Path,
    panel_count: int = 2,
    dialogue: str | None = "这是测试对白",
) -> str:
    """创建测试项目，并为每个分镜准备真实的 mock 视频文件。"""
    project = Project(name="合成测试项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(
        project_id=project.id,
        episode_order=0,
        title="第1集",
        summary=None,
        script_text=None,
        status=EPISODE_STATUS_DRAFT,
    )
    db_session.add(episode)
    await db_session.flush()

    mock_provider = MockVideoProvider(output_dir=str(tmp_path / "videos"))

    for index in range(panel_count):
        request = VideoGenerateRequest(
            prompt=f"测试提示词 - 分镜{index + 1}",
            duration_seconds=3.0,
            width=640,
            height=480,
        )
        task_id = await mock_provider.generate(request)
        status = await mock_provider.poll_status(task_id)

        panel = Panel(
            project_id=project.id,
            episode_id=episode.id,
            panel_order=index,
            title=f"分镜{index + 1}",
            script_text=dialogue,
            visual_prompt=request.prompt,
            duration_seconds=request.duration_seconds,
            tts_text=dialogue,
            video_url=status.result_url,
            status=PANEL_STATUS_COMPLETED,
        )
        db_session.add(panel)

    await db_session.commit()
    return project.id


async def _list_project_panels(db_session: AsyncSession, project_id: str) -> list[Panel]:
    return (
        await db_session.execute(
            select(Panel)
            .where(Panel.project_id == project_id)
            .order_by(Panel.panel_order)
        )
    ).scalars().all()


@pytest.mark.asyncio
async def test_compose_with_mock_videos(db_session: AsyncSession, tmp_path: Path):
    project_id = await _create_test_project_with_videos(db_session, tmp_path)
    editor = VideoEditorService()
    composition_id = await editor.compose(
        project_id,
        CompositionOptions(transition_type="none", include_subtitles=False, include_tts=False),
        db_session,
    )
    assert composition_id


@pytest.mark.asyncio
async def test_compose_with_subtitles(db_session: AsyncSession, tmp_path: Path):
    project_id = await _create_test_project_with_videos(db_session, tmp_path, panel_count=1)
    editor = VideoEditorService()
    composition_id = await editor.compose(
        project_id,
        CompositionOptions(transition_type="none", include_subtitles=True, include_tts=False),
        db_session,
    )
    assert composition_id


@pytest.mark.asyncio
async def test_compose_with_crossfade(db_session: AsyncSession, tmp_path: Path):
    project_id = await _create_test_project_with_videos(db_session, tmp_path)
    editor = VideoEditorService()
    composition_id = await editor.compose(
        project_id,
        CompositionOptions(
            transition_type="crossfade",
            transition_duration=0.5,
            include_subtitles=False,
            include_tts=False,
        ),
        db_session,
    )
    assert composition_id


@pytest.mark.asyncio
async def test_compose_with_simulated_tts(db_session: AsyncSession, tmp_path: Path):
    import numpy as np
    from moviepy import AudioClip

    project_id = await _create_test_project_with_videos(
        db_session,
        tmp_path,
        dialogue="模拟 TTS 对白",
    )
    panels = await _list_project_panels(db_session, project_id)

    tts_dir = tmp_path / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)

    def _silent_stereo(t):
        if isinstance(t, np.ndarray):
            return np.zeros((len(t), 2))
        return np.zeros(2)

    from app.services.tts_service import AudioResult

    fake_tts_map: dict[str, AudioResult] = {}
    for panel in panels:
        audio_path = tts_dir / f"{panel.id}.mp3"
        silent_audio = AudioClip(
            frame_function=_silent_stereo,
            duration=2.0,
            fps=44100,
        )
        silent_audio.write_audiofile(str(audio_path), logger=None)
        silent_audio.close()
        fake_tts_map[panel.id] = AudioResult(path=audio_path, text="模拟对白")

    mock_tts = AsyncMock()
    mock_tts.generate_for_panels.return_value = fake_tts_map

    editor = VideoEditorService()
    editor._tts = mock_tts

    composition_id = await editor.compose(
        project_id,
        CompositionOptions(
            transition_type="crossfade",
            transition_duration=0.5,
            include_subtitles=True,
            include_tts=True,
        ),
        db_session,
    )
    assert composition_id


@pytest.mark.asyncio
async def test_compose_tts_longer_than_scene(db_session: AsyncSession, tmp_path: Path):
    import numpy as np
    from moviepy import AudioClip

    project_id = await _create_test_project_with_videos(
        db_session,
        tmp_path,
        dialogue="TTS 对白超长测试",
    )
    panels = await _list_project_panels(db_session, project_id)

    tts_dir = tmp_path / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)

    def _silent_stereo(t):
        if isinstance(t, np.ndarray):
            return np.zeros((len(t), 2))
        return np.zeros(2)

    from app.services.tts_service import AudioResult

    fake_tts_map: dict[str, AudioResult] = {}
    for panel in panels:
        audio_path = tts_dir / f"{panel.id}.mp3"
        silent_audio = AudioClip(
            frame_function=_silent_stereo,
            duration=5.0,
            fps=44100,
        )
        silent_audio.write_audiofile(str(audio_path), logger=None)
        silent_audio.close()
        fake_tts_map[panel.id] = AudioResult(path=audio_path, text="超长对白")

    mock_tts = AsyncMock()
    mock_tts.generate_for_panels.return_value = fake_tts_map

    editor = VideoEditorService()
    editor._tts = mock_tts

    composition_id = await editor.compose(
        project_id,
        CompositionOptions(
            transition_type="none",
            transition_duration=0,
            include_subtitles=True,
            include_tts=True,
        ),
        db_session,
    )
    assert composition_id
