from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Character, CompositionTask, Project, Scene, SceneCharacter, VideoClip


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
async def test_parse_should_allow_force_recover_when_project_is_stuck_parsing(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakeLLM:
        async def close(self) -> None:
            return None

    class _FakeResult:
        character_count = 0
        scene_count = 0

    async def fake_parse_script(self, project_id: str, script_text: str, db: AsyncSession):  # noqa: ANN001
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = "parsed"
        await db.flush()
        return _FakeResult()

    monkeypatch.setattr("app.llm.factory.create_llm_adapter", lambda: _FakeLLM())
    monkeypatch.setattr("app.services.script_parser.ScriptParserService.parse_script", fake_parse_script)

    project = Project(name="解析强制恢复测试", status="parsing", script_text="测试剧本")
    db_session.add(project)
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/parse",
        params={"force_recover": "true"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["scene_count"] == 0
    assert response.json()["data"]["character_count"] == 0

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

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="A cinematic opening shot",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 409
    assert "不允许启动生成" in response.json()["detail"]


@pytest.mark.asyncio
async def test_generate_should_reject_when_project_is_draft_even_if_scenes_ready(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="草稿状态生成门禁测试", status="draft")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="历史已生成场景",
        video_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 409
    assert "不允许启动生成" in response.json()["detail"]


@pytest.mark.asyncio
async def test_generate_should_allow_force_recover_when_project_is_stuck_generating(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_all(self, project_id: str, db: AsyncSession):  # noqa: ANN001
        scenes = (await db.execute(select(Scene).where(Scene.project_id == project_id))).scalars().all()
        for scene in scenes:
            if scene.status in {"pending", "failed", "generating"}:
                scene.status = "generated"
        await db.flush()

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="生成强制恢复测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="待生成场景",
        video_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/generate",
        params={"force_recover": "true"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["completed"] == 1
    assert response.json()["data"]["failed"] == 0

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_generate_should_only_validate_prompts_for_pending_or_failed_scenes(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_all(self, project_id: str, db: AsyncSession):  # noqa: ANN001
        scenes = (await db.execute(select(Scene).where(Scene.project_id == project_id))).scalars().all()
        for scene in scenes:
            if scene.status in {"pending", "failed"}:
                scene.status = "generated"
        await db.flush()

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="提示词校验范围测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    generated_scene_without_prompt = Scene(
        project_id=project.id,
        sequence_order=0,
        title="已完成但无提示词场景",
        video_prompt="",
        duration_seconds=5.0,
        status="generated",
    )
    pending_scene = Scene(
        project_id=project.id,
        sequence_order=1,
        title="待生成场景",
        video_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add_all([generated_scene_without_prompt, pending_scene])
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_scenes"] == 2
    assert payload["completed"] == 2
    assert payload["failed"] == 0


@pytest.mark.asyncio
async def test_generate_should_treat_completed_scene_status_as_ready(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_all(self, project_id: str, db: AsyncSession):  # noqa: ANN001
        return None

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="历史状态兼容测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="历史已完成场景",
        video_prompt="legacy prompt",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_scenes"] == 1
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

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="A cinematic ending shot",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/compose",
        json={"include_subtitles": False, "include_tts": False},
    )
    assert response.status_code == 409
    assert "不允许启动合成" in response.json()["detail"]


@pytest.mark.asyncio
async def test_compose_should_allow_force_recover_when_project_is_stuck_composing(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_compose(self, project_id: str, options, db: AsyncSession):  # noqa: ANN001
        return "force-recover-compose-id"

    monkeypatch.setattr("app.api.composition.VideoEditorService.compose", fake_compose)

    project = Project(name="合成强制恢复测试", status="composing")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="已完成场景",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/compose",
        params={"force_recover": "true"},
        json={"include_subtitles": False, "include_tts": False},
    )
    assert response.status_code == 200
    assert response.json()["data"]["composition_id"] == "force-recover-compose-id"

    await db_session.refresh(project)
    assert project.status == "completed"


@pytest.mark.asyncio
async def test_compose_force_recover_should_not_restore_composing_when_async_submit_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    class _FailDispatcher:
        def delay(self, *args, **kwargs):  # noqa: ANN002, ANN003
            raise RuntimeError("queue down")

    monkeypatch.setattr("app.tasks.health.has_celery_worker", lambda: True)
    monkeypatch.setattr("app.api.task_mode.has_celery_worker", lambda: True)
    monkeypatch.setattr("app.tasks.compose_tasks.compose_video_task", _FailDispatcher())

    project = Project(name="合成恢复回滚测试", status="composing")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="已完成场景",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/compose",
        params={"async_mode": "true", "force_recover": "true"},
        json={"include_subtitles": False, "include_tts": False},
    )
    assert response.status_code == 500
    assert "合成任务提交失败" in response.json()["detail"]

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_compose_should_accept_completed_scene_status_for_legacy_data(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_compose(self, project_id: str, options, db: AsyncSession):  # noqa: ANN001
        return "legacy-comp-id"

    monkeypatch.setattr("app.api.composition.VideoEditorService.compose", fake_compose)

    project = Project(name="历史场景状态合成测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="历史场景",
        video_prompt="legacy prompt",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(
        f"/api/projects/{project.id}/compose",
        json={"include_subtitles": False, "include_tts": False},
    )
    assert response.status_code == 200
    assert response.json()["data"]["composition_id"] == "legacy-comp-id"


@pytest.mark.asyncio
async def test_compose_should_mark_previous_compositions_stale(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    new_composition_id = "11111111-1111-1111-1111-111111111111"

    async def fake_compose(self, project_id: str, options, db: AsyncSession):  # noqa: ANN001
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

    db_session.add(Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="generated",
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
async def test_update_scene_should_invalidate_clips_when_generation_fields_changed(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="场景更新失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="old prompt",
        negative_prompt="old negative",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.flush()

    clip = VideoClip(
        scene_id=scene.id,
        clip_order=0,
        file_path="./outputs/videos/old.mp4",
        duration_seconds=5.0,
        provider_task_id="task-old",
        status="completed",
    )
    db_session.add(clip)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/old.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.put(
        f"/api/scenes/{scene.id}",
        json={
            "video_prompt": "new prompt",
            "duration_seconds": 8.0,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"

    # API 在独立会话中提交了变更，测试会话的 identity map 持有旧对象（expire_on_commit=False），
    # 需手动过期以使后续 select 从数据库读取最新值。
    # 先保存 ID，因为 expire_all() 后访问 ORM 属性会触发同步懒加载，在 aiosqlite 中不可行。
    _scene_id = scene.id
    _project_id = project.id
    _composition_id = composition.id
    db_session.expire_all()

    clips = (await db_session.execute(
        select(VideoClip).where(VideoClip.scene_id == _scene_id)
    )).scalars().all()
    assert clips == []

    updated_project = (await db_session.execute(
        select(Project).where(Project.id == _project_id)
    )).scalar_one()
    updated_composition = (await db_session.execute(
        select(CompositionTask).where(CompositionTask.id == _composition_id)
    )).scalar_one()
    assert updated_project.status == "parsed"
    assert updated_composition.status == "stale"


@pytest.mark.asyncio
async def test_update_scene_should_not_invalidate_when_nullable_generation_fields_are_semantically_unchanged(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="场景空白归一测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="stable prompt",
        negative_prompt=None,
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.flush()

    clip = VideoClip(
        scene_id=scene.id,
        clip_order=0,
        file_path="./outputs/videos/stable.mp4",
        duration_seconds=5.0,
        provider_task_id="task-stable",
        status="completed",
    )
    db_session.add(clip)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/stable.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.put(
        f"/api/scenes/{scene.id}",
        json={
            "title": "场景一（仅标题更新）",
            "video_prompt": "stable prompt",
            "negative_prompt": "   ",
            "camera_movement": " ",
            "dialogue": "",
            "duration_seconds": 5.0,
        },
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "generated"

    clips = (await db_session.execute(
        select(VideoClip).where(VideoClip.scene_id == scene.id)
    )).scalars().all()
    assert len(clips) == 1

    await db_session.refresh(project)
    await db_session.refresh(composition)
    assert project.status == "parsed"
    assert composition.status == "stale"


@pytest.mark.asyncio
async def test_update_scene_should_reject_when_project_is_generating(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="场景编辑门禁测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.put(
        f"/api/scenes/{scene.id}",
        json={"video_prompt": "new prompt"},
    )
    assert response.status_code == 409
    assert "不允许编辑场景" in response.json()["detail"]


@pytest.mark.asyncio
async def test_retry_scene_should_keep_project_parsed_when_other_scenes_are_pending(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_scene(self, scene: Scene, db: AsyncSession):  # noqa: ANN001
        scene.status = "generated"
        await db.flush()
        return []

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_scene", fake_generate_scene)

    project = Project(name="单场景重试状态测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    retry_scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="待重试场景",
        video_prompt="retry prompt",
        duration_seconds=5.0,
        status="failed",
    )
    pending_scene = Scene(
        project_id=project.id,
        sequence_order=1,
        title="其他待生成场景",
        video_prompt="pending prompt",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add_all([retry_scene, pending_scene])
    await db_session.commit()

    response = await client.post(f"/api/scenes/{retry_scene.id}/retry")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "generated"

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_retry_scene_should_preserve_completed_project_when_retry_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_scene(self, scene: Scene, db: AsyncSession):  # noqa: ANN001
        raise RuntimeError("mock generation failure")

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_scene", fake_generate_scene)

    project = Project(name="已完成项目重试失败测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="失败场景",
        video_prompt="retry prompt",
        duration_seconds=5.0,
        status="failed",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(f"/api/scenes/{scene.id}/retry")
    assert response.status_code == 500
    assert "场景重试失败" in response.json()["detail"]

    await db_session.refresh(project)
    assert project.status == "completed"


@pytest.mark.asyncio
async def test_retry_scene_should_mark_previous_compositions_stale_on_success(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_scene(self, scene: Scene, db: AsyncSession):  # noqa: ANN001
        scene.status = "generated"
        await db.flush()
        return []

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_scene", fake_generate_scene)

    project = Project(name="重试成片失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="需重试场景",
        video_prompt="retry prompt",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/current.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.post(f"/api/scenes/{scene.id}/retry")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "generated"

    await db_session.refresh(project)
    await db_session.refresh(composition)
    assert project.status == "parsed"
    assert composition.status == "stale"


@pytest.mark.asyncio
async def test_retry_scene_should_mark_previous_compositions_stale_when_retry_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_scene(self, scene: Scene, db: AsyncSession):  # noqa: ANN001
        raise RuntimeError("mock generation failure")

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_scene", fake_generate_scene)

    project = Project(name="重试失败成片失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="失败场景",
        video_prompt="retry prompt",
        duration_seconds=5.0,
        status="failed",
    )
    db_session.add(scene)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/current.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.post(f"/api/scenes/{scene.id}/retry")
    assert response.status_code == 500
    assert "场景重试失败" in response.json()["detail"]

    await db_session.refresh(project)
    await db_session.refresh(composition)
    assert project.status == "completed"
    assert composition.status == "stale"


@pytest.mark.asyncio
async def test_retry_scene_should_keep_completed_scene_status_when_post_process_failed(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_scene(self, scene: Scene, db: AsyncSession):  # noqa: ANN001
        scene.status = "completed"
        await db.flush()
        raise RuntimeError("post process failed")

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_scene", fake_generate_scene)

    project = Project(name="重试历史状态保护测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="历史状态场景",
        video_prompt="retry prompt",
        duration_seconds=5.0,
        status="failed",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(f"/api/scenes/{scene.id}/retry")
    assert response.status_code == 500
    assert "场景重试失败" in response.json()["detail"]

    await db_session.refresh(scene)
    assert scene.status == "completed"


@pytest.mark.asyncio
async def test_retry_scene_should_mark_scene_failed_when_provider_init_failed(
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

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="失败场景",
        video_prompt="retry prompt",
        duration_seconds=5.0,
        status="failed",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(f"/api/scenes/{scene.id}/retry")
    assert response.status_code == 500
    assert "场景重试失败" in response.json()["detail"]

    await db_session.refresh(scene)
    assert scene.status == "failed"


@pytest.mark.asyncio
async def test_retry_scene_should_restore_ready_scene_when_provider_init_failed(
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

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="已完成场景",
        video_prompt="retry prompt",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    composition = CompositionTask(
        project_id=project.id,
        output_path="./outputs/compositions/current.mp4",
        duration_seconds=5.0,
        status="completed",
    )
    db_session.add(composition)
    await db_session.commit()

    response = await client.post(f"/api/scenes/{scene.id}/retry")
    assert response.status_code == 500
    assert "场景重试失败" in response.json()["detail"]

    await db_session.refresh(project)
    await db_session.refresh(scene)
    await db_session.refresh(composition)
    assert project.status == "completed"
    assert scene.status == "generated"
    assert composition.status == "completed"


@pytest.mark.asyncio
async def test_delete_scene_should_reject_when_project_is_generating(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="删除门禁测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.delete(f"/api/scenes/{scene.id}")
    assert response.status_code == 409
    assert "不允许删除场景" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reorder_scenes_should_reject_when_project_is_composing(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="排序门禁测试", status="composing")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.put(
        f"/api/scenes/project/{project.id}/reorder",
        json={"scene_ids": [scene.id]},
    )
    assert response.status_code == 409
    assert "不允许排序场景" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reorder_scenes_should_not_downgrade_when_order_unchanged(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="排序无变更测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    scene_a = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="prompt-a",
        duration_seconds=5.0,
        status="generated",
    )
    scene_b = Scene(
        project_id=project.id,
        sequence_order=1,
        title="场景二",
        video_prompt="prompt-b",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add_all([scene_a, scene_b])
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
        f"/api/scenes/project/{project.id}/reorder",
        json={"scene_ids": [scene_a.id, scene_b.id]},
    )
    assert response.status_code == 200

    await db_session.refresh(project)
    await db_session.refresh(composition)
    assert project.status == "completed"
    assert composition.status == "completed"


@pytest.mark.asyncio
async def test_update_character_reference_image_should_invalidate_related_scene_generation(
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

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="A cinematic portrait shot",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.flush()

    db_session.add(SceneCharacter(scene_id=scene.id, character_id=character.id, action="看向镜头"))
    db_session.add(VideoClip(
        scene_id=scene.id,
        clip_order=0,
        file_path="./outputs/videos/scene_old.mp4",
        status="completed",
        duration_seconds=5.0,
    ))
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
    await db_session.refresh(scene)
    await db_session.refresh(composition)
    clips = (await db_session.execute(select(VideoClip).where(VideoClip.scene_id == scene.id))).scalars().all()

    assert project.status == "parsed"
    assert scene.status == "pending"
    assert composition.status == "stale"
    assert clips == []


@pytest.mark.asyncio
async def test_update_unreferenced_character_should_not_invalidate_project_outputs(
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

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="A cinematic shot",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.flush()
    db_session.add(VideoClip(
        scene_id=scene.id,
        clip_order=0,
        file_path="./outputs/videos/scene.mp4",
        status="completed",
        duration_seconds=5.0,
    ))

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
    await db_session.refresh(scene)
    await db_session.refresh(composition)
    assert project.status == "completed"
    assert scene.status == "generated"
    assert composition.status == "completed"


@pytest.mark.asyncio
async def test_reorder_scenes_should_return_404_when_project_not_found(
    client: AsyncClient,
):
    response = await client.put(
        "/api/scenes/project/non-existent-project/reorder",
        json={"scene_ids": ["scene-1"]},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "项目不存在"


@pytest.mark.asyncio
async def test_reorder_scenes_should_require_full_scene_id_set(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="排序完整性测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene_a = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景A",
        video_prompt="prompt A",
        duration_seconds=5.0,
        status="pending",
    )
    scene_b = Scene(
        project_id=project.id,
        sequence_order=1,
        title="场景B",
        video_prompt="prompt B",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add_all([scene_a, scene_b])
    await db_session.commit()

    response = await client.put(
        f"/api/scenes/project/{project.id}/reorder",
        json={"scene_ids": [scene_a.id]},
    )
    assert response.status_code == 400
    assert "scene_ids 必须完整覆盖项目场景且不能重复" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_scene_should_compact_sequence_order_after_delete(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="删除后重排测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene_a = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景A",
        video_prompt="prompt A",
        duration_seconds=5.0,
        status="pending",
    )
    scene_b = Scene(
        project_id=project.id,
        sequence_order=1,
        title="场景B",
        video_prompt="prompt B",
        duration_seconds=5.0,
        status="pending",
    )
    scene_c = Scene(
        project_id=project.id,
        sequence_order=2,
        title="场景C",
        video_prompt="prompt C",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add_all([scene_a, scene_b, scene_c])
    await db_session.commit()

    response = await client.delete(f"/api/scenes/{scene_b.id}")
    assert response.status_code == 200

    # API 在独立会话中完成了删除和 sequence_order 压缩，需过期本会话缓存
    # 先保存 ID，因为 expire_all() 后访问 ORM 属性会触发同步懒加载，在 aiosqlite 中不可行。
    _project_id = project.id
    db_session.expire_all()

    remaining = (await db_session.execute(
        select(Scene).where(Scene.project_id == _project_id).order_by(Scene.sequence_order)
    )).scalars().all()
    assert [item.title for item in remaining] == ["场景A", "场景C"]
    assert [item.sequence_order for item in remaining] == [0, 1]


@pytest.mark.asyncio
async def test_generate_should_keep_completed_status_when_nothing_to_regenerate(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="已完成项目空生成测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="已生成场景",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    assert response.json()["data"]["completed"] == 1
    assert response.json()["data"]["failed"] == 0

    await db_session.refresh(project)
    assert project.status == "completed"


@pytest.mark.asyncio
async def test_generate_should_recover_failed_project_when_all_scenes_already_ready(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="失败状态直返恢复测试", status="failed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="已生成场景",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    assert response.json()["data"]["completed"] == 1
    assert response.json()["data"]["failed"] == 0

    await db_session.refresh(project)
    assert project.status == "parsed"


@pytest.mark.asyncio
async def test_generate_should_recover_generating_project_when_all_scenes_already_ready(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="生成卡状态直返恢复测试", status="generating")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="已生成场景",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add(scene)
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
    async def fake_generate_all(self, project_id: str, db: AsyncSession):  # noqa: ANN001
        target = (await db.execute(
            select(Scene).where(Scene.project_id == project_id, Scene.status == "failed")
        )).scalar_one()
        target.status = "generated"
        await db.flush()

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="重生成成片失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    ready_scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="已完成场景",
        video_prompt="prompt-ready",
        duration_seconds=5.0,
        status="generated",
    )
    failed_scene = Scene(
        project_id=project.id,
        sequence_order=1,
        title="失败场景",
        video_prompt="prompt-failed",
        duration_seconds=5.0,
        status="failed",
    )
    db_session.add_all([ready_scene, failed_scene])
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
    async def fake_generate_all(self, project_id: str, db: AsyncSession):  # noqa: ANN001
        raise RuntimeError("mock generation failure")

    monkeypatch.setattr("app.api.generation.VideoGeneratorService.generate_all", fake_generate_all)

    project = Project(name="重生成失败成片失效测试", status="completed")
    db_session.add(project)
    await db_session.flush()

    failed_scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="失败场景",
        video_prompt="prompt-failed",
        duration_seconds=5.0,
        status="failed",
    )
    db_session.add(failed_scene)
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

    failed_scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="失败场景",
        video_prompt="prompt-failed",
        duration_seconds=5.0,
        status="failed",
    )
    db_session.add(failed_scene)
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
async def test_generate_should_recover_stale_generating_scenes_after_interruption(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
):
    async def fake_generate_scene(self, scene: Scene, db: AsyncSession):  # noqa: ANN001
        scene.status = "generated"
        await db.flush()
        return []

    monkeypatch.setattr("app.api.generation.get_provider", lambda: object())
    monkeypatch.setattr("app.services.video_generator.VideoGeneratorService.generate_scene", fake_generate_scene)

    project = Project(name="中断恢复测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    stale_scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="中断中的场景",
        video_prompt="prompt-stale",
        duration_seconds=5.0,
        status="generating",
    )
    ready_scene = Scene(
        project_id=project.id,
        sequence_order=1,
        title="已完成场景",
        video_prompt="prompt-ready",
        duration_seconds=5.0,
        status="generated",
    )
    db_session.add_all([stale_scene, ready_scene])
    await db_session.commit()

    response = await client.post(f"/api/projects/{project.id}/generate")
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total_scenes"] == 2
    assert payload["completed"] == 2
    assert payload["failed"] == 0

    await db_session.refresh(project)
    await db_session.refresh(stale_scene)
    assert project.status == "parsed"
    assert stale_scene.status == "generated"


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
async def test_update_scene_should_reject_blank_title(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="场景标题校验测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="原场景",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.put(
        f"/api/scenes/{scene.id}",
        json={"title": "   "},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "场景标题不能为空"


@pytest.mark.asyncio
async def test_update_scene_should_reject_invalid_transition_hint(
    client: AsyncClient,
    db_session: AsyncSession,
):
    project = Project(name="转场校验测试", status="parsed")
    db_session.add(project)
    await db_session.flush()

    scene = Scene(
        project_id=project.id,
        sequence_order=0,
        title="场景一",
        video_prompt="prompt",
        duration_seconds=5.0,
        status="pending",
    )
    db_session.add(scene)
    await db_session.commit()

    response = await client.put(
        f"/api/scenes/{scene.id}",
        json={"transition_hint": "zoom-blur"},
    )
    assert response.status_code == 400
    assert "transition_hint 仅支持" in response.json()["detail"]


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
