from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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
