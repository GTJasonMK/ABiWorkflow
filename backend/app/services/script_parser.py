from __future__ import annotations

import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.base import LLMAdapter, Message
from app.models import Character, Project, Scene, SceneCharacter
from app.progress_payload import PROGRESS_KEY_MESSAGE, PROGRESS_KEY_PERCENT
from app.project_status import PROJECT_STATUS_PARSED
from app.prompts.narrative_analysis import NARRATIVE_ANALYSIS_SYSTEM, NARRATIVE_ANALYSIS_USER
from app.prompts.prompt_generation import PROMPT_GENERATION_SYSTEM, PROMPT_GENERATION_USER
from app.scene_status import SCENE_STATUS_PENDING
from app.services.composition_state import mark_completed_compositions_stale
from app.services.llm_json import extract_json_object
from app.services.progress import publish_progress

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


class ParseResult(BaseModel):
    """完整解析结果"""
    character_count: int
    panel_count: int


def _extract_json(content: str) -> dict:
    """兼容旧调用入口，统一走公共 JSON 提取逻辑。"""
    return extract_json_object(content)


def _publish_parse_progress(project_id: str, message: str, percent: int) -> None:
    publish_progress(project_id, "parse_progress", {
        PROGRESS_KEY_MESSAGE: message,
        PROGRESS_KEY_PERCENT: percent,
    })


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


def _normalize_scene_duration(duration_seconds: float, *, max_duration: float) -> float:
    return min(max(0.1, float(duration_seconds)), max_duration)



def _normalize_transition_hint(raw_transition_hint: str | None, *, scene_index: int) -> str:
    transition_hint = (raw_transition_hint or "crossfade").strip().lower()
    if transition_hint in ALLOWED_TRANSITIONS:
        return transition_hint
    logger.warning("场景 %d 的 transition_hint=%s 非法，已回退为 crossfade", scene_index + 1, raw_transition_hint)
    return "crossfade"



def _resolve_scene_title(prompt: ScenePrompt, narrative: SceneNarrative | None, *, scene_index: int) -> str:
    title = (prompt.title or "").strip()
    if not title and narrative:
        title = (narrative.title or "").strip()
    return title or f"场景 {scene_index + 1}"



def _resolve_character_action(narrative: SceneNarrative, raw_char_name: str | None, char_name: str) -> str:
    action = ""
    if isinstance(raw_char_name, str):
        action = narrative.character_actions.get(raw_char_name, "")
    return action or narrative.character_actions.get(char_name, "")


def _validate_scene_prompts(scene_prompts: list[ScenePrompt], analysis: NarrativeAnalysis) -> None:
    if not scene_prompts:
        raise RuntimeError("未生成任何场景提示词，请检查剧本内容后重试")
    if len(scene_prompts) != len(analysis.scenes):
        raise RuntimeError(
            f"提示词场景数({len(scene_prompts)})与叙事场景数({len(analysis.scenes)})不一致，请重试解析"
        )


async def _clear_project_storyboard_data(project_id: str, db: AsyncSession) -> None:
    old_scenes = (await db.execute(select(Scene).where(Scene.project_id == project_id))).scalars().all()
    for scene in old_scenes:
        await db.delete(scene)

    old_characters = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
    for character in old_characters:
        await db.delete(character)

    await mark_completed_compositions_stale(db, project_id)
    await db.flush()


async def _persist_characters(
    project_id: str,
    characters: list[CharacterProfile],
    db: AsyncSession,
) -> dict[str, Character]:
    char_map: dict[str, Character] = {}
    for profile in characters:
        normalized_name = (profile.name or "").strip()
        if not normalized_name:
            raise RuntimeError("角色姓名不能为空")
        if normalized_name in char_map:
            raise RuntimeError(f"角色姓名重复: {normalized_name}")

        character = Character(
            project_id=project_id,
            name=normalized_name,
            appearance=profile.appearance,
            personality=profile.personality,
            costume=profile.costume,
        )
        db.add(character)
        char_map[normalized_name] = character

    await db.flush()
    return char_map


async def _link_scene_characters(
    scene: Scene,
    narrative: SceneNarrative | None,
    char_map: dict[str, Character],
    db: AsyncSession,
) -> None:
    if narrative is None:
        return

    linked_character_ids: set[str] = set()
    for raw_char_name in narrative.character_names:
        char_name = (raw_char_name or "").strip()
        if char_name not in char_map:
            continue

        character_id = char_map[char_name].id
        if character_id in linked_character_ids:
            continue

        db.add(SceneCharacter(
            scene_id=scene.id,
            character_id=character_id,
            action=_resolve_character_action(narrative, raw_char_name, char_name),
        ))
        linked_character_ids.add(character_id)


def _build_scene_entity(
    *,
    project_id: str,
    scene_index: int,
    prompt: ScenePrompt,
    narrative: SceneNarrative | None,
    max_duration: float,
) -> Scene:
    prompt_text = (prompt.video_prompt or "").strip()
    if not prompt_text:
        raise RuntimeError(f"第 {scene_index + 1} 个场景缺少有效视频提示词")

    return Scene(
        project_id=project_id,
        sequence_order=scene_index,
        title=_resolve_scene_title(prompt, narrative, scene_index=scene_index),
        description=narrative.narrative if narrative else "",
        video_prompt=prompt_text,
        negative_prompt=prompt.negative_prompt,
        camera_movement=prompt.camera_movement,
        setting=narrative.setting if narrative else "",
        style_keywords=prompt.style_keywords,
        dialogue=narrative.dialogue if narrative else None,
        duration_seconds=_normalize_scene_duration(prompt.duration_seconds, max_duration=max_duration),
        transition_hint=_normalize_transition_hint(prompt.transition_hint, scene_index=scene_index),
        status=SCENE_STATUS_PENDING,
    )


async def _mark_project_parsed(project_id: str, db: AsyncSession) -> None:
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
    project.status = PROJECT_STATUS_PARSED
    await db.flush()


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

    async def analyze_narrative(self, script_text: str) -> NarrativeAnalysis:
        """第一阶段：叙事结构分析"""
        max_sec = int(settings.video_provider_max_duration_seconds)
        messages = [
            Message(role="system", content=NARRATIVE_ANALYSIS_SYSTEM.format(max_scene_seconds=max_sec)),
            Message(role="user", content=NARRATIVE_ANALYSIS_USER.format(
                script_text=script_text,
                max_scene_seconds=max_sec,
            )),
        ]
        result = await self._complete_with_retry(
            messages=messages,
            response_format=NarrativeAnalysis,
            temperature=0.3,
            attempt_label="叙事分析",
            failure_label="叙事分析失败",
        )
        return NarrativeAnalysis.model_validate(result)

    async def generate_scene_prompts(self, analysis: NarrativeAnalysis) -> list[ScenePrompt]:
        """第二阶段：为每个场景生成视频提示词"""
        max_sec = int(settings.video_provider_max_duration_seconds)

        messages = [
            Message(role="system", content=PROMPT_GENERATION_SYSTEM.format(max_scene_seconds=max_sec)),
            Message(role="user", content=PROMPT_GENERATION_USER.format(
                global_style=_format_global_style(analysis.global_style),
                characters_info=_format_characters_info(analysis.characters),
                scenes_info=_format_scenes_info(analysis.scenes),
                max_scene_seconds=max_sec,
            )),
        ]
        result = await self._complete_with_retry(
            messages=messages,
            response_format=ScenePromptsResult,
            temperature=0.5,
            attempt_label="提示词生成",
            failure_label="提示词生成失败",
        )
        return ScenePromptsResult.model_validate(result).scenes

    async def parse_script(self, project_id: str, script_text: str, db: AsyncSession) -> ParseResult:
        """完整解析流程：分析 → 生成 → 持久化"""
        _publish_parse_progress(project_id, "正在进行叙事分析...", 10)

        # 第一阶段：叙事分析
        analysis = await self.analyze_narrative(script_text)
        _publish_parse_progress(project_id, "叙事分析完成，正在生成场景提示词...", 35)

        # 第二阶段：生成视频提示词
        scene_prompts = await self.generate_scene_prompts(analysis)
        _publish_parse_progress(project_id, "提示词生成完成，正在写入角色与场景...", 60)
        _validate_scene_prompts(scene_prompts, analysis)

        # 清理旧数据
        await _clear_project_storyboard_data(project_id, db)
        _publish_parse_progress(project_id, "历史数据已清理，正在创建角色...", 72)

        # 持久化角色
        char_map = await _persist_characters(project_id, analysis.characters, db)
        _publish_parse_progress(project_id, "角色创建完成，正在写入场景...", 82)

        # 持久化场景
        max_duration = settings.video_provider_max_duration_seconds
        for i, sp in enumerate(scene_prompts):
            narrative = analysis.scenes[i] if i < len(analysis.scenes) else None
            scene = _build_scene_entity(
                project_id=project_id,
                scene_index=i,
                prompt=sp,
                narrative=narrative,
                max_duration=max_duration,
            )
            db.add(scene)
            await db.flush()

            # 关联角色
            await _link_scene_characters(scene, narrative, char_map, db)

            percent = 82 + round(((i + 1) / max(1, len(scene_prompts))) * 14)
            _publish_parse_progress(project_id, f"正在写入场景 {i + 1}/{len(scene_prompts)}...", percent)

        # 更新项目状态
        await _mark_project_parsed(project_id, db)
        _publish_parse_progress(project_id, "正在收尾并更新项目状态...", 98)

        return ParseResult(
            character_count=len(char_map),
            panel_count=len(scene_prompts),
        )
