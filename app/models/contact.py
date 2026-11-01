"""
Contact ORM Model — allow-listed phone contacts the robot may call / message.

Privacy (benefits_section.docx §14.9):
  * Only people the owner explicitly added can be called or messaged by voice.
  * Phone numbers live ONLY in this table. They are never injected into LLM
    prompts or RAG context (the model only ever sees display names).
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )

    # Display name as the owner says it, e.g. "ماما"
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    # Comma-separated spoken aliases STT may produce, e.g. "مامي,ماميتي,الوالدة"
    aliases: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    # Latin slug sent to the phone as {"contact": "mama"}
    slug: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    phone_number: Mapped[str] = mapped_column(String(32), nullable=False)
    relationship: Mapped[str | None] = mapped_column(String(32), nullable=True)

    is_allowlisted: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Verbal «أكلّم ماما؟» confirmation before calling. Messages ALWAYS confirm.
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Minimum security level needed to call / message this contact (1 or 2)
    required_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Family member to notify when a reminder goes unacknowledged
    notify_on_missed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
