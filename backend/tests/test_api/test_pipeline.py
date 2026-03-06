from __future__ import annotations

import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMAdapter, LLMResponse, Message
from app.models import CompositionTask
from app.video_providers.base import VideoGenerateRequest, VideoProvider, VideoTaskStatus


class FakePipelineLLM(LLMAdapter):
    """用于 API 全链路测试的固定输出 LLM。"""

    def __init__(self):
        self._calls = 0

    async def complete(
        self,
        messages: list[Message],
        response_format=None,
        temperature: float = 0.7,
    ) -> LLMResponse:
        self._calls += 1
        if self._calls == 1:
            content = json.dumps({
                "global_style": {
                    "visual_style": "电影感写实",
                    "color_tone": "冷色低饱和",
                    "era": "现代都市",
                    "mood": "悬疑紧张",
                },
                "characters": [
                    {
                        "name": "林川",
                        "appearance": "黑发，短夹克",
                        "personality": "克制冷静",
                        "costume": "深色风衣",
                    }
                ],
                "scenes": [
                    {
                        "title": "雨夜街口",
                        "narrative": "林川在雨夜街口等待目标出现",
                        "setting": "城市街口，夜晚，路灯昏黄",
                        "mood": "压抑",
                        "character_names": ["林川"],
                        "character_actions": {"林川": "抬头观察远处"},
                        "dialogue": "时间到了。",
                        "estimated_duration": 6.0,
                    },
                    {
                        "title": "天台对峙",
                        "narrative": "林川在天台与目标对峙",
                        "setting": "高楼天台，夜风强烈",
                        "mood": "紧张",
                        "character_names": ["林川"],
                        "character_actions": {"林川": "缓慢逼近"},
                        "dialogue": "到此为止。",
                        "estimated_duration": 4.0,
                    },
                ],
            }, ensure_ascii=False)
            return LLMResponse(content=content)

        content = json.dumps({
            "scenes": [
                {
                    "sequence_order": 0,
                    "title": "雨夜街口",
                    "video_prompt": "rainy city street at night, cinematic, tracking shot, male lead in dark coat",
                    "negative_prompt": "low quality, blurry, watermark",
                    "camera_movement": "tracking",
                    "style_keywords": "cinematic, realistic, moody",
                    "duration_seconds": 6.0,
                    "transition_hint": "crossfade",
                },
                {
                    "sequence_order": 1,
                    "title": "天台对峙",
                    "video_prompt": "rooftop confrontation at night, dramatic wind, close-up to wide shot",
                    "negative_prompt": "low quality, blurry, watermark",
                    "camera_movement": "dolly out",
                    "style_keywords": "cinematic, tense, realistic",
                    "duration_seconds": 4.0,
                    "transition_hint": "fade_black",
                },
            ]
        }, ensure_ascii=False)
        return LLMResponse(content=content)

    async def stream(self, messages: list[Message]) -> AsyncIterator[str]:
        if False:
            yield ""

    async def close(self) -> None:
        return None


class FakePipelineProvider(VideoProvider):
    """用于视频生成链路测试的假 provider。"""

    def __init__(self):
        self.requests: list[VideoGenerateRequest] = []
        self._task_counter = 0
        self._poll_counter: dict[str, int] = {}

    @property
    def name(self) -> str:
        return "pipeline-fake"

    @property
    def max_duration_seconds(self) -> float:
        return 4.0

    async def generate(self, request: VideoGenerateRequest) -> str:
        self.requests.append(request)
        self._task_counter += 1
        task_id = f"task-{self._task_counter}"
        self._poll_counter[task_id] = 0
        return task_id

    async def poll_status(self, task_id: str) -> VideoTaskStatus:
        count = self._poll_counter.get(task_id, 0)
        self._poll_counter[task_id] = count + 1
        if count == 0:
            return VideoTaskStatus(task_id=task_id, status="processing", progress_percent=60.0)
        return VideoTaskStatus(task_id=task_id, status="completed", progress_percent=100.0)

    async def download(self, task_id: str, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-video-content")
        return output_path


@pytest.mark.asyncio
async def test_pipeline_parse_generate_compose_should_succeed(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    fake_llm = FakePipelineLLM()
    fake_provider = FakePipelineProvider()
    monkeypatch.setattr("app.llm.factory.create_llm_adapter", lambda: fake_llm)
    monkeypatch.setattr("app.api.generation.get_provider", lambda: fake_provider)

    async def fake_compose(
        self,
        project_id: str,
        options,
        db: AsyncSession,
        episode_id: str | None = None,
    ) -> str:
        task = CompositionTask(
            project_id=project_id,
            output_path=f"/tmp/{project_id}.mp4",
            transition_type=options.transition_type.value,
            include_subtitles=options.include_subtitles,
            include_tts=options.include_tts,
            status="completed",
        )
        db.add(task)
        await db.flush()
        return task.id

    monkeypatch.setattr("app.api.composition.VideoEditorService.compose", fake_compose)

    create_resp = await client.post("/api/projects", json={"name": "流水线项目"})
    assert create_resp.status_code == 200
    project_id = create_resp.json()["data"]["id"]

    update_resp = await client.put(
        f"/api/projects/{project_id}",
        json={"script_text": "一个雨夜追踪并在天台对峙的短剧本"},
    )
    assert update_resp.status_code == 200

    parse_resp = await client.post(f"/api/projects/{project_id}/parse")
    assert parse_resp.status_code == 200
    assert parse_resp.json()["data"]["panel_count"] == 2
    assert parse_resp.json()["data"]["character_count"] == 1

    characters_resp = await client.get(f"/api/characters/project/{project_id}")
    assert characters_resp.status_code == 200
    characters = characters_resp.json()["data"]
    assert len(characters) == 1
    character_id = characters[0]["id"]

    reference_image_url = "https://example.com/linchuan.png"
    update_char_resp = await client.put(
        f"/api/characters/{character_id}",
        json={"reference_image_url": reference_image_url},
    )
    assert update_char_resp.status_code == 200
    assert update_char_resp.json()["data"]["reference_image_url"] == reference_image_url

    generate_resp = await client.post(f"/api/projects/{project_id}/generate")
    assert generate_resp.status_code == 200
    assert generate_resp.json()["data"]["total_panels"] == 2
    assert generate_resp.json()["data"]["completed"] == 2
    assert generate_resp.json()["data"]["failed"] == 0

    # 第一场 6 秒 + 第二场 4 秒，provider 最大 4 秒 => 3 段请求。
    assert len(fake_provider.requests) == 3
    assert all(req.reference_image_url == reference_image_url for req in fake_provider.requests)

    compose_resp = await client.post(
        f"/api/projects/{project_id}/compose",
        json={
            "transition_type": "crossfade",
            "transition_duration": 0.5,
            "include_subtitles": False,
            "include_tts": False,
        },
    )
    assert compose_resp.status_code == 200
    composition_id = compose_resp.json()["data"]["composition_id"]

    get_comp_resp = await client.get(f"/api/compositions/{composition_id}")
    assert get_comp_resp.status_code == 200
    assert get_comp_resp.json()["data"]["status"] == "completed"

    # 最终项目状态应为 completed。
    project_resp = await client.get(f"/api/projects/{project_id}")
    assert project_resp.status_code == 200
    assert project_resp.json()["data"]["status"] == "completed"
