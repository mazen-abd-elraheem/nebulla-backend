"""
Memory ORM Model — long-term memory storage with embedding vectors for RAG.
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Memory(Base):
    """
    Individual memory item with pre-computed embedding vector.
    Used by RAGService to ground LLM responses in context.
    """
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    personality_id: Mapped[int | None] = mapped_column(Integer, index=True, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="conversation")
    importance: Mapped[int] = mapped_column(Integer, default=5)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_accessed: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
