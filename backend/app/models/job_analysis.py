import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class JobAnalysis(Base):
    __tablename__ = "job_analyses"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    requirements: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    matches: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    gaps: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    learning_path: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def privacy_redacted(self) -> bool:
        return not isinstance(self.report, dict) or self.report.get("privacy_redacted") is True
