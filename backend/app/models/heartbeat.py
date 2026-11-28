"""Lightweight liveness facts for the long-running worker and scheduler."""

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

HEARTBEAT_ROLES = ("worker", "scheduler")


class RuntimeHeartbeat(Base):
    __tablename__ = "runtime_heartbeats"

    role: Mapped[str] = mapped_column(String(16), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(36), nullable=False)
    pid: Mapped[int] = mapped_column(Integer, nullable=False)
    heartbeat_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    started_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
