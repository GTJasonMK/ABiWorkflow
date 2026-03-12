from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import resolve_runtime_path, settings
from app.episode_status import EPISODE_STATUS_DRAFT
from app.models import Episode, Panel, Project, VideoClip
from app.panel_status import PANEL_STATUS_COMPLETED, PANEL_STATUS_FAILED, PANEL_STATUS_PENDING
from app.services.panel_generation import sync_panel_outputs_from_clips


@pytest.mark.asyncio
async def test_sync_panel_outputs_from_clips_should_update_video_url_and_completed_count(
    db_session: AsyncSession,
):
    project = Project(name="分镜输出同步项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(project_id=project.id, episode_order=0, title="第1集", status=EPISODE_STATUS_DRAFT)
    db_session.add(episode)
    await db_session.flush()

    panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="分镜一",
        visual_prompt="prompt-1",
        duration_seconds=5.0,
        status=PANEL_STATUS_PENDING,
    )
    db_session.add(panel)
    await db_session.flush()

    clip_path = resolve_runtime_path(settings.video_output_dir) / project.id / "panel-0.mp4"
    db_session.add(VideoClip(
        panel_id=panel.id,
        clip_order=0,
        candidate_index=0,
        is_selected=True,
        file_path=str(clip_path),
        status="completed",
    ))
    await db_session.commit()

    completed, failed = await sync_panel_outputs_from_clips(project.id, db_session)
    await db_session.commit()

    await db_session.refresh(panel)
    assert completed == 1
    assert failed == 0
    assert panel.status == PANEL_STATUS_COMPLETED
    assert panel.video_url == f"/media/videos/{project.id}/panel-0.mp4"
    assert panel.error_message is None


@pytest.mark.asyncio
async def test_sync_panel_outputs_from_clips_should_clear_stale_video_url_without_available_clip(
    db_session: AsyncSession,
):
    project = Project(name="分镜缺片段项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(project_id=project.id, episode_order=0, title="第1集", status=EPISODE_STATUS_DRAFT)
    db_session.add(episode)
    await db_session.flush()

    panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="孤立分镜",
        visual_prompt="prompt-mismatch",
        duration_seconds=5.0,
        status=PANEL_STATUS_COMPLETED,
        video_url="/media/videos/stale.mp4",
    )
    db_session.add(panel)
    await db_session.commit()

    completed, failed = await sync_panel_outputs_from_clips(project.id, db_session)
    await db_session.commit()

    await db_session.refresh(panel)
    assert completed == 0
    assert failed == 0
    assert panel.status == PANEL_STATUS_PENDING
    assert panel.video_url is None
    assert panel.error_message is None


@pytest.mark.asyncio
async def test_sync_panel_outputs_from_clips_should_prefer_selected_clip_and_sync_failed_error(
    db_session: AsyncSession,
):
    project = Project(name="分镜输出批量同步项目", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = Episode(project_id=project.id, episode_order=0, title="第1集", status=EPISODE_STATUS_DRAFT)
    db_session.add(episode)
    await db_session.flush()

    completed_panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=0,
        title="完成分镜",
        visual_prompt="prompt-ok",
        duration_seconds=5.0,
        status=PANEL_STATUS_PENDING,
    )
    failed_panel = Panel(
        project_id=project.id,
        episode_id=episode.id,
        panel_order=1,
        title="失败分镜",
        visual_prompt="prompt-failed",
        duration_seconds=5.0,
        status=PANEL_STATUS_PENDING,
    )
    db_session.add_all([completed_panel, failed_panel])
    await db_session.flush()

    project_dir = resolve_runtime_path(settings.video_output_dir) / project.id
    db_session.add_all([
        VideoClip(
            panel_id=completed_panel.id,
            clip_order=0,
            candidate_index=0,
            is_selected=False,
            file_path=str(project_dir / "fallback.mp4"),
            status="completed",
        ),
        VideoClip(
            panel_id=completed_panel.id,
            clip_order=1,
            candidate_index=0,
            is_selected=True,
            file_path=str(project_dir / "selected.mp4"),
            status="completed",
        ),
        VideoClip(
            panel_id=failed_panel.id,
            clip_order=0,
            candidate_index=0,
            is_selected=False,
            file_path=str(project_dir / "failed.mp4"),
            status="failed",
            error_message="provider failed",
        ),
    ])
    await db_session.commit()

    completed, failed = await sync_panel_outputs_from_clips(project.id, db_session)
    await db_session.commit()

    await db_session.refresh(completed_panel)
    await db_session.refresh(failed_panel)
    assert completed == 1
    assert failed == 1
    assert completed_panel.status == PANEL_STATUS_COMPLETED
    assert completed_panel.video_url == f"/media/videos/{project.id}/selected.mp4"
    assert failed_panel.status == PANEL_STATUS_FAILED
    assert failed_panel.video_url is None
    assert failed_panel.error_message == "provider failed"
