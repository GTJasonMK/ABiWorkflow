from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.database import async_session_factory
from app.models import TaskEvent
from app.services.task_records import serialize_task_event

router = APIRouter(tags=["SSE 事件流"])


def _parse_last_event_id(value: str | None) -> int:
    if not value:
        return 0
    try:
        return max(0, int(value.strip()))
    except (TypeError, ValueError):
        return 0


async def _event_stream(
    request: Request,
    *,
    project_id: str | None,
    episode_id: str | None,
    panel_id: str | None,
    start_event_no: int,
) -> AsyncGenerator[str, None]:
    current_event_no = start_event_no

    while True:
        if await request.is_disconnected():
            break

        async with async_session_factory() as db:
            stmt = select(TaskEvent).where(TaskEvent.event_no > current_event_no).order_by(TaskEvent.event_no).limit(100)
            if project_id:
                stmt = stmt.where(TaskEvent.project_id == project_id)
            if episode_id:
                stmt = stmt.where(TaskEvent.episode_id == episode_id)
            if panel_id:
                stmt = stmt.where(TaskEvent.panel_id == panel_id)

            events = (await db.execute(stmt)).scalars().all()

        if events:
            for event in events:
                payload = serialize_task_event(event)
                current_event_no = int(event.event_no)
                yield (
                    f"id: {event.event_no}\n"
                    f"event: {event.event_type}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                )
        else:
            yield ": ping\n\n"

        await asyncio.sleep(1.0)


@router.get("/sse")
async def stream_task_events(
    request: Request,
    project_id: str | None = None,
    episode_id: str | None = None,
    panel_id: str | None = None,
    last_event_id: int | None = None,
):
    header_last_id = _parse_last_event_id(request.headers.get("Last-Event-ID"))
    query_last_id = max(0, int(last_event_id or 0))
    start_event_no = max(header_last_id, query_last_id)
    stream = _event_stream(
        request,
        project_id=project_id,
        episode_id=episode_id,
        panel_id=panel_id,
        start_event_no=start_event_no,
    )
    return StreamingResponse(stream, media_type="text/event-stream")
