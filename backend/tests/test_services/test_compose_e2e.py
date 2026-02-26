"""端到端测试：复现合成流程中的 NoneType get_frame 错误。

用 mock 视频提供者生成真实视频文件，然后执行 VideoEditorService.compose 来验证完整合成流程。
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, Scene, VideoClip
from app.services.video_editor import CompositionOptions, VideoEditorService
from app.video_providers.mock_provider import MockVideoProvider


async def _create_test_project_with_videos(
    db_session: AsyncSession,
    tmp_path: Path,
    scene_count: int = 2,
    dialogue: str | None = "这是测试对白",
) -> str:
    """创建测试项目并为每个场景生成 mock 视频。"""
    project = Project(name="合成测试项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    mock_provider = MockVideoProvider(output_dir=str(tmp_path / "videos"))
    from app.video_providers.base import VideoGenerateRequest

    for i in range(scene_count):
        scene = Scene(
            project_id=project.id,
            sequence_order=i,
            title=f"场景{i + 1}",
            video_prompt=f"测试提示词 - 场景{i + 1}",
            dialogue=dialogue,
            duration_seconds=3.0,
            status="generated",
        )
        db_session.add(scene)
        await db_session.flush()

        request = VideoGenerateRequest(
            prompt=scene.video_prompt,
            duration_seconds=scene.duration_seconds,
            width=640,
            height=480,
        )
        task_id = await mock_provider.generate(request)
        status = await mock_provider.poll_status(task_id)

        clip = VideoClip(
            scene_id=scene.id,
            clip_order=0,
            file_path=status.result_url,
            duration_seconds=scene.duration_seconds,
            status="completed",
        )
        db_session.add(clip)

    await db_session.commit()
    return project.id


@pytest.mark.asyncio
async def test_compose_with_mock_videos(db_session: AsyncSession, tmp_path):
    """使用 mock 视频端到端测试合成流程。"""
    project_id = await _create_test_project_with_videos(db_session, tmp_path)
    editor = VideoEditorService()
    composition_id = await editor.compose(
        project_id,
        CompositionOptions(transition_type="none", include_subtitles=False, include_tts=False),
        db_session,
    )
    assert composition_id


@pytest.mark.asyncio
async def test_compose_with_subtitles(db_session: AsyncSession, tmp_path):
    """测试带字幕的合成流程。"""
    project_id = await _create_test_project_with_videos(db_session, tmp_path, scene_count=1)
    editor = VideoEditorService()
    composition_id = await editor.compose(
        project_id,
        CompositionOptions(transition_type="none", include_subtitles=True, include_tts=False),
        db_session,
    )
    assert composition_id


@pytest.mark.asyncio
async def test_compose_with_crossfade(db_session: AsyncSession, tmp_path):
    """测试 crossfade 转场的合成流程。"""
    project_id = await _create_test_project_with_videos(db_session, tmp_path)
    editor = VideoEditorService()
    composition_id = await editor.compose(
        project_id,
        CompositionOptions(
            transition_type="crossfade", transition_duration=0.5,
            include_subtitles=False, include_tts=False,
        ),
        db_session,
    )
    assert composition_id


@pytest.mark.asyncio
async def test_compose_with_simulated_tts(db_session: AsyncSession, tmp_path):
    """测试带模拟 TTS 音频的完整合成流程（最接近用户默认配置）。

    使用 moviepy 生成短的静音 MP3 文件来模拟 TTS 输出，
    验证音频合成路径不会导致 NoneType get_frame 错误。
    """
    from moviepy import AudioClip
    import numpy as np

    project_id = await _create_test_project_with_videos(
        db_session, tmp_path, dialogue="模拟 TTS 对白",
    )

    # 查询场景 ID，生成假 TTS 音频文件
    scenes = (await db_session.execute(
        select(Scene).where(Scene.project_id == project_id).order_by(Scene.sequence_order)
    )).scalars().all()

    tts_dir = tmp_path / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)

    def _silent_stereo(t):
        """静音立体声帧函数，需正确处理标量和数组输入。"""
        if isinstance(t, np.ndarray):
            return np.zeros((len(t), 2))
        return np.zeros(2)

    from app.services.tts_service import AudioResult
    fake_tts_map: dict[str, AudioResult] = {}
    for scene in scenes:
        # 生成 2 秒静音 MP3
        audio_path = tts_dir / f"{scene.id}.mp3"
        silent_audio = AudioClip(
            frame_function=_silent_stereo,
            duration=2.0,
            fps=44100,
        )
        silent_audio.write_audiofile(str(audio_path), logger=None)
        silent_audio.close()
        fake_tts_map[scene.id] = AudioResult(path=audio_path, text="模拟对白")

    # mock TTSService.generate_for_scenes 返回假 TTS 结果
    with patch.object(
        VideoEditorService, "_tts", create=True,
    ) as mock_tts_attr:
        mock_tts = AsyncMock()
        mock_tts.generate_for_scenes.return_value = fake_tts_map

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
async def test_compose_tts_longer_than_scene(db_session: AsyncSession, tmp_path):
    """测试 TTS 音频时长超过场景时长的情况（触发 subclipped 路径）。

    旧代码在 subclipped 后关闭原始 AudioFileClip，导致共享 reader 被置为 None，
    write_videofile 时触发 'NoneType' object has no attribute 'get_frame'。
    """
    from moviepy import AudioClip
    import numpy as np

    project_id = await _create_test_project_with_videos(
        db_session, tmp_path, dialogue="TTS 对白超长测试",
    )

    scenes = (await db_session.execute(
        select(Scene).where(Scene.project_id == project_id).order_by(Scene.sequence_order)
    )).scalars().all()

    tts_dir = tmp_path / "tts"
    tts_dir.mkdir(parents=True, exist_ok=True)

    def _silent_stereo(t):
        if isinstance(t, np.ndarray):
            return np.zeros((len(t), 2))
        return np.zeros(2)

    from app.services.tts_service import AudioResult
    fake_tts_map: dict[str, AudioResult] = {}
    for scene in scenes:
        # 生成 5 秒音频（场景时长 3 秒，触发 subclipped 截断）
        audio_path = tts_dir / f"{scene.id}.mp3"
        silent_audio = AudioClip(
            frame_function=_silent_stereo,
            duration=5.0,
            fps=44100,
        )
        silent_audio.write_audiofile(str(audio_path), logger=None)
        silent_audio.close()
        fake_tts_map[scene.id] = AudioResult(path=audio_path, text="超长对白")

    mock_tts = AsyncMock()
    mock_tts.generate_for_scenes.return_value = fake_tts_map

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
