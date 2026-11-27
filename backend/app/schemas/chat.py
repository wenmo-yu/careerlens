from typing import Any

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=5000)
    thread_id: str | None = Field(default=None, max_length=128)
    job_analysis_id: str | None = None
    mode: str = Field(default="rag", pattern="^(rag|wiki|hybrid)$")

    @field_validator("message")
    @classmethod
    def nonempty_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Message must contain visible text")
        return value


class ChatMessage(BaseModel):
    role: str
    content: str
    intent: str | None = None
    created_at: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    intent: str
    answer: str
    evidence: list[dict[str, Any]]
    retrieval: dict[str, Any]
    model: dict[str, Any]
    messages: list[ChatMessage] = Field(default_factory=list)
