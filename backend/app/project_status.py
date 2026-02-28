from __future__ import annotations

from typing import Final

PROJECT_STATUS_DRAFT: Final = "draft"
PROJECT_STATUS_PARSING: Final = "parsing"
PROJECT_STATUS_PARSED: Final = "parsed"
PROJECT_STATUS_GENERATING: Final = "generating"
PROJECT_STATUS_COMPOSING: Final = "composing"
PROJECT_STATUS_COMPLETED: Final = "completed"
PROJECT_STATUS_FAILED: Final = "failed"

PROJECT_BUSY_STATUSES: Final = frozenset({
    PROJECT_STATUS_PARSING,
    PROJECT_STATUS_GENERATING,
    PROJECT_STATUS_COMPOSING,
})

PROJECT_PARSE_ALLOWED_FROM: Final = (
    PROJECT_STATUS_DRAFT,
    PROJECT_STATUS_PARSED,
    PROJECT_STATUS_FAILED,
    PROJECT_STATUS_COMPLETED,
)
PROJECT_GENERATE_ALLOWED_FROM: Final = (
    PROJECT_STATUS_PARSED,
    PROJECT_STATUS_FAILED,
    PROJECT_STATUS_COMPLETED,
)
PROJECT_COMPOSE_ALLOWED_FROM: Final = (
    PROJECT_STATUS_PARSED,
    PROJECT_STATUS_FAILED,
    PROJECT_STATUS_COMPLETED,
)

PROJECT_RESET_TO_DRAFT_ON_SCRIPT_CHANGE: Final = frozenset({
    PROJECT_STATUS_PARSED,
    PROJECT_STATUS_FAILED,
    PROJECT_STATUS_COMPLETED,
})
PROJECT_RESET_TO_PARSED_ON_CONTENT_CHANGE: Final = frozenset({
    PROJECT_STATUS_COMPLETED,
    PROJECT_STATUS_FAILED,
})
PROJECT_RESTORE_TO_PARSED_OR_COMPLETED: Final = frozenset({
    PROJECT_STATUS_PARSED,
    PROJECT_STATUS_COMPLETED,
})


def is_project_busy(status: str) -> bool:
    return status in PROJECT_BUSY_STATUSES


def resolve_parse_recover_status(has_structured_data: bool) -> str:
    return PROJECT_STATUS_PARSED if has_structured_data else PROJECT_STATUS_DRAFT


def resolve_post_scene_generation_status(previous_status: str) -> str:
    return (
        previous_status
        if previous_status in PROJECT_RESTORE_TO_PARSED_OR_COMPLETED
        else PROJECT_STATUS_PARSED
    )
