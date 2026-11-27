from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RegisterRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    name: str = Field(default="owner", min_length=1, max_length=100)


class TokenCreateRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(min_length=1, max_length=5)
    audience: Literal["api", "mcp"] = "api"


class TokenCreated(BaseModel):
    id: str
    user_id: str
    name: str
    scopes: list[str]
    token: str
    created_at: datetime
    audience: str
    expires_at: datetime


class TokenRead(BaseModel):
    id: str
    user_id: str
    name: str
    scopes: list[str]
    active: bool
    created_at: datetime
    last_used_at: datetime | None
    audience: str
    expires_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SessionRead(BaseModel):
    mode: str
    user_id: str | None = None
    scopes: list[str] = Field(default_factory=list)
    can_operate: bool = False
    registration_enabled: bool = False


class AuditEventRead(BaseModel):
    id: str
    user_id: str
    actor_token_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    details: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
