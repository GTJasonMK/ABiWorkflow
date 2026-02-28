from __future__ import annotations

from typing import Final

EPISODE_STATUS_DRAFT: Final = "draft"
EPISODE_STATUS_READY: Final = "ready"
EPISODE_STATUS_RENDERING: Final = "rendering"
EPISODE_STATUS_COMPLETED: Final = "completed"
EPISODE_STATUS_FAILED: Final = "failed"

EPISODE_TERMINAL_STATUSES: Final = frozenset({
    EPISODE_STATUS_COMPLETED,
    EPISODE_STATUS_FAILED,
})
