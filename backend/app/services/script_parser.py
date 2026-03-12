from __future__ import annotations

import logging

from pydantic import BaseModel

from app.config import settings
from app.llm.base import LLMAdapter, Message
from app.prompts.narrative_analysis import NARRATIVE_ANALYSIS_SYSTEM, NARRATIVE_ANALYSIS_USER
from app.prompts.prompt_generation import PROMPT_GENERATION_SYSTEM, PROMPT_GENERATION_USER
from app.services.llm_json import extract_json_object

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
ALLOWED_TRANSITIONS = {"none", "cut", "crossfade", "fade_black"}


class CharacterProfile(BaseModel):
    """角色档案"""
    name: str
    appearance: str
    personality: str
    costume: str


class SceneNarrative(BaseModel):
    """场景叙事"""
    title: str
    narrative: str
    setting: str
    mood: str
    character_names: list[str]
    character_actions: dict[str, str]
    dialogue: str | None = None
    estimated_duration: float = 5.0


class GlobalStyle(BaseModel):
    """全局视觉风格"""
    visual_style: str
    color_tone: str
    era: str
    mood: str


class NarrativeAnalysis(BaseModel):
    """第一阶段输出：叙事分析结果"""
    global_style: GlobalStyle
    characters: list[CharacterProfile]
    scenes: list[SceneNarrative]


class ScenePrompt(BaseModel):
    """第二阶段输出：场景视频提示词"""
    sequence_order: int
    title: str
    video_prompt: str
    negative_prompt: str = ""
    camera_movement: str = "static"
    style_keywords: str = ""
    duration_seconds: float = 5.0
    transition_hint: str = "crossfade"


class ScenePromptsResult(BaseModel):
    """第二阶段输出列表"""
    scenes: list[ScenePrompt]


def _format_global_style(style: GlobalStyle) -> str:
    return (
        f"风格: {style.visual_style}, "
        f"色调: {style.color_tone}, "
        f"时代: {style.era}, "
        f"氛围: {style.mood}"
    )


def _format_characters_info(characters: list[CharacterProfile]) -> str:
    return "\n".join(f"- {c.name}: 外貌={c.appearance}, 服装={c.costume}" for c in characters)


def _format_scenes_info(scenes: list[SceneNarrative]) -> str:
    return "\n".join(
        f"场景{i + 1} [{scene.title}]: {scene.narrative} (环境: {scene.setting}, 氛围: {scene.mood}, "
        f"角色: {', '.join(scene.character_names)}, 时长: {scene.estimated_duration}秒"
        f"{', 台词: ' + scene.dialogue if scene.dialogue else ''})"
        for i, scene in enumerate(scenes)
    )


def _normalize_allowed_panel_seconds(raw_allowed: list[int] | None) -> list[int]:
    """标准化离散秒数列表（去重、排序、过滤非法值）。"""
    if not raw_allowed:
        return []

    items: set[int] = set()
    for raw in raw_allowed:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            items.add(value)
    return sorted(items)


def _resolve_panel_duration_constraints(
    *,
    max_scene_seconds: int | None,
    allowed_scene_seconds: list[int] | None,
) -> tuple[int, list[int] | None, str]:
    """解析时长约束：同时支持 max 上限与离散秒数列表。"""
    allowed = _normalize_allowed_panel_seconds(allowed_scene_seconds)
    if allowed:
        max_sec = max(allowed)
        if max_scene_seconds is not None and int(max_scene_seconds) < max_sec:
            raise ValueError(
                f"max_scene_seconds({max_scene_seconds}) 小于 allowed_scene_seconds 的最大值({max_sec})，配置不一致"
            )
        allowed_text = ", ".join(str(value) for value in allowed)
        return max_sec, allowed, allowed_text

    max_sec = int(max_scene_seconds or settings.video_provider_max_duration_seconds)
    max_sec = max(1, max_sec)
    return max_sec, None, "（未提供离散列表）"


def normalize_panel_duration(
    duration_seconds: float,
    *,
    max_duration: float,
    allowed_seconds: list[int] | None = None,
) -> float:
    """按约束规范化时长：先裁剪到 max，再吸附到 allowed_seconds（若提供）。"""
    normalized = min(max(0.1, float(duration_seconds)), float(max_duration))
    if allowed_seconds:
        nearest = min(allowed_seconds, key=lambda second: abs(second - normalized))
        return float(nearest)
    return normalized


class ScriptParserService:
    """剧本解析服务：两阶段 LLM 分析"""

    def __init__(self, llm: LLMAdapter):
        self._llm = llm

    async def _complete_with_retry(
        self,
        *,
        messages: list[Message],
        response_format: type[BaseModel],
        temperature: float,
        attempt_label: str,
        failure_label: str,
    ) -> BaseModel:
        for attempt in range(MAX_RETRIES):
            try:
                response = await self._llm.complete(messages, response_format=response_format, temperature=temperature)
                data = extract_json_object(response.content)
                return response_format.model_validate(data)
            except Exception as e:
                logger.warning("%s第 %d 次尝试失败: %s", attempt_label, attempt + 1, e)
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(f"{failure_label}（已重试 {MAX_RETRIES} 次）: {e}") from e

        raise RuntimeError(failure_label)

    async def analyze_narrative(
        self,
        script_text: str,
        *,
        max_scene_seconds: int | None = None,
        allowed_scene_seconds: list[int] | None = None,
    ) -> NarrativeAnalysis:
        """第一阶段：叙事结构分析"""
        max_sec, allowed_seconds, allowed_seconds_text = _resolve_panel_duration_constraints(
            max_scene_seconds=max_scene_seconds,
            allowed_scene_seconds=allowed_scene_seconds,
        )
        messages = [
            Message(role="system", content=NARRATIVE_ANALYSIS_SYSTEM.format(
                max_scene_seconds=max_sec,
                allowed_scene_seconds=allowed_seconds_text,
            )),
            Message(role="user", content=NARRATIVE_ANALYSIS_USER.format(
                script_text=script_text,
                max_scene_seconds=max_sec,
                allowed_scene_seconds=allowed_seconds_text,
            )),
        ]
        result = await self._complete_with_retry(
            messages=messages,
            response_format=NarrativeAnalysis,
            temperature=0.3,
            attempt_label="叙事分析",
            failure_label="叙事分析失败",
        )
        analysis = NarrativeAnalysis.model_validate(result)
        if allowed_seconds:
            for scene in analysis.scenes:
                scene.estimated_duration = normalize_panel_duration(
                    scene.estimated_duration,
                    max_duration=max_sec,
                    allowed_seconds=allowed_seconds,
                )
        return analysis

    async def generate_panel_prompts(
        self,
        analysis: NarrativeAnalysis,
        *,
        max_scene_seconds: int | None = None,
        allowed_scene_seconds: list[int] | None = None,
    ) -> list[ScenePrompt]:
        """第二阶段：为每个分镜生成视频提示词"""
        max_sec, allowed_seconds, allowed_seconds_text = _resolve_panel_duration_constraints(
            max_scene_seconds=max_scene_seconds,
            allowed_scene_seconds=allowed_scene_seconds,
        )

        messages = [
            Message(role="system", content=PROMPT_GENERATION_SYSTEM.format(
                max_scene_seconds=max_sec,
                allowed_scene_seconds=allowed_seconds_text,
            )),
            Message(role="user", content=PROMPT_GENERATION_USER.format(
                global_style=_format_global_style(analysis.global_style),
                characters_info=_format_characters_info(analysis.characters),
                scenes_info=_format_scenes_info(analysis.scenes),
                max_scene_seconds=max_sec,
                allowed_scene_seconds=allowed_seconds_text,
            )),
        ]
        result = await self._complete_with_retry(
            messages=messages,
            response_format=ScenePromptsResult,
            temperature=0.5,
            attempt_label="提示词生成",
            failure_label="提示词生成失败",
        )
        prompts = ScenePromptsResult.model_validate(result).scenes
        if allowed_seconds:
            for prompt in prompts:
                prompt.duration_seconds = normalize_panel_duration(
                    prompt.duration_seconds,
                    max_duration=max_sec,
                    allowed_seconds=allowed_seconds,
                )
        return prompts
