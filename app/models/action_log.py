"""
ActionLog ORM Model — audit trail of phone actions (benefits_section.docx §14.5/§14.9).

The log records EVENTS ONLY: who, what, when, outcome.
It MUST NEVER contain message text, call audio, transcripts or phone numbers.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ActionLog(Base):
    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # call | app | msg | reminder | read_notifications | sensitive
    action_type: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    # Contact display name / app id only — never a number or message body
    target: Mapped[str | None] = mapped_column(String(64), nullable=True)
    security_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # requested | challenged | confirmed | dispatched | completed | failed | rejected | cancelled | expired
    status: Mapped[str] = mapped_column(String(24), index=True, default="requested", nullable=False)
    # Short machine code, e.g. "not_verified", "lockout", "contact_unknown"
    reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Speaker-match score at request time (diagnostics / threshold calibration)
    speaker_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
