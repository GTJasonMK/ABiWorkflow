from __future__ import annotations

import json
import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.base import LLMAdapter, Message
from app.models import Character, Project, Scene, SceneCharacter
from app.prompts.narrative_analysis import NARRATIVE_ANALYSIS_SYSTEM, NARRATIVE_ANALYSIS_USER
from app.prompts.prompt_generation import PROMPT_GENERATION_SYSTEM, PROMPT_GENERATION_USER

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
        messages = [
            Message(role="system", content=NARRATIVE_ANALYSIS_SYSTEM),
            Message(role="user", content=NARRATIVE_ANALYSIS_USER.format(script_text=script_text)),
        ]

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._llm.complete(messages, response_format=NarrativeAnalysis, temperature=0.3)
                data = _extract_json(response.content)
                return NarrativeAnalysis.model_validate(data)
            except Exception as e:
                logger.warning("叙事分析第 %d 次尝试失败: %s", attempt + 1, e)
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(f"叙事分析失败（已重试 {MAX_RETRIES} 次）: {e}") from e

        raise RuntimeError("叙事分析失败")  # 不可达

    async def generate_scene_prompts(self, analysis: NarrativeAnalysis) -> list[ScenePrompt]:
        """第二阶段：为每个场景生成视频提示词"""
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
            Message(role="system", content=PROMPT_GENERATION_SYSTEM),
            Message(role="user", content=PROMPT_GENERATION_USER.format(
                global_style=global_style,
                characters_info=characters_info,
                scenes_info=scenes_info,
            )),
        ]

        for attempt in range(MAX_RETRIES):
            try:
                response = await self._llm.complete(messages, response_format=ScenePromptsResult, temperature=0.5)
                data = _extract_json(response.content)
                result = ScenePromptsResult.model_validate(data)
                return result.scenes
            except Exception as e:
                logger.warning("提示词生成第 %d 次尝试失败: %s", attempt + 1, e)
                if attempt == MAX_RETRIES - 1:
                    raise RuntimeError(f"提示词生成失败（已重试 {MAX_RETRIES} 次）: {e}") from e

        raise RuntimeError("提示词生成失败")  # 不可达

    async def parse_script(self, project_id: str, script_text: str, db: AsyncSession) -> ParseResult:
        """完整解析流程：分析 → 生成 → 持久化"""
        # 第一阶段：叙事分析
        analysis = await self.analyze_narrative(script_text)

        # 第二阶段：生成视频提示词
        scene_prompts = await self.generate_scene_prompts(analysis)
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
        await db.flush()

        # 持久化角色
        char_map: dict[str, Character] = {}
        for cp in analysis.characters:
            character = Character(
                project_id=project_id,
                name=cp.name,
                appearance=cp.appearance,
                personality=cp.personality,
                costume=cp.costume,
            )
            db.add(character)
            char_map[cp.name] = character
        await db.flush()

        # 持久化场景
        for i, sp in enumerate(scene_prompts):
            prompt_text = (sp.video_prompt or "").strip()
            if not prompt_text:
                raise RuntimeError(f"第 {i + 1} 个场景缺少有效视频提示词")

            duration_seconds = max(0.1, float(sp.duration_seconds))
            transition_hint = (sp.transition_hint or "crossfade").strip().lower()
            if transition_hint not in ALLOWED_TRANSITIONS:
                logger.warning("场景 %d 的 transition_hint=%s 非法，已回退为 crossfade", i + 1, sp.transition_hint)
                transition_hint = "crossfade"

            # 从叙事分析中获取对应场景的元数据
            narrative = analysis.scenes[i] if i < len(analysis.scenes) else None

            scene = Scene(
                project_id=project_id,
                sequence_order=i,
                title=sp.title,
                description=narrative.narrative if narrative else "",
                video_prompt=prompt_text,
                negative_prompt=sp.negative_prompt,
                camera_movement=sp.camera_movement,
                setting=narrative.setting if narrative else "",
                style_keywords=sp.style_keywords,
                dialogue=narrative.dialogue if narrative else None,
                duration_seconds=duration_seconds,
                transition_hint=transition_hint,
                status="pending",
            )
            db.add(scene)
            await db.flush()

            # 关联角色
            if narrative:
                for char_name in narrative.character_names:
                    if char_name in char_map:
                        action = narrative.character_actions.get(char_name, "")
                        sc = SceneCharacter(
                            scene_id=scene.id,
                            character_id=char_map[char_name].id,
                            action=action,
                        )
                        db.add(sc)

        # 更新项目状态
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.status = "parsed"
        await db.flush()

        return ParseResult(
            character_count=len(char_map),
            scene_count=len(scene_prompts),
        )


def _extract_json(text: str) -> dict:
    """从 LLM 输出中提取 JSON（处理可能的 markdown 代码块包裹）"""
    text = text.strip()
    if text.startswith("```"):
        # 去除 markdown 代码块
        lines = text.split("\n")
        # 跳过第一行（```json）和最后一行（```）
        json_lines = []
        in_block = False
        for line in lines:
            if line.strip().startswith("```") and not in_block:
                in_block = True
                continue
            if line.strip() == "```" and in_block:
                break
            if in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)

    return json.loads(text)
