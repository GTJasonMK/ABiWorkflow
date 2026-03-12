from __future__ import annotations

from typing import Final

PANEL_STATUS_DRAFT: Final = "draft"
PANEL_STATUS_PENDING: Final = "pending"
PANEL_STATUS_PROCESSING: Final = "processing"
PANEL_STATUS_COMPLETED: Final = "completed"
PANEL_STATUS_FAILED: Final = "failed"

PANEL_READY_STATUSES: Final = frozenset({
    PANEL_STATUS_COMPLETED,
})

PANEL_REGENERATABLE_STATUSES: Final = frozenset({
    PANEL_STATUS_DRAFT,
    PANEL_STATUS_PENDING,
    PANEL_STATUS_FAILED,
    PANEL_STATUS_PROCESSING,
})

PANEL_RENDERABLE_STATUSES: Final = frozenset({
    PANEL_STATUS_PENDING,
    PANEL_STATUS_FAILED,
})
