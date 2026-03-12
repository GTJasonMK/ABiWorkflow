from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Episode, Panel, Project
from app.project_status import PROJECT_RESET_TO_DRAFT_ON_SCRIPT_CHANGE, PROJECT_STATUS_DRAFT
from app.services.composition_state import mark_completed_compositions_stale
from app.services.episode_workflow_config import (
    apply_episode_workflow_config,
    resolve_episode_update_workflow_config,
)
from app.services.project_workflow_defaults import (
    apply_project_workflow_defaults,
    read_project_workflow_defaults,
    resolve_project_workflow_defaults,
)

PANEL_EXISTS_BLOCK_DETAIL = "当前项目已存在分镜，禁止从剧本分集页覆盖分集结构"


class ProjectScriptWorkspaceConflictError(RuntimeError):
    """脚本分集工作台保存冲突。"""


@dataclass(slots=True)
class NormalizedEpisodeWorkspaceDraft:
    id: str | None
    title: str
    summary: str | None
    script_text: str
    workflow_config: dict[str, Any]


def _normalize_episode_title(raw_title: str | None, index: int) -> str:
    title = (raw_title or "").strip()
    return title[:200] if title else f"第{index + 1}集"


def _normalize_episode_summary(raw_summary: str | None) -> str | None:
    return (raw_summary or "").strip() or None


def _normalize_episode_script_text(raw_script_text: str | None) -> str:
    return (raw_script_text or "").strip()


def _normalize_project_script_text(raw_script_text: str | None) -> str:
    return (raw_script_text or "").strip()


async def assert_project_script_workspace_syncable(project_id: str, db: AsyncSession) -> None:
    has_panel = (await db.execute(
        select(Panel.id).where(Panel.project_id == project_id).limit(1)
    )).scalar_one_or_none()
    if has_panel is not None:
        raise ProjectScriptWorkspaceConflictError(PANEL_EXISTS_BLOCK_DETAIL)


async def _normalize_episode_workspace_drafts(
    db: AsyncSession,
    *,
    raw_episodes: list[dict[str, Any]],
) -> list[NormalizedEpisodeWorkspaceDraft]:
    normalized: list[NormalizedEpisodeWorkspaceDraft] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw_episodes):
        episode_id = str(item.get("id") or "").strip() or None
        if episode_id:
            if episode_id in seen_ids:
                raise ValueError(f"episodes 存在重复 id: {episode_id}")
            seen_ids.add(episode_id)

        script_text = _normalize_episode_script_text(item.get("script_text"))
        if not script_text:
            continue

        workflow_config = await resolve_episode_update_workflow_config(db, raw_updates={
            "video_provider_key": item.get("video_provider_key"),
            "tts_provider_key": item.get("tts_provider_key"),
            "lipsync_provider_key": item.get("lipsync_provider_key"),
            "provider_payload_defaults": item.get("provider_payload_defaults") or {},
            "skipped_checks": item.get("skipped_checks") or [],
        })
        normalized.append(NormalizedEpisodeWorkspaceDraft(
            id=episode_id,
            title=_normalize_episode_title(item.get("title"), index),
            summary=_normalize_episode_summary(item.get("summary")),
            script_text=script_text,
            workflow_config=workflow_config,
        ))
    if not normalized:
        raise ValueError("至少需要一个包含正文的分集")
    return normalized


async def sync_project_script_workspace(
    db: AsyncSession,
    *,
    project: Project,
    raw_script_text: str | None,
    raw_workflow_defaults: dict[str, Any] | None,
    raw_episodes: list[dict[str, Any]],
) -> None:
    await assert_project_script_workspace_syncable(project.id, db)

    script_text = _normalize_project_script_text(raw_script_text)
    if not script_text:
        raise ValueError("项目剧本文本不能为空")

    workflow_defaults = await resolve_project_workflow_defaults(
        db,
        raw_workflow_defaults,
        base_defaults=read_project_workflow_defaults(project),
        clear_when_none=True,
    )
    normalized_episodes = await _normalize_episode_workspace_drafts(db, raw_episodes=raw_episodes)

    existing_episodes = (await db.execute(
        select(Episode).where(Episode.project_id == project.id)
    )).scalars().all()
    existing_episode_map = {episode.id: episode for episode in existing_episodes}

    for item in normalized_episodes:
        if item.id is not None and item.id not in existing_episode_map:
            raise ValueError(f"分集不存在或不属于当前项目: {item.id}")

    script_text_changed = script_text != (project.script_text or "").strip()
    project.script_text = script_text
    apply_project_workflow_defaults(project, workflow_defaults)
    if script_text_changed and project.status in PROJECT_RESET_TO_DRAFT_ON_SCRIPT_CHANGE:
        project.status = PROJECT_STATUS_DRAFT
    if script_text_changed:
        await mark_completed_compositions_stale(db, project.id)

    keep_ids: set[str] = set()
    for index, item in enumerate(normalized_episodes):
        episode = existing_episode_map.get(item.id) if item.id is not None else None
        if episode is None:
            episode = Episode(
                project_id=project.id,
                episode_order=index,
                title=item.title,
                summary=item.summary,
                script_text=item.script_text,
            )
            db.add(episode)
            await db.flush()
            existing_episode_map[episode.id] = episode
        else:
            episode.episode_order = index
            episode.title = item.title
            episode.summary = item.summary
            episode.script_text = item.script_text
        apply_episode_workflow_config(episode, item.workflow_config)
        keep_ids.add(episode.id)

    for episode in existing_episodes:
        if episode.id not in keep_ids:
            await db.delete(episode)
