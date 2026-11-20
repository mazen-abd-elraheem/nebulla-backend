"""
Memory ORM Model — long-term memory storage with embedding vectors for RAG.
"""

from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.models.user import User


class Memory(Base):
    """
    Individual memory item with pre-computed embedding vector.
    Used by RAGService to ground LLM responses in context.
    """
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    personality_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="conversation")
    importance: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[Optional["User"]] = relationship("User", back_populates="memories")

