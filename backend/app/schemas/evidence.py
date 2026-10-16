from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class EvidenceTextCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    source_type: str = Field(default="self_statement", min_length=1, max_length=50)
    source_name: str = Field(default="manual-input", min_length=1, max_length=255)
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceRead(BaseModel):
    id: str
    user_id: str
    source_type: str
    source_name: str
    content: str
    content_type: str
    chunk_index: int
    source_metadata: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EvidenceBatchRead(BaseModel):
    items: list[EvidenceRead]
    count: int


class ConnectorImportRead(BaseModel):
    items: list[EvidenceRead]
    created_count: int
    skipped_count: int
    duplicate_count: int
    connector: str

