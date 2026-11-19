from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WikiCompileRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    slug: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    evidence_ids: list[str] = Field(default_factory=list, max_length=50)
    base_version: int | None = Field(default=None, ge=1)
    edit_source: str = Field(default="pipeline", pattern="^(user|agent|pipeline|revert)$")


class WikiPageRead(BaseModel):
    id: str
    user_id: str
    slug: str
    title: str
    page_type: str
    content: str
    summary: str | None
    version: int
    last_edit_source: str
    source_refs: list[Any]
    chunk_refs: list[Any]
    out_links: list[Any]
    in_links: list[Any]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WikiCompileRead(BaseModel):
    page: WikiPageRead
    diagnostics: dict[str, Any]


class WikiRevertRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    target_version: int = Field(ge=1)
