"""
User ORM Model — user registration, login, and personality ownership.
"""

from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """
    User account model supporting email/password login,
    Neural Face ID biometric verification, and personality ownership.
    """
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    # Neural Face ID (links to registered face profile)
    face_profile_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("face_profiles.id", ondelete="SET NULL"), nullable=True
    )

    # Terms & Conditions accepted (as required on registration screen)
    terms_accepted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    terms_accepted_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False)

    # Password reset support
    reset_token: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # Personalities owned by this user
    personalities: Mapped[List["Personality"]] = relationship(
        "Personality", back_populates="user", cascade="all, delete-orphan", lazy="selectin"
    )

    # Biometric face profile
    face_profile: Mapped[Optional["FaceProfile"]] = relationship("FaceProfile", lazy="selectin")

    # Enrolled speaker acoustic voiceprint (1:1)
    voiceprint: Mapped[Optional["Voiceprint"]] = relationship(
        "Voiceprint", uselist=False, cascade="all, delete-orphan", lazy="selectin"
    )

    # Allowlisted phone contacts
    contacts: Mapped[List["Contact"]] = relationship(
        "Contact", cascade="all, delete-orphan", lazy="selectin"
    )

    # Scheduled reminders
    reminders: Mapped[List["Reminder"]] = relationship(
        "Reminder", cascade="all, delete-orphan", lazy="selectin"
    )
