from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=5000)
    thread_id: str | None = Field(default=None, max_length=128)
    job_analysis_id: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    intent: str
    answer: str
    evidence: list[dict[str, Any]]
    retrieval: dict[str, Any]
    model: dict[str, Any]
