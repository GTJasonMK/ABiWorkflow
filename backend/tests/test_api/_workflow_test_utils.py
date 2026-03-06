from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Episode, Panel, Scene


def build_episode(project_id: str, *, order: int = 0, title: str = "第1集") -> Episode:
    return Episode(
        project_id=project_id,
        episode_order=order,
        title=title,
    )


def build_panel(
    project_id: str,
    episode_id: str,
    *,
    order: int = 0,
    title: str = "分镜一",
    visual_prompt: str | None = "prompt",
    duration_seconds: float = 5.0,
    status: str = "pending",
    video_url: str | None = None,
) -> Panel:
    return Panel(
        project_id=project_id,
        episode_id=episode_id,
        panel_order=order,
        title=title,
        visual_prompt=visual_prompt,
        duration_seconds=duration_seconds,
        status=status,
        video_url=video_url,
    )


def panel_status_for_scene(scene_status: str) -> str:
    if scene_status in {"generated", "completed"}:
        return "completed"
    if scene_status == "failed":
        return "failed"
    return "pending"


async def seed_panels_from_scenes(
    db_session: AsyncSession,
    project_id: str,
    scenes: list[Scene],
) -> Episode:
    episode = build_episode(project_id)
    db_session.add(episode)
    await db_session.flush()

    for index, scene in enumerate(sorted(scenes, key=lambda item: item.sequence_order)):
        db_session.add(build_panel(
            project_id,
            episode.id,
            order=index,
            title=scene.title or f"分镜{index + 1}",
            visual_prompt=(scene.video_prompt or None),
            duration_seconds=float(scene.duration_seconds or 5.0),
            status=panel_status_for_scene(scene.status),
            video_url=(f"/media/videos/{scene.id}.mp4" if scene.status in {"generated", "completed"} else None),
        ))
    await db_session.flush()
    return episode


async def seed_single_panel(
    db_session: AsyncSession,
    project_id: str,
    *,
    title: str,
    visual_prompt: str | None,
    duration_seconds: float,
    status: str,
    video_url: str | None = None,
) -> Episode:
    episode = build_episode(project_id)
    db_session.add(episode)
    await db_session.flush()
    db_session.add(build_panel(
        project_id,
        episode.id,
        title=title,
        visual_prompt=visual_prompt,
        duration_seconds=duration_seconds,
        status=status,
        video_url=video_url,
    ))
    await db_session.flush()
    return episode
