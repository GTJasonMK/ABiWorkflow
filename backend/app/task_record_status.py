from __future__ import annotations

from typing import Final

TASK_RECORD_STATUS_PENDING: Final = "pending"
TASK_RECORD_STATUS_RUNNING: Final = "running"
TASK_RECORD_STATUS_COMPLETED: Final = "completed"
TASK_RECORD_STATUS_FAILED: Final = "failed"
TASK_RECORD_STATUS_CANCELLED: Final = "cancelled"

TASK_RECORD_READY_STATUSES: Final = frozenset({
    TASK_RECORD_STATUS_COMPLETED,
    TASK_RECORD_STATUS_FAILED,
    TASK_RECORD_STATUS_CANCELLED,
})
