from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Character, CompositionTask, Panel, Project, VideoClip
from tests.test_api._workflow_test_utils import build_episode, build_panel


def build_completed_clip(panel: Panel, *, clip_order: int = 0) -> VideoClip:
    return VideoClip(
        panel_id=panel.id,
        clip_order=clip_order,
        candidate_index=0,
        is_selected=True,
        file_path=f"./outputs/videos/{panel.id}_{clip_order}.mp4",
        status="completed",
        duration_seconds=panel.duration_seconds,
    )


@pytest.mark.asyncio
async def test_abort_project_task_should_restore_to_parsed_when_only_characters_exist(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="中止恢复测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    db_session.add(Character(
        project_id=project.id,
        name="主角",
        appearance="短发",
        personality="冷静",
        costume="风衣",
    ))
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/abort")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["aborted"] is True
    assert payload["status"] == "parsed"

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_parse_should_reject_when_project_is_generating(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="解析门禁测试", status="generating", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/parse")
    assert response.status_code == 409
    assert "不允许解析剧本" in response.json()["detail"]


@pytest.mark.asyncio
async def test_parse_sync_should_restore_previous_status_when_parse_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakeLLM:
        async def close(self) -> None:
            return None

    async def fake_parse_project_from_episodes(project_id: str, script_text: str, llm, db: AsyncSession):  # noqa: ANN001
        raise RuntimeError("sync parse failed")

    monkeypatch.setattr("app.llm.factory.create_llm_adapter", lambda: _FakeLLM())
    monkeypatch.setattr(
        "app.api.projects_workflow.parse_project_from_episodes",
        fake_parse_project_from_episodes,
    )

    project = Project(name="解析同步失败回滚测试", status="parsed", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/parse")
    assert response.status_code == 500
    assert "剧本解析失败" in response.json()["detail"]

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_generate_should_reject_when_project_is_generating(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="生成门禁测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    db_session.add(build_panel(
        project.id,
        episode.id,
        title="分镜一",
        visual_prompt="A cinematic opening shot",
        duration_seconds=5.0,
        status="pending",
    ))
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 409
    assert "不允许启动生成" in response.json()["detail"]


@pytest.mark.asyncio
async def test_generate_should_recover_draft_project_when_all_panels_are_already_ready(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="草稿状态生成门禁测试", status="draft")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="历史已完成分镜",
        visual_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(panel)
    await db_session.flush()
    db_session.add(build_completed_clip(panel))
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_panels"] == 1
    assert payload["completed"] == 1
    assert payload["failed"] == 0

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_generate_should_only_validate_prompts_for_pending_or_failed_panels(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_all(self, project_id: str, db: AsyncSession, *, panel_ids=None):  # noqa: ANN001
        stmt = select(Panel).where(Panel.project_id == project_id)
        if panel_ids:
            stmt = stmt.where(Panel.id.in_(list(panel_ids)))
        panels = (await db.execute(stmt)).scalars().all()
        for panel in panels:
            if panel.status in {"pending", "failed", "processing", "draft"}:
                panel.status = "completed"
                db.add(build_completed_clip(panel))
        await db.flush()

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="提示词校验范围测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    ready_panel_without_prompt = build_panel(
        project.id,
        episode.id,
        order=0,
        title="已完成但无提示词分镜",
        visual_prompt=None,
        duration_seconds=5.0,
        status="completed",
    )
    pending_panel = build_panel(
        project.id,
        episode.id,
        order=1,
        title="待生成分镜",
        visual_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add_all([ready_panel_without_prompt, pending_panel])
    await db_session.flush()
    db_session.add(build_completed_clip(ready_panel_without_prompt))
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_panels"] == 2
    assert payload["completed"] == 2
    assert payload["failed"] == 0


@pytest.mark.asyncio
async def test_generate_should_treat_completed_panel_status_as_ready(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_all(self, project_id: str, db: AsyncSession, *, panel_ids=None):  # noqa: ANN001
        return None

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="已完成场景生成测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="已完成分镜",
        visual_prompt="completed prompt",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(panel)
    await db_session.flush()
    db_session.add(build_completed_clip(panel))
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_panels"] == 1
    assert payload["completed"] == 1
    assert payload["failed"] == 0

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_compose_should_reject_when_project_is_composing(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="合成门禁测试", status="composing")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    db_session.add(build_panel(
        project.id,
        episode.id,
        title="分镜一",
        visual_prompt="A cinematic ending shot",
        duration_seconds=5.0,
        status="completed",
    ))
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/compose",
        json={"include_subtitles": False, "include_tts": False},
    )
    assert response.status_code == 409
    assert "不允许启动合成" in response.json()["detail"]


@pytest.mark.asyncio
async def test_compose_should_accept_completed_panel_status(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_compose(self, project_id: str, options, db: AsyncSession, episode_id: str | None = None):  # noqa: ANN001
        return "completed-panel-comp-id"

    monkeypatch.setattr("app.api.composition.VideoEditorService.compose", fake_compose)

    project = Project(name="已完成场景状态合成测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    db_session.add(build_panel(
        project.id,
        episode.id,
        title="已完成分镜",
        visual_prompt="completed prompt",
        duration_seconds=5.0,
        status="completed",
    ))
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/compose",
        json={"include_subtitles": False, "include_tts": False},
    )
    assert response.status_code == 200
    assert response.json()["data"]["composition_id"] == "completed-panel-comp-id"


@pytest.mark.asyncio
async def test_compose_should_mark_previous_compositions_stale(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    new_composition_id = "11111111-1111-1111-1111-111111111111"

    async def fake_compose(self, project_id: str, options, db: AsyncSession, episode_id: str | None = None):  # noqa: ANN001
        db.add(CompositionTask(
            id=new_composition_id,
            project_id=project_id,
            output_path="./outputs/compositions/new.mp4",
            duration_seconds=5.0,
            status="completed",
        ))
        await db.flush()
        return new_composition_id

    monkeypatch.setattr("app.api.composition.VideoEditorService.compose", fake_compose)

    project = Project(name="多次合成状态收敛测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    db_session.add(build_panel(
        project.id,
        episode.id,
        title="分镜一",
        visual_prompt="prompt",
        duration_seconds=5.0,
        status="completed",
    ))
    previous_task = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/old.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(previous_task)
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/compose",
        json={"include_subtitles": False, "include_tts": False},
    )
    assert response.status_code == 200
    assert response.json()["data"]["composition_id"] == new_composition_id

    await db_session.refresh(previous_task)
    new_task = (await db_session.execute(
        select(CompositionTask).where(CompositionTask.id == new_composition_id)
    )).scalar_one()

    assert previous_task.status == "stale"
    assert new_task.status == "completed"


@pytest.mark.asyncio
async def test_compose_should_validate_transition_duration(
    client: AsyncClient,
):
    create_resp = await client.post("/api/projects", json={"name": "参数校验项目"})
    project_id = create_resp.json()["data"]["id"]

    response = await client.post(
        f"/api/projects/{project_id}/compose",
        json={"transition_duration": -1.0},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_panel_should_invalidate_outputs_when_generation_fields_changed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜更新失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜一",
        visual_prompt="old prompt",
        status="completed",
        video_url="/media/videos/old.mp4",
    )
    panel.video_provider_task_id = "video-task-stale-1"
    panel.lipsync_provider_task_id = "lipsync-task-stale-1"
    panel.tts_provider_task_id = "tts-task-keep-1"
    db_session.add(panel)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/old.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.put(
        f"/api/panels/{panel.id}",
        json={
            "visual_prompt": "new prompt",
            "duration_seconds": 8.0,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"
    assert response.json()["data"]["video_url"] is None
    assert response.json()["data"]["video_provider_task_id"] is None
    assert response.json()["data"]["lipsync_provider_task_id"] is None
    assert response.json()["data"]["tts_provider_task_id"] == "tts-task-keep-1"

    _project_id = project.id
    _panel_id = panel.id
    _composition_id = composition.id
    db_session.expire_all()

    updated_project = (await db_session.execute(
        select(Project).where(Project.id == _project_id)
    )).scalar_one()
    updated_panel = (await db_session.execute(
        select(Panel).where(Panel.id == _panel_id)
    )).scalar_one()
    updated_composition = (await db_session.execute(
        select(CompositionTask).where(CompositionTask.id == _composition_id)
    )).scalar_one()
    assert updated_project.status == "parsed"
    assert updated_panel.video_provider_task_id is None
    assert updated_panel.lipsync_provider_task_id is None
    assert updated_panel.tts_provider_task_id == "tts-task-keep-1"
    assert updated_composition.status == "stale"


@pytest.mark.asyncio
async def test_update_panel_should_only_invalidate_same_episode_compositions(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜分集级失效范围测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode_a = build_episode(project.id, order=0, title="第1集")
    episode_b = build_episode(project.id, order=1, title="第2集")
    db_session.add_all([episode_a, episode_b])
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode_a.id,
        title="分镜一",
        visual_prompt="old prompt",
        status="completed",
        video_url="/media/videos/episode-a.mp4",
    )
    db_session.add(panel)
    episode_b_panel = build_panel(
        project.id,
        episode_b.id,
        order=0,
        title="分镜二",
        visual_prompt="stable prompt",
        status="completed",
        video_url="/media/videos/episode-b.mp4",
    )
    db_session.add(episode_b_panel)

    project_composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/project.mp4",
        duration_seconds=10.0,
        status="completed",
    )
    episode_a_composition = CompositionTask(
        project_id=project.id,
        episode_id=episode_a.id,
        output_path="./outputs/compositions/episode-a.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    episode_b_composition = CompositionTask(
        project_id=project.id,
        episode_id=episode_b.id,
        output_path="./outputs/compositions/episode-b.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add_all([project_composition, episode_a_composition, episode_b_composition])
    await db_session.commit()

    response = await client.put(
        f"/api/panels/{panel.id}",
        json={"visual_prompt": "new prompt"},
    )
    assert response.status_code == 200

    await db_session.refresh(project_composition)
    await db_session.refresh(episode_a_composition)
    await db_session.refresh(episode_b_composition)
    assert project_composition.status == "stale"
    assert episode_a_composition.status == "stale"
    assert episode_b_composition.status == "completed"


@pytest.mark.asyncio
async def test_update_panel_should_invalidate_voice_outputs_when_voice_inputs_changed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜语音输入失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜语音失效",
        visual_prompt="stable prompt",
        status="completed",
        video_url="/media/videos/stable.mp4",
    )
    panel.tts_text = "旧台词"
    panel.tts_audio_url = "/media/audio/stale.mp3"
    panel.tts_provider_task_id = "tts-task-stale-1"
    panel.lipsync_video_url = "/media/videos/lipsync-stale.mp4"
    panel.lipsync_provider_task_id = "lipsync-task-stale-1"
    db_session.add(panel)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/stable.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.put(
        f"/api/panels/{panel.id}",
        json={"tts_text": "新台词"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "completed"
    assert data["video_url"] == "/media/videos/stable.mp4"
    assert data["tts_audio_url"] is None
    assert data["tts_provider_task_id"] is None
    assert data["lipsync_video_url"] is None
    assert data["lipsync_provider_task_id"] is None

    _project_id = project.id
    _panel_id = panel.id
    _composition_id = composition.id
    db_session.expire_all()

    updated_project = (await db_session.execute(
        select(Project).where(Project.id == _project_id)
    )).scalar_one()
    updated_panel = (await db_session.execute(
        select(Panel).where(Panel.id == _panel_id)
    )).scalar_one()
    updated_composition = (await db_session.execute(
        select(CompositionTask).where(CompositionTask.id == _composition_id)
    )).scalar_one()
    assert updated_project.status == "parsed"
    assert updated_panel.video_url == "/media/videos/stable.mp4"
    assert updated_panel.tts_audio_url is None
    assert updated_panel.tts_provider_task_id is None
    assert updated_panel.lipsync_video_url is None
    assert updated_panel.lipsync_provider_task_id is None
    assert updated_composition.status == "stale"


@pytest.mark.asyncio
async def test_update_panel_should_not_invalidate_outputs_when_only_non_generation_fields_changed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜非生成字段更新测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜一",
        visual_prompt="stable prompt",
        status="completed",
        video_url="/media/videos/stable.mp4",
    )
    db_session.add(panel)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/stable.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.put(
        f"/api/panels/{panel.id}",
        json={
            "tts_audio_url": "https://example.com/audio/stable.mp3",
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"
    assert response.json()["data"]["video_url"] == "/media/videos/stable.mp4"

    await db_session.refresh(project)
    await db_session.refresh(composition)
    assert project.status == "completed"
    assert composition.status == "completed"


@pytest.mark.asyncio
async def test_update_panel_should_reject_when_project_is_generating(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜编辑门禁测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(project.id, episode.id, title="分镜一", visual_prompt="prompt", status="pending")
    db_session.add(panel)
    await db_session.commit()

    response = await client.put(
        f"/api/panels/{panel.id}",
        json={"visual_prompt": "new prompt"},
    )
    assert response.status_code == 409
    assert "不允许编辑分镜" in response.json()["detail"]


@pytest.mark.asyncio
async def test_retry_panel_should_keep_project_parsed_when_other_panels_are_pending(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_panel(self, panel: Panel, db: AsyncSession):  # noqa: ANN001
        panel.status = "completed"
        clip = build_completed_clip(panel)
        db.add(clip)
        await db.flush()
        return [clip]

    monkeypatch.setattr("app.api.generation.get_provider", lambda: object())
    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_panel", fake_generate_panel)

    project = Project(name="单分镜重试状态测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    retry_panel = build_panel(
        project.id,
        episode.id,
        order=0,
        title="待重试分镜",
        visual_prompt="retry prompt",
        status="failed",
    )
    pending_panel = build_panel(
        project.id,
        episode.id,
        order=1,
        title="其他待生成分镜",
        visual_prompt="pending prompt",
        status="pending",
    )
    db_session.add_all([retry_panel, pending_panel])
    await db_session.commit()

    response = await client.post(f"/api/panels/{retry_panel.id}/retry")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_retry_panel_should_preserve_completed_project_when_retry_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_panel(self, panel: Panel, db: AsyncSession):  # noqa: ANN001
        raise RuntimeError("mock generation failure")

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_panel", fake_generate_panel)

    project = Project(name="已完成项目重试失败测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="失败分镜",
        visual_prompt="retry prompt",
        status="failed",
    )
    db_session.add(panel)
    await db_session.commit()

    response = await client.post(f"/api/panels/{panel.id}/retry")
    assert response.status_code == 500
    assert "分镜重试失败" in response.json()["detail"]

    await db_session.refresh(project)
    assert project.status == "completed"


@pytest.mark.asyncio
async def test_retry_panel_should_mark_previous_compositions_stale_on_success(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_panel(self, panel: Panel, db: AsyncSession):  # noqa: ANN001
        panel.status = "completed"
        clip = build_completed_clip(panel)
        db.add(clip)
        await db.flush()
        return [clip]

    monkeypatch.setattr("app.api.generation.get_provider", lambda: object())
    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_panel", fake_generate_panel)

    project = Project(name="重试成片失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="需重试分镜",
        visual_prompt="retry prompt",
        status="completed",
        video_url="/media/videos/current.mp4",
    )
    db_session.add(panel)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/current.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.post(f"/api/panels/{panel.id}/retry")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "completed"

    await db_session.refresh(project)
    await db_session.refresh(composition)
    assert project.status == "parsed"
    assert composition.status == "stale"


@pytest.mark.asyncio
async def test_retry_panel_should_mark_previous_compositions_stale_when_retry_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_panel(self, panel: Panel, db: AsyncSession):  # noqa: ANN001
        raise RuntimeError("mock generation failure")

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_panel", fake_generate_panel)

    project = Project(name="重试失败成片失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="失败分镜",
        visual_prompt="retry prompt",
        status="failed",
    )
    db_session.add(panel)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/current.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.post(f"/api/panels/{panel.id}/retry")
    assert response.status_code == 500
    assert "分镜重试失败" in response.json()["detail"]

    await db_session.refresh(project)
    await db_session.refresh(composition)
    assert project.status == "completed"
    assert composition.status == "stale"


@pytest.mark.asyncio
async def test_retry_panel_should_keep_completed_panel_status_when_post_process_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_panel(self, panel: Panel, db: AsyncSession):  # noqa: ANN001
        panel.status = "completed"
        await db.flush()
        raise RuntimeError("post process failed")

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_panel", fake_generate_panel)

    project = Project(name="重试完成状态保护测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="历史状态分镜",
        visual_prompt="retry prompt",
        status="failed",
    )
    db_session.add(panel)
    await db_session.commit()

    response = await client.post(f"/api/panels/{panel.id}/retry")
    assert response.status_code == 500
    assert "分镜重试失败" in response.json()["detail"]

    await db_session.refresh(panel)
    assert panel.status == "completed"


@pytest.mark.asyncio
async def test_retry_panel_should_keep_failed_panel_status_when_provider_init_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_get_provider():  # noqa: ANN202
        raise RuntimeError("provider not configured")

    monkeypatch.setattr("app.api.generation.get_provider", fake_get_provider)

    project = Project(name="重试初始化失败测试", status="failed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="失败分镜",
        visual_prompt="retry prompt",
        status="failed",
    )
    db_session.add(panel)
    await db_session.commit()

    response = await client.post(f"/api/panels/{panel.id}/retry")
    assert response.status_code == 500
    assert "分镜重试失败" in response.json()["detail"]

    await db_session.refresh(panel)
    assert panel.status == "failed"


@pytest.mark.asyncio
async def test_retry_panel_should_restore_ready_panel_when_provider_init_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    def fake_get_provider():  # noqa: ANN202
        raise RuntimeError("provider not configured")

    monkeypatch.setattr("app.api.generation.get_provider", fake_get_provider)

    project = Project(name="重试初始化失败回滚测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="已完成分镜",
        visual_prompt="retry prompt",
        status="completed",
        video_url="/media/videos/current.mp4",
    )
    db_session.add(panel)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/current.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.post(f"/api/panels/{panel.id}/retry")
    assert response.status_code == 500
    assert "分镜重试失败" in response.json()["detail"]

    await db_session.refresh(project)
    await db_session.refresh(panel)
    await db_session.refresh(composition)
    assert project.status == "completed"
    assert panel.status == "completed"
    assert composition.status == "completed"


@pytest.mark.asyncio
async def test_delete_panel_should_reject_when_project_is_generating(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="删除门禁测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(project.id, episode.id, title="分镜一", visual_prompt="prompt", status="pending")
    db_session.add(panel)
    await db_session.commit()

    response = await client.delete(f"/api/panels/{panel.id}")
    assert response.status_code == 409
    assert "不允许删除分镜" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reorder_panels_should_reject_when_project_is_composing(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="排序门禁测试", status="composing")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(project.id, episode.id, title="分镜一", visual_prompt="prompt", status="completed")
    db_session.add(panel)
    await db_session.commit()

    response = await client.put(
        f"/api/episodes/{episode.id}/panels/reorder",
        json={"panel_ids": [panel.id]},
    )
    assert response.status_code == 409
    assert "不允许排序分镜" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reorder_panels_should_not_downgrade_when_order_unchanged(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="排序无变更测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel_a = build_panel(
        project.id,
        episode.id,
        order=0,
        title="分镜一",
        visual_prompt="prompt-a",
        status="completed",
    )
    panel_b = build_panel(
        project.id,
        episode.id,
        order=1,
        title="分镜二",
        visual_prompt="prompt-b",
        status="completed",
    )
    db_session.add_all([panel_a, panel_b])
    await db_session.flush()

    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/current.mp4",
        duration_seconds=10.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.put(
        f"/api/episodes/{episode.id}/panels/reorder",
        json={"panel_ids": [panel_a.id, panel_b.id]},
    )
    assert response.status_code == 200

    await db_session.refresh(project)
    await db_session.refresh(composition)
    assert project.status == "completed"
    assert composition.status == "completed"


@pytest.mark.asyncio
async def test_update_character_reference_image_should_invalidate_project_panel_generation(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="角色参考图失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    character = Character(
        project_id=project.id,
        name="主角",
        appearance="黑发",
        personality="冷静",
        costume="风衣",
        reference_image_url="https://example.com/old.png",
    )
    db_session.add(character)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜一",
        visual_prompt="A cinematic portrait shot",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(panel)
    await db_session.flush()

    db_session.add(build_completed_clip(panel))
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/old.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.put(
        f"/api/characters/{character.id}",
        json={"reference_image_url": "https://example.com/new.png"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["reference_image_url"] == "https://example.com/new.png"

    await db_session.refresh(project)
    await db_session.refresh(panel)
    await db_session.refresh(composition)
    clips = (await db_session.execute(select(VideoClip).where(VideoClip.panel_id == panel.id))).scalars().all()

    assert project.status == "parsed"
    assert panel.status == "pending"
    assert composition.status == "stale"
    assert clips == []


@pytest.mark.asyncio
async def test_update_character_reference_image_should_invalidate_project_outputs_even_without_explicit_binding(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="未引用角色更新测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    character = Character(
        project_id=project.id,
        name="旁白角色",
        reference_image_url="https://example.com/old-unused.png",
    )
    db_session.add(character)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()

    panel = build_panel(
        project.id,
        episode.id,
        title="分镜一",
        visual_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(panel)
    await db_session.flush()
    db_session.add(build_completed_clip(panel))

    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/current.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.put(
        f"/api/characters/{character.id}",
        json={"reference_image_url": "https://example.com/new-unused.png"},
    )
    assert response.status_code == 200

    await db_session.refresh(project)
    await db_session.refresh(panel)
    await db_session.refresh(composition)
    clips = (await db_session.execute(select(VideoClip).where(VideoClip.panel_id == panel.id))).scalars().all()
    assert project.status == "parsed"
    assert panel.status == "pending"
    assert composition.status == "stale"
    assert clips == []


@pytest.mark.asyncio
async def test_reorder_panels_should_return_404_when_episode_not_found(
    client: AsyncClient,
):
    response = await client.put(
        "/api/episodes/non-existent-episode/panels/reorder",
        json={"panel_ids": ["panel-1"]},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "分集不存在"


@pytest.mark.asyncio
async def test_reorder_panels_should_require_full_panel_id_set(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="排序完整性测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel_a = build_panel(project.id, episode.id, order=0, title="分镜A", visual_prompt="prompt A", status="pending")
    panel_b = build_panel(project.id, episode.id, order=1, title="分镜B", visual_prompt="prompt B", status="pending")
    db_session.add_all([panel_a, panel_b])
    await db_session.commit()

    response = await client.put(
        f"/api/episodes/{episode.id}/panels/reorder",
        json={"panel_ids": [panel_a.id]},
    )
    assert response.status_code == 400
    assert "panel_ids 必须完整覆盖当前分集分镜" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_panel_should_compact_panel_order_after_delete(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="删除后重排测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel_a = build_panel(project.id, episode.id, order=0, title="分镜A", visual_prompt="prompt A", status="pending")
    panel_b = build_panel(project.id, episode.id, order=1, title="分镜B", visual_prompt="prompt B", status="pending")
    panel_c = build_panel(project.id, episode.id, order=2, title="分镜C", visual_prompt="prompt C", status="pending")
    db_session.add_all([panel_a, panel_b, panel_c])
    await db_session.commit()

    response = await client.delete(f"/api/panels/{panel_b.id}")
    assert response.status_code == 200

    # API 在独立会话中完成了删除和 panel_order 压缩，需过期本会话缓存。
    # 先保存 ID，因为 expire_all() 后访问 ORM 属性会触发同步懒加载，在 aiosqlite 中不可行。
    _episode_id = episode.id
    db_session.expire_all()

    remaining = (await db_session.execute(
        select(Panel).where(Panel.episode_id == _episode_id).order_by(Panel.panel_order)
    )).scalars().all()
    assert [item.title for item in remaining] == ["分镜A", "分镜C"]
    assert [item.panel_order for item in remaining] == [0, 1]


@pytest.mark.asyncio
async def test_generate_should_keep_completed_status_when_nothing_to_regenerate(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="已完成项目空生成测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="已完成分镜",
        visual_prompt="prompt",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(panel)
    await db_session.flush()
    db_session.add(build_completed_clip(panel))
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    assert response.json()["data"]["completed"] == 1
    assert response.json()["data"]["failed"] == 0

    await db_session.refresh(project)
    assert project.status == "completed"


@pytest.mark.asyncio
async def test_generate_should_recover_failed_project_when_all_panels_are_already_ready(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="失败状态直返恢复测试", status="failed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="已完成分镜",
        visual_prompt="prompt",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(panel)
    await db_session.flush()
    db_session.add(build_completed_clip(panel))
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    assert response.json()["data"]["completed"] == 1
    assert response.json()["data"]["failed"] == 0

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_generate_should_recover_generating_project_when_all_panels_are_already_ready(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="生成卡状态直返恢复测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(
        project.id,
        episode.id,
        title="已完成分镜",
        visual_prompt="prompt",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(panel)
    await db_session.flush()
    db_session.add(build_completed_clip(panel))
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    assert response.json()["data"]["completed"] == 1
    assert response.json()["data"]["failed"] == 0

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_generate_should_mark_previous_compositions_stale_when_regenerating(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_all(self, project_id: str, db: AsyncSession, *, panel_ids=None):  # noqa: ANN001
        stmt = select(Panel).where(Panel.project_id == project_id)
        if panel_ids:
            stmt = stmt.where(Panel.id.in_(list(panel_ids)))
        panels = (await db.execute(stmt)).scalars().all()
        for panel in panels:
            if panel.status in {"pending", "failed", "processing", "draft"}:
                panel.status = "completed"
                db.add(build_completed_clip(panel))
        await db.flush()

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="重生成成片失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    ready_panel = build_panel(
        project.id,
        episode.id,
        order=0,
        title="已完成分镜",
        visual_prompt="prompt-ready",
        duration_seconds=5.0,
        status="completed",
    )
    failed_panel = build_panel(
        project.id,
        episode.id,
        order=1,
        title="失败分镜",
        visual_prompt="prompt-failed",
        duration_seconds=5.0,
        status="failed",
    )
    db_session.add_all([ready_panel, failed_panel])
    await db_session.flush()
    db_session.add(build_completed_clip(ready_panel))
    previous_composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/old.mp4",
        duration_seconds=10.0,
        status="completed",
    )
    db_session.add(previous_composition)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    assert response.json()["data"]["completed"] == 2
    assert response.json()["data"]["failed"] == 0

    await db_session.refresh(project)
    await db_session.refresh(previous_composition)
    assert project.status == "completed"
    assert previous_composition.status == "stale"


@pytest.mark.asyncio
async def test_generate_should_mark_previous_compositions_stale_when_regeneration_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_all(self, project_id: str, db: AsyncSession, *, panel_ids=None):  # noqa: ANN001
        raise RuntimeError("mock generation failure")

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="重生成失败成片失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    failed_panel = build_panel(
        project.id,
        episode.id,
        title="失败分镜",
        visual_prompt="prompt-failed",
        duration_seconds=5.0,
        status="failed",
    )
    db_session.add(failed_panel)
    await db_session.flush()
    previous_composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/old.mp4",
        duration_seconds=10.0,
        status="completed",
    )
    db_session.add(previous_composition)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 500
    assert "视频生成失败" in response.json()["detail"]

    await db_session.refresh(project)
    await db_session.refresh(previous_composition)
    assert project.status == "completed"
    assert previous_composition.status == "stale"


@pytest.mark.asyncio
async def test_generate_async_submit_failed_should_not_mark_previous_compositions_stale(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class _FailDispatcher:
        def delay(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("queue down")

    monkeypatch.setattr("app.tasks.health.has_celery_worker", lambda: True)
    monkeypatch.setattr("app.api.task_mode.has_celery_worker", lambda: True)
    monkeypatch.setattr("app.tasks.generate_tasks.generate_videos_task", _FailDispatcher())

    project = Project(name="异步提交失败成片保护测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    failed_panel = build_panel(
        project.id,
        episode.id,
        title="失败分镜",
        visual_prompt="prompt-failed",
        duration_seconds=5.0,
        status="failed",
    )
    db_session.add(failed_panel)
    await db_session.flush()
    previous_composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/old.mp4",
        duration_seconds=10.0,
        status="completed",
    )
    db_session.add(previous_composition)
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/generate",
        params={"async_mode": "true"},
    )
    assert response.status_code == 500
    assert "生成任务提交失败" in response.json()["detail"]

    await db_session.refresh(project)
    await db_session.refresh(previous_composition)
    assert project.status == "completed"
    assert previous_composition.status == "completed"


@pytest.mark.asyncio
async def test_generate_should_recover_stale_processing_panels_after_interruption(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_panel(self, panel: Panel, db: AsyncSession):  # noqa: ANN001
        panel.status = "completed"
        clip = build_completed_clip(panel)
        db.add(clip)
        await db.flush()
        return [clip]

    monkeypatch.setattr("app.api.generation.get_provider", lambda: object())
    monkeypatch.setattr("app.services.video_generator.VideoGeneratorService.generate_panel", fake_generate_panel)

    project = Project(name="中断恢复测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    stale_panel = build_panel(
        project.id,
        episode.id,
        order=0,
        title="中断中的分镜",
        visual_prompt="prompt-stale",
        duration_seconds=5.0,
        status="processing",
    )
    ready_panel = build_panel(
        project.id,
        episode.id,
        order=1,
        title="已完成分镜",
        visual_prompt="prompt-ready",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add_all([stale_panel, ready_panel])
    await db_session.flush()
    db_session.add(build_completed_clip(ready_panel))
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_panels"] == 2
    assert payload["completed"] == 2
    assert payload["failed"] == 0

    await db_session.refresh(project)
    await db_session.refresh(stale_panel)
    assert project.status == "parsed"
    assert stale_panel.status == "completed"


@pytest.mark.asyncio
async def test_update_character_should_reject_when_project_is_generating(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="角色编辑门禁测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    character = Character(
        project_id=project.id,
        name="主角",
        appearance="短发",
        personality="坚毅",
        costume="校服",
    )
    db_session.add(character)
    await db_session.commit()

    response = await client.put(
        f"/api/characters/{character.id}",
        json={"name": "主角-更新"},
    )
    assert response.status_code == 409
    assert "不允许编辑角色" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_character_should_reject_blank_name(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="角色名称校验测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    character = Character(project_id=project.id, name="原名")
    db_session.add(character)
    await db_session.commit()

    response = await client.put(
        f"/api/characters/{character.id}",
        json={"name": "   "},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "角色名称不能为空"


@pytest.mark.asyncio
async def test_update_character_should_reject_duplicate_name(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="角色重名校验测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    character_a = Character(project_id=project.id, name="主角")
    character_b = Character(project_id=project.id, name="配角")
    db_session.add_all([character_a, character_b])
    await db_session.commit()

    response = await client.put(
        f"/api/characters/{character_b.id}",
        json={"name": " 主角 "},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "角色名称已存在，请使用不同名称"


@pytest.mark.asyncio
async def test_update_panel_should_reject_blank_title(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="分镜标题校验测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.flush()
    panel = build_panel(project.id, episode.id, title="原分镜", visual_prompt="prompt", status="pending")
    db_session.add(panel)
    await db_session.commit()

    response = await client.put(
        f"/api/panels/{panel.id}",
        json={"title": "   "},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "分镜标题不能为空"


@pytest.mark.asyncio
async def test_create_panel_should_reject_when_project_is_busy(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="创建分镜门禁测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    episode = build_episode(project.id)
    db_session.add(episode)
    await db_session.commit()

    response = await client.post(
        f"/api/episodes/{episode.id}/panels",
        json={
            "title": "新增分镜",
            "visual_prompt": "prompt",
            "duration_seconds": 5.0,
        },
    )
    assert response.status_code == 409
    assert "不允许创建分镜" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_project_should_reject_when_project_is_generating(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="项目删除门禁测试", status="generating")
    db_session.add(project)
    await db_session.commit()

    response = await client.delete(f"/api/projects/{project.id}")
    assert response.status_code == 409
    assert "不允许删除" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_project_should_reject_blank_name(client: AsyncClient):
    response = await client.post("/api/projects", json={"name": "   ", "description": "desc"})
    assert response.status_code == 400
    assert response.json()["detail"] == "项目名称不能为空"


@pytest.mark.asyncio
async def test_update_project_should_reject_blank_name(client: AsyncClient):
    create_resp = await client.post("/api/projects", json={"name": "有效项目名"})
    project_id = create_resp.json()["data"]["id"]

    response = await client.put(f"/api/projects/{project_id}", json={"name": "   "})
    assert response.status_code == 400
    assert response.json()["detail"] == "项目名称不能为空"


@pytest.mark.asyncio
async def test_update_project_should_reject_when_project_is_parsing(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="项目更新门禁测试", status="parsing", script_text="原始剧本")
    db_session.add(project)
    await db_session.commit()

    response = await client.put(
        f"/api/projects/{project.id}",
        json={"script_text": "新剧本"},
    )
    assert response.status_code == 409
    assert "不允许更新项目信息" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_project_should_reset_to_draft_and_stale_compositions_when_script_changed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="脚本变更回退测试", status="completed", script_text="旧剧本")
    db_session.add(project)
    await db_session.flush()

    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/old.mp4",
        duration_seconds=8.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.put(
        f"/api/projects/{project.id}",
        json={"script_text": "新剧本"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["script_text"] == "新剧本"
    assert payload["status"] == "draft"

    await db_session.refresh(project)
    await db_session.refresh(composition)
    assert project.status == "draft"
    assert composition.status == "stale"


@pytest.mark.asyncio
async def test_update_project_should_keep_status_when_script_not_changed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="脚本无变更测试", status="completed", script_text="同一份剧本")
    db_session.add(project)
    await db_session.flush()

    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/current.mp4",
        duration_seconds=8.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.put(
        f"/api/projects/{project.id}",
        json={"script_text": "同一份剧本"},
    )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "completed"

    await db_session.refresh(project)
    await db_session.refresh(composition)
    assert project.status == "completed"
    assert composition.status == "completed"
