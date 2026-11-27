from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class AccountDeletionRead(BaseModel):
    deleted: bool
    receipt_id: str
    deleted_counts: dict[str, int]
    vector_result: dict[str, Any]
    checkpoint_result: dict[str, Any]
    cleanup_status: Literal["pending", "completed", "failed", "unknown"]
    pending_targets: int = 0
    completed_targets: int = 0
    failed_targets: int = 0
    cleanup_attempts: int = 0
    last_error_codes: list[str] = []
    created_at: datetime
