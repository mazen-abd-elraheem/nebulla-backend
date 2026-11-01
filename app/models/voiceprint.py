"""
Voiceprint ORM Model — enrolled speaker embeddings (benefits_section.docx §14.3).

Privacy by design:
  * We store ONLY the mean speaker embedding (a float32 vector), never the
    enrolment recordings themselves.
  * Enrolment requires explicit consent (recorded in ``consent_at``).
  * The owner can delete a voiceprint at any time (right to be forgotten).
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Voiceprint(Base):
    __tablename__ = "voiceprints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    # One voiceprint per user account
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    speaker_name: Mapped[str] = mapped_column(String(64), nullable=False)

    # L2-normalised float32 mean embedding (raw bytes)
    embedding: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    embedding_dim: Mapped[int] = mapped_column(Integer, nullable=False)
    samples_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    model_id: Mapped[str] = mapped_column(String(128), default="", nullable=False)

    # Highest security level this speaker may reach (child = 0, owner = 2/3)
    max_level: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    # Cross-modal links (Face ID, Personality ID, Memory ID)
    face_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    personality_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    consent_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
