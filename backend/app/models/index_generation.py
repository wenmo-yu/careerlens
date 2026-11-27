from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class IndexGeneration(Base):
    """Ever-written Qdrant collection within the configured vector service."""

    __tablename__ = "index_generations"

    collection: Mapped[str] = mapped_column(String(255), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
