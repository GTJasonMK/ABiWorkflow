from __future__ import annotations

import math
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clip_status import CLIP_STATUS_COMPLETED, CLIP_STATUS_FAILED
from app.config import resolve_runtime_path, settings
from app.episode_status import EPISODE_STATUS_DRAFT
from app.models import Character, Episode, Panel, PanelEffectiveBinding, Scene, VideoClip
from app.panel_status import (
    PANEL_STATUS_COMPLETED,
    PANEL_STATUS_FAILED,
    PANEL_STATUS_PENDING,
    PANEL_STATUS_PROCESSING,
)
from app.scene_status import (
    SCENE_STATUS_FAILED,
    SCENE_STATUS_GENERATED,
    SCENE_STATUS_GENERATING,
    SCENE_STATUS_PENDING,
)
from app.services.json_codec import from_json_text


def _safe_weight(value: str | None) -> float:
    text = (value or "").strip()
    if not text:
        return 1.0
    return float(max(1, len(text)))


def _distribute_item_counts(total_items: int, weights: list[float]) -> list[int]:
    bucket_count = len(weights)
    if bucket_count <= 0:
        return []
    if total_items <= 0:
        return [0] * bucket_count

    normalized = [max(0.0, float(weight)) for weight in weights]
    if sum(normalized) <= 0:
        normalized = [1.0] * bucket_count

    total_weight = sum(normalized)
    raw = [total_items * (weight / total_weight) for weight in normalized]
    counts = [int(math.floor(item)) for item in raw]
    remainder = total_items - sum(counts)
    if remainder > 0:
        order = sorted(
            range(bucket_count),
            key=lambda idx: (raw[idx] - counts[idx], normalized[idx], -idx),
            reverse=True,
        )
        for idx in range(remainder):
            counts[order[idx % bucket_count]] += 1

    # 只要项目数足够，尽量保证每个桶至少分到一项，避免全挤在前几个桶里。
    if total_items >= bucket_count:
        empty_indices = [idx for idx, count in enumerate(counts) if count <= 0]
        for target in empty_indices:
            donor = max(range(bucket_count), key=lambda idx: counts[idx])
            if counts[donor] <= 1:
                break
            counts[donor] -= 1
            counts[target] += 1

    # 防御性修正，确保总量精确一致。
    delta = total_items - sum(counts)
    if delta > 0:
        counts[-1] += delta
    elif delta < 0:
        counts[-1] = max(0, counts[-1] + delta)
    return counts


def _clip_to_media_url(file_path: str | None) -> str | None:
    if not file_path:
        return None
    resolved = Path(file_path)
    if not resolved.is_absolute():
        resolved = resolve_runtime_path(resolved)
    root = resolve_runtime_path(settings.video_output_dir)
    try:
        relative = resolved.relative_to(root).as_posix()
        return f"/media/videos/{relative}"
    except ValueError:
        return None


def _scene_status_from_panel(panel: Panel) -> str:
    if panel.status == PANEL_STATUS_COMPLETED:
        return SCENE_STATUS_GENERATED
    if panel.status == PANEL_STATUS_FAILED:
        return SCENE_STATUS_FAILED
    if panel.status == PANEL_STATUS_PROCESSING:
        return SCENE_STATUS_GENERATING
    return SCENE_STATUS_PENDING


def _panel_status_from_scene(scene: Scene) -> str:
    if scene.status in {SCENE_STATUS_GENERATED, "completed"}:
        return PANEL_STATUS_COMPLETED
    if scene.status == SCENE_STATUS_FAILED:
        return PANEL_STATUS_FAILED
    if scene.status == SCENE_STATUS_GENERATING:
        return PANEL_STATUS_PROCESSING
    return PANEL_STATUS_PENDING


def _build_episode_from_blueprint(project_id: str, index: int, blueprint: dict[str, str | None]) -> Episode:
    return Episode(
        project_id=project_id,
        episode_order=index,
        title=(blueprint.get("title") or f"第{index + 1}集"),
        summary=blueprint.get("summary"),
        script_text=blueprint.get("script_text"),
        status=(blueprint.get("status") or EPISODE_STATUS_DRAFT),
    )


def _build_panel_from_scene(
    scene: Scene,
    *,
    project_id: str,
    episode_id: str,
    panel_order: int,
    default_title: str,
) -> Panel:
    return Panel(
        project_id=project_id,
        episode_id=episode_id,
        panel_order=panel_order,
        title=scene.title or default_title,
        script_text=(scene.description or "").strip() or None,
        visual_prompt=(scene.video_prompt or "").strip() or None,
        negative_prompt=(scene.negative_prompt or "").strip() or None,
        camera_hint=(scene.camera_movement or "").strip() or None,
        duration_seconds=max(0.1, float(scene.duration_seconds or 5.0)),
        style_preset=(scene.style_keywords or "").strip() or None,
        tts_text=(scene.dialogue or "").strip() or None,
        status=_panel_status_from_scene(scene),
    )


def _apply_panel_metadata_to_scene(
    scene: Scene,
    panel: Panel,
    index: int,
    effective_binding: dict | None,
    default_reference_image: str | None,
) -> None:
    effective = effective_binding or {}
    effective_prompt = effective.get("effective_visual_prompt") if isinstance(effective, dict) else None
    effective_ref = effective.get("effective_reference_image_url") if isinstance(effective, dict) else None
    effective_tts = effective.get("effective_tts_text") if isinstance(effective, dict) else None

    scene.sequence_order = index
    scene.title = (panel.title or "").strip() or f"场景 {index + 1}"
    scene.description = (panel.script_text or "").strip() or None
    scene.video_prompt = (
        str(effective_prompt or panel.visual_prompt or panel.script_text or panel.title or "").strip() or None
    )
    scene.negative_prompt = (panel.negative_prompt or "").strip() or None
    scene.camera_movement = (panel.camera_hint or "").strip() or None
    # 复用 setting 字段透传参考图 URL，供生成器兜底读取。
    scene.setting = (str(effective_ref or panel.reference_image_url or default_reference_image or "").strip() or None)
    scene.style_keywords = (panel.style_preset or "").strip() or None
    scene.dialogue = (str(effective_tts or panel.tts_text or "").strip() or None)
    scene.duration_seconds = max(0.1, float(panel.duration_seconds or 5.0))
    if scene.transition_hint not in {"none", "cut", "crossfade", "fade_black"}:
        scene.transition_hint = "crossfade"


async def list_project_panels_ordered(project_id: str, db: AsyncSession) -> list[Panel]:
    stmt = (
        select(Panel)
        .join(Episode, Panel.episode_id == Episode.id)
        .where(Panel.project_id == project_id)
        .order_by(Episode.episode_order, Panel.panel_order, Panel.created_at)
    )
    return (await db.execute(stmt)).scalars().all()


async def list_project_scenes_ordered(project_id: str, db: AsyncSession) -> list[Scene]:
    return (await db.execute(
        select(Scene)
        .where(Scene.project_id == project_id)
        .order_by(Scene.sequence_order, Scene.created_at)
    )).scalars().all()


async def _load_effective_binding_map(panel_ids: list[str], db: AsyncSession) -> dict[str, dict]:
    if not panel_ids:
        return {}

    effective_rows = (await db.execute(
        select(PanelEffectiveBinding).where(PanelEffectiveBinding.panel_id.in_(panel_ids))
    )).scalars().all()
    effective_map: dict[str, dict] = {}
    for row in effective_rows:
        value = from_json_text(row.compiled_json, {})
        if isinstance(value, dict):
            effective_map[row.panel_id] = value
    return effective_map


async def _load_default_reference_image(project_id: str, db: AsyncSession) -> str | None:
    return (await db.execute(
        select(Character.reference_image_url)
        .where(
            Character.project_id == project_id,
            Character.reference_image_url.is_not(None),
        )
        .limit(1)
    )).scalar_one_or_none()


async def _load_scene_clip(
    scene_id: str,
    db: AsyncSession,
    *,
    status: str,
    selected_only: bool = False,
) -> VideoClip | None:
    filters = [
        VideoClip.scene_id == scene_id,
        VideoClip.status == status,
    ]
    if selected_only:
        filters.append(VideoClip.is_selected == True)  # noqa: E712

    stmt = select(VideoClip).where(*filters).order_by(VideoClip.clip_order, VideoClip.candidate_index).limit(1)
    return (await db.execute(stmt)).scalar_one_or_none()


async def _load_preferred_clip(scene_id: str, db: AsyncSession) -> VideoClip | None:
    selected_clip = await _load_scene_clip(
        scene_id,
        db,
        status=CLIP_STATUS_COMPLETED,
        selected_only=True,
    )
    if selected_clip is not None:
        return selected_clip
    return await _load_scene_clip(scene_id, db, status=CLIP_STATUS_COMPLETED)


async def _load_failed_clip(scene_id: str, db: AsyncSession) -> VideoClip | None:
    return await _load_scene_clip(scene_id, db, status=CLIP_STATUS_FAILED)


async def seed_panels_from_scenes(
    project_id: str,
    db: AsyncSession,
    *,
    replace_existing: bool = True,
) -> tuple[int, int]:
    scenes = await list_project_scenes_ordered(project_id, db)

    episode_blueprints: list[dict[str, str | None]] = []
    if replace_existing:
        previous_episodes = (await db.execute(
            select(Episode)
            .where(Episode.project_id == project_id)
            .order_by(Episode.episode_order, Episode.created_at)
        )).scalars().all()
        episode_blueprints = [
            {
                "title": (item.title or "").strip() or f"第{idx + 1}集",
                "summary": item.summary,
                "script_text": item.script_text,
                "status": item.status,
            }
            for idx, item in enumerate(previous_episodes)
        ]

    if replace_existing:
        await db.execute(delete(Panel).where(Panel.project_id == project_id))
        await db.execute(delete(Episode).where(Episode.project_id == project_id))

    if not scenes:
        return 0, 0

    if not episode_blueprints:
        episode_blueprints = [{
            "title": "第1集",
            "summary": "自动由解析结果生成",
            "script_text": None,
            "status": EPISODE_STATUS_DRAFT,
        }]

    created_episodes: list[Episode] = []
    for idx, blueprint in enumerate(episode_blueprints):
        created = _build_episode_from_blueprint(project_id, idx, blueprint)
        db.add(created)
        created_episodes.append(created)
    await db.flush()

    weights = [_safe_weight(item.script_text) for item in created_episodes]
    panel_counts_by_episode = _distribute_item_counts(len(scenes), weights)
    if not panel_counts_by_episode:
        panel_counts_by_episode = [len(scenes)]

    episode_slots: list[int] = []
    for episode_idx, count in enumerate(panel_counts_by_episode):
        episode_slots.extend([episode_idx] * max(0, count))
    if len(episode_slots) < len(scenes):
        episode_slots.extend([len(created_episodes) - 1] * (len(scenes) - len(episode_slots)))
    if len(episode_slots) > len(scenes):
        episode_slots = episode_slots[:len(scenes)]

    panel_count = 0
    panel_order_counters = [0] * len(created_episodes)
    for index, scene in enumerate(scenes):
        episode_slot_index = episode_slots[index] if index < len(episode_slots) else len(created_episodes) - 1
        bounded_episode_index = max(0, min(episode_slot_index, len(created_episodes) - 1))
        episode = created_episodes[bounded_episode_index]
        panel_order = panel_order_counters[bounded_episode_index]
        panel_order_counters[bounded_episode_index] += 1

        panel = _build_panel_from_scene(
            scene,
            project_id=project_id,
            episode_id=episode.id,
            panel_order=panel_order,
            default_title=f"分镜{index + 1}",
        )
        db.add(panel)
        panel_count += 1

    await db.flush()
    return len(created_episodes), panel_count


async def migrate_legacy_scenes_to_panels(db: AsyncSession) -> tuple[int, int]:
    """一次性迁移：将仅存在 Scene 的历史项目转换为 Panel。"""
    project_ids = (await db.execute(
        select(Scene.project_id).group_by(Scene.project_id)
    )).scalars().all()

    migrated_projects = 0
    migrated_panels = 0
    for project_id in project_ids:
        panel_count = int((await db.execute(
            select(func.count(Panel.id)).where(Panel.project_id == project_id)
        )).scalar() or 0)
        if panel_count > 0:
            continue
        _, created_count = await seed_panels_from_scenes(project_id, db, replace_existing=True)
        if created_count <= 0:
            continue
        migrated_projects += 1
        migrated_panels += created_count
    await db.flush()
    return migrated_projects, migrated_panels


async def rebuild_scenes_from_panels(project_id: str, db: AsyncSession) -> int:
    panels = await list_project_panels_ordered(project_id, db)
    if not panels:
        return 0

    panel_ids = [item.id for item in panels]
    effective_map = await _load_effective_binding_map(panel_ids, db)
    default_reference_image = await _load_default_reference_image(project_id, db)

    existing_scene_ids = (await db.execute(
        select(Scene.id).where(Scene.project_id == project_id)
    )).scalars().all()
    if existing_scene_ids:
        await db.execute(delete(VideoClip).where(VideoClip.scene_id.in_(existing_scene_ids)))
    await db.execute(delete(Scene).where(Scene.project_id == project_id))
    await db.flush()

    for index, panel in enumerate(panels):
        scene = Scene(
            project_id=project_id,
            sequence_order=index,
            title=(panel.title or "").strip() or f"场景 {index + 1}",
            transition_hint="crossfade",
            # 每次项目级生成都从 pending 重建，确保素材与分镜一致。
            status=SCENE_STATUS_PENDING,
        )
        _apply_panel_metadata_to_scene(
            scene,
            panel,
            index,
            effective_map.get(panel.id),
            default_reference_image,
        )
        db.add(scene)

    await db.flush()
    return len(panels)


async def ensure_scene_projection_from_panels(project_id: str, db: AsyncSession) -> tuple[list[Panel], list[Scene]]:
    panels = await list_project_panels_ordered(project_id, db)
    if not panels:
        return [], []

    scenes = await list_project_scenes_ordered(project_id, db)
    if not scenes or len(scenes) != len(panels):
        rebuilt_count = await rebuild_scenes_from_panels(project_id, db)
        if rebuilt_count == 0:
            return panels, []
        scenes = await list_project_scenes_ordered(project_id, db)
        if len(scenes) != len(panels):
            raise RuntimeError("分镜执行映射数量不一致")

    panel_ids = [item.id for item in panels]
    effective_map = await _load_effective_binding_map(panel_ids, db)
    default_reference_image = await _load_default_reference_image(project_id, db)

    # 非破坏性同步：仅覆写元数据，不清空已有片段与状态。
    for index, panel in enumerate(panels):
        _apply_panel_metadata_to_scene(
            scenes[index],
            panel,
            index,
            effective_map.get(panel.id),
            default_reference_image,
        )

    await db.flush()
    return panels, scenes


async def sync_panel_outputs_from_scenes(project_id: str, db: AsyncSession) -> tuple[int, int]:
    scenes = await list_project_scenes_ordered(project_id, db)
    panels = await list_project_panels_ordered(project_id, db)

    completed = 0
    failed = 0
    for index, panel in enumerate(panels):
        if index >= len(scenes):
            panel.status = PANEL_STATUS_FAILED
            panel.error_message = "分镜与场景映射数量不一致"
            failed += 1
            continue

        scene = scenes[index]
        panel.status = _panel_status_from_scene(scene)
        if panel.status == PANEL_STATUS_COMPLETED:
            completed += 1
        elif panel.status == PANEL_STATUS_FAILED:
            failed += 1

        selected_clip = await _load_preferred_clip(scene.id, db)
        panel.video_url = _clip_to_media_url(selected_clip.file_path) if selected_clip else None

        if panel.status == PANEL_STATUS_FAILED:
            failed_clip = await _load_failed_clip(scene.id, db)
            panel.error_message = failed_clip.error_message if failed_clip else "分镜生成失败"
        else:
            panel.error_message = None

    await db.flush()
    return completed, failed
