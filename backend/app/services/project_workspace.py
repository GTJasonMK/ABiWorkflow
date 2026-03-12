from __future__ import annotations

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.project_common import get_project_aggregate_counts, to_project_response
from app.api.response_utils import isoformat_or_empty
from app.clip_status import CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED
from app.composition_status import COMPOSITION_STATUS_COMPLETED
from app.models import (
    CompositionTask,
    Episode,
    GlobalVoice,
    Panel,
    Project,
    ScriptEntity,
    ScriptEntityAssetBinding,
    VideoClip,
)
from app.schemas.project import (
    ProjectWorkspacePreview,
    ProjectWorkspaceResourceSummary,
    ProjectWorkspaceResponse,
)
from app.services.episode_response_builder import build_episode_responses


async def build_project_workspace(project: Project, db: AsyncSession) -> ProjectWorkspaceResponse:
    counts = await get_project_aggregate_counts(project.id, db)
    project_payload = to_project_response(
        project,
        character_count=counts.character_count,
        episode_count=counts.episode_count,
        panel_count=counts.panel_count,
        generated_panel_count=counts.generated_panel_count,
    )

    episodes = (await db.execute(
        select(Episode).where(Episode.project_id == project.id).order_by(Episode.episode_order, Episode.created_at)
    )).scalars().all()
    panel_count_rows = (await db.execute(
        select(Panel.episode_id, func.count(Panel.id))
        .where(Panel.project_id == project.id)
        .group_by(Panel.episode_id)
    )).all()
    panel_count_map = {episode_id: int(count or 0) for episode_id, count in panel_count_rows}
    episode_payloads = await build_episode_responses(episodes, db=db, panel_count_map=panel_count_map)

    entities = (await db.execute(
        select(ScriptEntity.id, ScriptEntity.entity_type).where(ScriptEntity.project_id == project.id)
    )).all()
    entity_type_map = {entity_id: entity_type for entity_id, entity_type in entities}
    bindings = (await db.execute(
        select(ScriptEntityAssetBinding.entity_id, ScriptEntityAssetBinding.asset_type)
        .where(ScriptEntityAssetBinding.project_id == project.id)
    )).all()

    entity_counts = {"character": 0, "location": 0}
    for _, entity_type in entities:
        if entity_type in entity_counts:
            entity_counts[entity_type] += 1
    bound_entity_sets = {"character": set(), "location": set()}
    for entity_id, asset_type in bindings:
        entity_type = entity_type_map.get(entity_id)
        if entity_type and entity_type == asset_type and entity_type in bound_entity_sets:
            bound_entity_sets[entity_type].add(entity_id)

    voice_asset_count = (await db.execute(
        select(func.count(GlobalVoice.id)).where(
            or_(GlobalVoice.project_id.is_(None), GlobalVoice.project_id == project.id)
        )
    )).scalar() or 0
    clip_summary = (await db.execute(
        select(
            func.count(VideoClip.id),
            func.sum(case((VideoClip.status == CLIP_STATUS_COMPLETED, 1), else_=0)),
            func.sum(case((VideoClip.status == CLIP_STATUS_FAILED, 1), else_=0)),
        )
        .select_from(VideoClip)
        .join(Panel, Panel.id == VideoClip.panel_id)
        .where(Panel.project_id == project.id)
    )).one()
    clip_count = int(clip_summary[0] or 0)
    ready_clip_count = int(clip_summary[1] or 0)
    failed_clip_count = int(clip_summary[2] or 0)

    composition_count = (await db.execute(
        select(func.count(CompositionTask.id)).where(
            CompositionTask.project_id == project.id,
            CompositionTask.status == COMPOSITION_STATUS_COMPLETED,
        )
    )).scalar() or 0
    latest_preview_row = (await db.execute(
        select(CompositionTask)
        .where(
            CompositionTask.project_id == project.id,
            CompositionTask.status == COMPOSITION_STATUS_COMPLETED,
        )
        .order_by(CompositionTask.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()

    recommended_episode_id: str | None = None
    recommended_step = "script"
    for episode in episode_payloads:
        recommended_step = str(episode.workflow_summary.get("current_step") or "script")
        if recommended_step == "preview" and bool(episode.workflow_summary.get("checks", {}).get("composed")):
            continue
        recommended_episode_id = episode.id if recommended_step != "script" else None
        break
    if recommended_episode_id is None and episode_payloads:
        first_episode = episode_payloads[0]
        fallback_step = str(first_episode.workflow_summary.get("current_step") or "script")
        recommended_step = fallback_step
        if fallback_step != "script":
            recommended_episode_id = first_episode.id

    latest_preview = None if latest_preview_row is None else ProjectWorkspacePreview(
        id=latest_preview_row.id,
        status=latest_preview_row.status,
        duration_seconds=float(latest_preview_row.duration_seconds or 0),
        created_at=isoformat_or_empty(latest_preview_row.created_at),
        updated_at=isoformat_or_empty(latest_preview_row.updated_at),
    )

    return ProjectWorkspaceResponse(
        project=project_payload,
        episodes=episode_payloads,
        resource_summary=ProjectWorkspaceResourceSummary(
            character_entity_count=entity_counts["character"],
            bound_character_entity_count=len(bound_entity_sets["character"]),
            location_entity_count=entity_counts["location"],
            bound_location_entity_count=len(bound_entity_sets["location"]),
            voice_asset_count=int(voice_asset_count or 0),
            panel_count=counts.panel_count,
            clip_count=clip_count,
            ready_clip_count=ready_clip_count,
            failed_clip_count=failed_clip_count,
            composition_count=int(composition_count or 0),
        ),
        latest_preview=latest_preview,
        recommended_episode_id=recommended_episode_id,
        recommended_step=recommended_step,
    )
