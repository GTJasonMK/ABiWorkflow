from __future__ import annotations

from typing import Final

SCENE_STATUS_PENDING: Final = "pending"
SCENE_STATUS_GENERATING: Final = "generating"
SCENE_STATUS_GENERATED: Final = "generated"
SCENE_STATUS_COMPLETED: Final = "completed"
SCENE_STATUS_FAILED: Final = "failed"

READY_SCENE_STATUSES: Final = frozenset({
    SCENE_STATUS_GENERATED,
    SCENE_STATUS_COMPLETED,
})

REGENERATABLE_SCENE_STATUSES: Final = frozenset({
    SCENE_STATUS_PENDING,
    SCENE_STATUS_FAILED,
    SCENE_STATUS_GENERATING,
})
