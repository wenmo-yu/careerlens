from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AccountDeletionRead(BaseModel):
    deleted: bool
    receipt_id: str
    deleted_counts: dict[str, int]
    vector_result: dict[str, Any]
    checkpoint_result: dict[str, Any]
    created_at: datetime
