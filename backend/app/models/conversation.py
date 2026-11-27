import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ConversationThread(Base):
    __tablename__ = "conversation_threads"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (Index("ix_conversation_user_updated", "user_id", "updated_at"),)


class ConversationMessage(Base):
    """One persisted turn in a chat thread.

    Messages are the durable facts used to assemble multi-turn context, distinct
    from LangGraph checkpoints (which hold rebuildable execution state). They are
    what the UI renders and what the model reads on the next turn.
    """

    __tablename__ = "conversation_messages"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(String(8000), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    evidence_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Python-side microsecond timestamp keeps ordering reliable within a turn,
    # where server-side second precision can make user/assistant tie and sort by
    # random UUID. The server_default remains as a DB-level fallback.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
    )

    __table_args__ = (Index("ix_conversation_msg_thread_created", "thread_id", "created_at"),)
