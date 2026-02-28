from __future__ import annotations

import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.llm.base import LLMAdapter, Message
from app.models import Character, Project, Scene, SceneCharacter
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
    scene_count: int


class ScriptParserService:
    """剧本解析服务：两阶段 LLM 分析"""

    def __init__(self, llm: LLMAdapter):
        self._llm = llm

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

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._llm.complete(messages, response_format=NarrativeAnalysis, temperature=0.3)
                data = extract_json_object(response.content)
                return NarrativeAnalysis.model_validate(data)
            except Exception as e:
                logger.warning("叙事分析第 %d 次尝试失败: %s", attempt + 1, e)
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(f"叙事分析失败（已重试 {MAX_RETRIES} 次）: {e}") from e

        raise RuntimeError("叙事分析失败")  # 不可达

    async def generate_scene_prompts(self, analysis: NarrativeAnalysis) -> list[ScenePrompt]:
        """第二阶段：为每个场景生成视频提示词"""
        max_sec = int(settings.video_provider_max_duration_seconds)

        global_style = (
            f"风格: {analysis.global_style.visual_style}, "
            f"色调: {analysis.global_style.color_tone}, "
            f"时代: {analysis.global_style.era}, "
            f"氛围: {analysis.global_style.mood}"
        )

        characters_info = "\n".join(
            f"- {c.name}: 外貌={c.appearance}, 服装={c.costume}"
            for c in analysis.characters
        )

        scenes_info = "\n".join(
            f"场景{i+1} [{s.title}]: {s.narrative} (环境: {s.setting}, 氛围: {s.mood}, "
            f"角色: {', '.join(s.character_names)}, 时长: {s.estimated_duration}秒"
            f"{', 台词: ' + s.dialogue if s.dialogue else ''})"
            for i, s in enumerate(analysis.scenes)
        )

        messages = [
            Message(role="system", content=PROMPT_GENERATION_SYSTEM.format(max_scene_seconds=max_sec)),
            Message(role="user", content=PROMPT_GENERATION_USER.format(
                global_style=global_style,
                characters_info=characters_info,
                scenes_info=scenes_info,
                max_scene_seconds=max_sec,
            )),
        ]

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._llm.complete(messages, response_format=ScenePromptsResult, temperature=0.5)
                data = extract_json_object(response.content)
                result = ScenePromptsResult.model_validate(data)
                return result.scenes
            except Exception as e:
                logger.warning("提示词生成第 %d 次尝试失败: %s", attempt + 1, e)
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(f"提示词生成失败（已重试 {MAX_RETRIES} 次）: {e}") from e

        raise RuntimeError("提示词生成失败")  # 不可达

    async def parse_script(self, project_id: str, script_text: str, db: AsyncSession) -> ParseResult:
        """完整解析流程：分析 → 生成 → 持久化"""
        publish_progress(project_id, "parse_progress", {"message": "正在进行叙事分析...", "percent": 10})

        # 第一阶段：叙事分析
        analysis = await self.analyze_narrative(script_text)
        publish_progress(project_id, "parse_progress", {"message": "叙事分析完成，正在生成场景提示词...", "percent": 35})

        # 第二阶段：生成视频提示词
        scene_prompts = await self.generate_scene_prompts(analysis)
        publish_progress(project_id, "parse_progress", {"message": "提示词生成完成，正在写入角色与场景...", "percent": 60})
        if not scene_prompts:
            raise RuntimeError("未生成任何场景提示词，请检查剧本内容后重试")
        if len(scene_prompts) != len(analysis.scenes):
            raise RuntimeError(
                f"提示词场景数({len(scene_prompts)})与叙事场景数({len(analysis.scenes)})不一致，请重试解析"
            )

        # 清理旧数据
        old_scenes = (await db.execute(select(Scene).where(Scene.project_id == project_id))).scalars().all()
        for s in old_scenes:
            await db.delete(s)
        old_chars = (await db.execute(select(Character).where(Character.project_id == project_id))).scalars().all()
        for c in old_chars:
            await db.delete(c)
        await mark_completed_compositions_stale(db, project_id)
        await db.flush()
        publish_progress(project_id, "parse_progress", {"message": "历史数据已清理，正在创建角色...", "percent": 72})

        # 持久化角色
        char_map: dict[str, Character] = {}
        for cp in analysis.characters:
            normalized_name = (cp.name or "").strip()
            if not normalized_name:
                raise RuntimeError("角色姓名不能为空")
            if normalized_name in char_map:
                raise RuntimeError(f"角色姓名重复: {normalized_name}")

            character = Character(
                project_id=project_id,
                name=normalized_name,
                appearance=cp.appearance,
                personality=cp.personality,
                costume=cp.costume,
            )
            db.add(character)
            char_map[normalized_name] = character
        await db.flush()
        publish_progress(project_id, "parse_progress", {"message": "角色创建完成，正在写入场景...", "percent": 82})

        # 持久化场景
        max_duration = settings.video_provider_max_duration_seconds
        for i, sp in enumerate(scene_prompts):
            prompt_text = (sp.video_prompt or "").strip()
            if not prompt_text:
                raise RuntimeError(f"第 {i + 1} 个场景缺少有效视频提示词")

            duration_seconds = min(max(0.1, float(sp.duration_seconds)), max_duration)
            transition_hint = (sp.transition_hint or "crossfade").strip().lower()
            if transition_hint not in ALLOWED_TRANSITIONS:
                logger.warning("场景 %d 的 transition_hint=%s 非法，已回退为 crossfade", i + 1, sp.transition_hint)
                transition_hint = "crossfade"

            # 从叙事分析中获取对应场景的元数据
            narrative = analysis.scenes[i] if i < len(analysis.scenes) else None
            title = (sp.title or "").strip()
            if not title and narrative:
                title = (narrative.title or "").strip()
            if not title:
                title = f"场景 {i + 1}"

            scene = Scene(
                project_id=project_id,
                sequence_order=i,
                title=title,
                description=narrative.narrative if narrative else "",
                video_prompt=prompt_text,
                negative_prompt=sp.negative_prompt,
                camera_movement=sp.camera_movement,
                setting=narrative.setting if narrative else "",
                style_keywords=sp.style_keywords,
                dialogue=narrative.dialogue if narrative else None,
                duration_seconds=duration_seconds,
                transition_hint=transition_hint,
                status=SCENE_STATUS_PENDING,
            )
            db.add(scene)
            await db.flush()

            # 关联角色
            if narrative:
                linked_character_ids: set[str] = set()
                for raw_char_name in narrative.character_names:
                    char_name = (raw_char_name or "").strip()
                    if char_name in char_map:
                        character_id = char_map[char_name].id
                        if character_id in linked_character_ids:
                            continue

                        action = ""
                        if isinstance(raw_char_name, str):
                            action = narrative.character_actions.get(raw_char_name, "")
                        if not action:
                            action = narrative.character_actions.get(char_name, "")
                        sc = SceneCharacter(
                            scene_id=scene.id,
                            character_id=character_id,
                            action=action,
                        )
                        db.add(sc)
                        linked_character_ids.add(character_id)

            percent = 82 + round(((i + 1) / max(1, len(scene_prompts))) * 14)
            publish_progress(
                project_id,
                "parse_progress",
                {"message": f"正在写入场景 {i + 1}/{len(scene_prompts)}...", "percent": percent},
            )

        # 更新项目状态
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = PROJECT_STATUS_PARSED
        await db.flush()
        publish_progress(project_id, "parse_progress", {"message": "正在收尾并更新项目状态...", "percent": 98})

        return ParseResult(
            character_count=len(char_map),
            scene_count=len(scene_prompts),
        )
