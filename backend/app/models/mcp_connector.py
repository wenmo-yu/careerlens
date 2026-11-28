"""MCP connector admission records (M8 policy layer).

This is an admission registry only. It does not connect to any server, open a
socket or load third-party code. It records the reviewed namespace, tool
allowlist, required scope and the exact config digest so the gateway can apply
default-deny admission without ever widening privileges.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

CONNECTOR_STATES = ("registered", "enabled", "disabled")


class AgentMcpConnector(Base):
    __tablename__ = "agent_mcp_connectors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workspace_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    namespace: Mapped[str] = mapped_column(String(64), nullable=False)
    allowed_tools: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    required_scope: Mapped[str] = mapped_column(String(32), nullable=False, default="read")
    config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="registered")
    revoked: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("user_id", "namespace", name="uq_agent_mcp_connector_user_ns"),
        CheckConstraint(
            "state IN ('registered','enabled','disabled')", name="ck_agent_mcp_connector_state"
        ),
        Index("ix_agent_mcp_connector_user", "user_id", "state"),
    )
