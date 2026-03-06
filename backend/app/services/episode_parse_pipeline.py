from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.episode_status import EPISODE_STATUS_DRAFT
from app.llm.base import LLMAdapter
from app.models import Character, Episode, Panel, Project, Scene, SceneCharacter
from app.panel_status import PANEL_STATUS_PENDING
from app.project_status import PROJECT_STATUS_PARSED
from app.scene_status import SCENE_STATUS_PENDING
from app.services.composition_state import mark_completed_compositions_stale
from app.services.progress import publish_progress
from app.services.script_parser import ALLOWED_TRANSITIONS, NarrativeAnalysis, ScenePrompt, ScriptParserService


@dataclass(slots=True)
class EpisodeParseInput:
    title: str
    summary: str | None
    script_text: str | None
    status: str


@dataclass(slots=True)
class EpisodeParseWork:
    plan: EpisodeParseInput
    analysis: NarrativeAnalysis | None
    prompts: list[ScenePrompt]


@dataclass(slots=True)
class EpisodeParseResult:
    character_count: int
    panel_count: int
    episode_count: int


def _normalize_episode_title(raw_title: str | None, index: int) -> str:
    title = (raw_title or "").strip()
    return title or f"第{index + 1}集"


def _merge_character_field(current_value: str, next_value: str | None) -> str:
    if current_value.strip():
        return current_value.strip()
    return (next_value or "").strip()


async def _build_episode_inputs(
    project_id: str,
    project_script_text: str,
    db: AsyncSession,
) -> list[EpisodeParseInput]:
    existing = (await db.execute(
        select(Episode)
        .where(Episode.project_id == project_id)
        .order_by(Episode.episode_order, Episode.created_at)
    )).scalars().all()

    if existing:
        plans = [
            EpisodeParseInput(
                title=_normalize_episode_title(item.title, idx),
                summary=(item.summary or "").strip() or None,
                script_text=(item.script_text or "").strip() or None,
                status=(item.status or EPISODE_STATUS_DRAFT).strip() or EPISODE_STATUS_DRAFT,
            )
            for idx, item in enumerate(existing)
        ]
        if any((plan.script_text or "").strip() for plan in plans):
            return plans

    fallback_text = (project_script_text or "").strip()
    if not fallback_text:
        return []
    return [
        EpisodeParseInput(
            title="第1集",
            summary=fallback_text[:80],
            script_text=fallback_text,
            status=EPISODE_STATUS_DRAFT,
        )
    ]


async def parse_project_from_episodes(
    project_id: str,
    project_script_text: str,
    llm: LLMAdapter,
    db: AsyncSession,
) -> EpisodeParseResult:
    episode_inputs = await _build_episode_inputs(project_id, project_script_text, db)
    if not episode_inputs:
        raise RuntimeError("剧本内容为空，无法解析")

    parser = ScriptParserService(llm)
    total_episodes = len(episode_inputs)
    works: list[EpisodeParseWork] = []

    for episode_index, plan in enumerate(episode_inputs):
        script = (plan.script_text or "").strip()
        if not script:
            works.append(EpisodeParseWork(plan=plan, analysis=None, prompts=[]))
            continue

        progress_base = 8 + int((episode_index / max(1, total_episodes)) * 40)
        publish_progress(project_id, "parse_progress", {
            "message": f"正在解析第 {episode_index + 1}/{total_episodes} 集叙事结构...",
            "percent": progress_base,
        })
        analysis = await parser.analyze_narrative(script)

        publish_progress(project_id, "parse_progress", {
            "message": f"正在生成第 {episode_index + 1}/{total_episodes} 集分镜提示词...",
            "percent": min(70, progress_base + 12),
        })
        prompts = await parser.generate_scene_prompts(analysis)
        if not prompts:
            raise RuntimeError(f"第 {episode_index + 1} 集未生成任何分镜提示词")
        if len(prompts) != len(analysis.scenes):
            raise RuntimeError(
                f"第 {episode_index + 1} 集提示词数量({len(prompts)})与叙事场景数({len(analysis.scenes)})不一致"
            )
        works.append(EpisodeParseWork(plan=plan, analysis=analysis, prompts=prompts))

    panel_count = sum(len(item.prompts) for item in works)
    if panel_count <= 0:
        raise RuntimeError("未生成任何分镜提示词，请检查剧本内容后重试")

    publish_progress(project_id, "parse_progress", {
        "message": "正在清理历史解析数据...",
        "percent": 72,
    })
    await db.execute(delete(Scene).where(Scene.project_id == project_id))
    await db.execute(delete(Panel).where(Panel.project_id == project_id))
    await db.execute(delete(Episode).where(Episode.project_id == project_id))
    await db.execute(delete(Character).where(Character.project_id == project_id))
    await mark_completed_compositions_stale(db, project_id)
    await db.flush()

    publish_progress(project_id, "parse_progress", {
        "message": "正在汇总角色并写入分集与分镜...",
        "percent": 80,
    })
    character_profiles: dict[str, dict[str, str]] = {}
    for work in works:
        if work.analysis is None:
            continue
        for character in work.analysis.characters:
            name = (character.name or "").strip()
            if not name:
                continue
            bucket = character_profiles.setdefault(name, {"appearance": "", "personality": "", "costume": ""})
            bucket["appearance"] = _merge_character_field(bucket["appearance"], character.appearance)
            bucket["personality"] = _merge_character_field(bucket["personality"], character.personality)
            bucket["costume"] = _merge_character_field(bucket["costume"], character.costume)

    character_map: dict[str, Character] = {}
    for name, profile in character_profiles.items():
        entity = Character(
            project_id=project_id,
            name=name,
            appearance=profile["appearance"] or "",
            personality=profile["personality"] or "",
            costume=profile["costume"] or "",
        )
        db.add(entity)
        character_map[name] = entity

    max_duration = settings.video_provider_max_duration_seconds
    scene_sequence_order = 0
    for episode_index, work in enumerate(works):
        episode = Episode(
            project_id=project_id,
            episode_order=episode_index,
            title=_normalize_episode_title(work.plan.title, episode_index),
            summary=(work.plan.summary or "").strip() or None,
            script_text=(work.plan.script_text or "").strip() or None,
            status=(work.plan.status or EPISODE_STATUS_DRAFT).strip() or EPISODE_STATUS_DRAFT,
        )
        db.add(episode)

        for panel_index, prompt in enumerate(work.prompts):
            narrative = work.analysis.scenes[panel_index] if work.analysis and panel_index < len(work.analysis.scenes) else None
            title = (prompt.title or "").strip()
            if not title and narrative:
                title = (narrative.title or "").strip()
            if not title:
                title = f"分镜 {panel_index + 1}"

            visual_prompt = (prompt.video_prompt or "").strip()
            if not visual_prompt:
                raise RuntimeError(f"第 {episode_index + 1} 集第 {panel_index + 1} 个分镜缺少视频提示词")

            duration_seconds = min(max(0.1, float(prompt.duration_seconds or 5.0)), max_duration)
            transition_hint = (prompt.transition_hint or "crossfade").strip().lower()
            if transition_hint not in ALLOWED_TRANSITIONS:
                transition_hint = "crossfade"

            camera_hint = (prompt.camera_movement or "").strip()
            style_keywords = (prompt.style_keywords or "").strip()
            negative_prompt = (prompt.negative_prompt or "").strip()
            narrative_text = (narrative.narrative if narrative else "") or ""
            setting_text = (narrative.setting if narrative else "") or ""
            dialogue_text = (narrative.dialogue if narrative else "") or ""

            panel = Panel(
                project_id=project_id,
                episode=episode,
                panel_order=panel_index,
                title=title,
                script_text=narrative_text.strip() or None,
                visual_prompt=visual_prompt,
                negative_prompt=negative_prompt or None,
                camera_hint=(camera_hint[:200] if camera_hint else None),
                duration_seconds=duration_seconds,
                style_preset=(style_keywords[:100] if style_keywords else None),
                tts_text=dialogue_text.strip() or None,
                status=PANEL_STATUS_PENDING,
            )
            db.add(panel)

            scene = Scene(
                project_id=project_id,
                sequence_order=scene_sequence_order,
                title=title,
                description=narrative_text.strip() or None,
                video_prompt=visual_prompt,
                negative_prompt=negative_prompt or None,
                camera_movement=(camera_hint[:200] if camera_hint else None),
                setting=setting_text.strip() or None,
                style_keywords=(style_keywords[:500] if style_keywords else None),
                dialogue=dialogue_text.strip() or None,
                duration_seconds=duration_seconds,
                transition_hint=transition_hint,
                status=SCENE_STATUS_PENDING,
            )
            db.add(scene)

            if narrative:
                linked_character_names: set[str] = set()
                for raw_character_name in narrative.character_names:
                    normalized_name = (raw_character_name or "").strip()
                    if not normalized_name:
                        continue
                    character = character_map.get(normalized_name)
                    if character is None:
                        continue
                    if normalized_name in linked_character_names:
                        continue

                    action = ""
                    if isinstance(raw_character_name, str):
                        action = narrative.character_actions.get(raw_character_name, "")
                    if not action:
                        action = narrative.character_actions.get(normalized_name, "")

                    db.add(SceneCharacter(
                        scene=scene,
                        character=character,
                        action=(action or "").strip() or None,
                    ))
                    linked_character_names.add(normalized_name)

            scene_sequence_order += 1

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
    project.status = PROJECT_STATUS_PARSED
    await db.flush()

    publish_progress(project_id, "parse_progress", {
        "message": "解析结果已写入分集与分镜，正在完成收尾...",
        "percent": 98,
    })
    return EpisodeParseResult(
        character_count=len(character_map),
        panel_count=panel_count,
        episode_count=len(works),
    )
