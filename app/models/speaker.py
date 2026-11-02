"""
Speaker ORM Model — unified digital-twin identity and speaker profile.
Aggregates:
  1. verification_id (Voiceprint biometric embedding ID)
  2. voice_id (TTS cloned voice sample / model identifier)
  3. personality_id (Digital-twin personality prompt ID)
  4. is_main (Whether this speaker is a primary/main owner of the robot)
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Speaker(Base):
    __tablename__ = "speakers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    # 1. Verification ID (Links to Voiceprint biometric embedding)
    verification_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("voiceprints.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # 2. Voice ID (Cloned voice sample or TTS model identifier, e.g. "1", "personality_1", or custom voice tag)
    voice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # 3. Personality ID (Links to robot digital-twin personality profile)
    personality_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("personalities.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # 4. Main Speaker Flag (Multi-main supported: e.g. Mazen and Menna can both be main speakers)
    is_main: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Relationships
    voiceprint: Mapped[Optional["Voiceprint"]] = relationship("Voiceprint", foreign_keys=[verification_id])
    personality: Mapped[Optional["Personality"]] = relationship("Personality", foreign_keys=[personality_id])

