"""
Reminder ORM Model — medicine / task reminders with family escalation
(benefits_section.docx §14.1, §14.6 «الدوا والمتابعة»).

Lifecycle:  pending → announced → (acknowledged | escalated)
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    # medicine | task | appointment
    reminder_type: Mapped[str] = mapped_column(String(16), default="task", nullable=False)

    # Stored as naive UTC
    target_time: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    # once | daily | weekly
    recurrence: Mapped[str] = mapped_column(String(8), default="once", nullable=False)

    # pending | announced | acknowledged | escalated | cancelled
    status: Mapped[str] = mapped_column(String(14), index=True, default="pending", nullable=False)
    announced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Family member to notify when unacknowledged (set explicitly by the owner)
    escalation_contact_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    # msg | call
    escalation_mode: Mapped[str] = mapped_column(String(4), default="msg", nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
