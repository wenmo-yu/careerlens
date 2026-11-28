"""Durable long-lived roles for the M8 agent plane.

A role is a user-configured persistence boundary: it owns one long-lived agent
session, a frozen configuration version, and a tool allowlist that is enforced
on the trusted gateway. Roles never create roles, never send messages on behalf
of another identity, and never gain tools that are not registered.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

ROLE_STATES = ("active", "paused", "archived")


class AgentRole(Base):
    __tablename__ = "agent_roles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    template: Mapped[str] = mapped_column(String(48), nullable=False)
    # Bumped on every configuration update; a run records the version it used.
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    tool_allowlist: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    model_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    budget: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output_schema: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # One persistent main session; the warm pool releases compute when idle.
    session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_token_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_agent_role_user_name"),
        CheckConstraint("state IN ('active','paused','archived')", name="ck_agent_role_state"),
        Index("ix_agent_role_user", "user_id", "state"),
    )
