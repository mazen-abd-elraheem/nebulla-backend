"""
Reminder scheduler — medicine / task reminders with family escalation
(benefits_section.docx §14.6 «الدوا والمتابعة», §14.8 «تذكير الدوا ومفيش رد»):

    due → announce by voice («خدته؟») → user says «أيوه» / taps ack
        → no answer within REMINDER_ESCALATION_MINUTES → notify the family contact

An in-process asyncio loop (single robot, single process) — no external broker.
All timestamps are naive UTC (matching the rest of the schema).
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from sqlalchemy import select

from app.core.config import settings
from app.core.logger import get_logger
from app.models.contact import Contact
from app.models.reminder import Reminder

logger = get_logger(__name__)

_MAX_LATE = timedelta(minutes=30)  # a reminder this late is marked missed, not announced


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def advance_recurrence(rem: Reminder) -> None:
    """After a reminder is finished, roll recurring ones forward to their next occurrence."""
    if rem.recurrence == "daily":
        step = timedelta(days=1)
    elif rem.recurrence == "weekly":
        step = timedelta(days=7)
    else:
        return
    now = utcnow_naive()
    nxt = rem.target_time + step
    while nxt <= now:           # skip occurrences missed while the robot was off
        nxt += step
    rem.target_time = nxt
    rem.status = "pending"
    rem.announced_at = None


class ReminderScheduler:
    def __init__(self, service, *, session_factory=None) -> None:
        self._svc = service
        self._sf = session_factory
        self._task: Optional[asyncio.Task] = None

    def _session(self):
        if self._sf is not None:
            return self._sf()
        from app.db.session import AsyncSessionLocal
        return AsyncSessionLocal()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        try:
            purged = await self._svc.purge_old_logs()
            if purged:
                logger.info("Purged %d old action-log rows", purged)
        except Exception as e:  # noqa: BLE001
            logger.warning("Action-log purge skipped: %s", e)
        self._task = asyncio.create_task(self._loop(), name="reminder-scheduler")
        logger.info("⏰ Reminder scheduler started")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("Reminder tick failed")
            await asyncio.sleep(settings.REMINDER_CHECK_INTERVAL_SECONDS)

    async def tick(self, now: Optional[datetime] = None) -> None:
        now = now or utcnow_naive()
        to_say: List[Tuple[str, str]] = []
        escalations: List[Tuple[int, Contact, str, str]] = []  # (reminder_id, contact, text, mode)

        async with self._session() as db:
            # 1) announce due reminders
            due = (await db.execute(
                select(Reminder).where(
                    Reminder.is_active == True,  # noqa: E712
                    Reminder.status == "pending",
                    Reminder.target_time <= now,
                )
            )).scalars().all()
            for r in due:
                if now - r.target_time > _MAX_LATE:
                    r.status = "missed"
                    advance_recurrence(r)
                    continue
                if self._svc.in_call() or not self._svc._mgr.phone_connected:
                    continue  # retry next tick (muted during calls / phone offline)
                if r.reminder_type == "medicine":
                    r.status = "announced"
                    r.announced_at = now
                    self._svc.mark_awaiting_ack(r.id)
                    to_say.append((f"حان ميعاد {r.title}. خدته؟", "alert"))
                else:
                    r.status = "acknowledged"
                    r.acknowledged_at = now
                    advance_recurrence(r)
                    to_say.append((f"فكّرتك: {r.title}", "happy"))

            # 2) escalate medicine reminders nobody acknowledged
            stale_cutoff = now - timedelta(minutes=settings.REMINDER_ESCALATION_MINUTES)
            stale = (await db.execute(
                select(Reminder).where(
                    Reminder.status == "announced",
                    Reminder.announced_at <= stale_cutoff,
                )
            )).scalars().all()
            for r in stale:
                contact = await db.get(Contact, r.escalation_contact_id) if r.escalation_contact_id else None
                if contact is None:
                    r.status = "missed"
                    r.escalated_at = now
                    self._svc._awaiting_ack = [i for i in self._svc._awaiting_ack if i != r.id]
                    advance_recurrence(r)
                    continue
                escalations.append((r.id, contact, f"تنبيه: لسه ما اتأكدش إن {r.title} اتاخد.", r.escalation_mode))
            await db.commit()

        # Speak after the DB transaction is closed (TTS can take seconds)
        for text, mood in to_say:
            await self._svc.say(text, mood)

        for rid, contact, text, mode in escalations:
            ok = await self._svc.dispatch_escalation(contact, text, mode)
            async with self._session() as db:
                r = await db.get(Reminder, rid)
                if r is None:
                    continue
                if ok:
                    r.status = "escalated"
                    r.escalated_at = now
                    self._svc._awaiting_ack = [i for i in self._svc._awaiting_ack if i != rid]
                    advance_recurrence(r)
                    await db.commit()
                    await self._svc.say(f"بلّغت {contact.name}.", "neutral")
                elif r.announced_at and now - r.announced_at > _MAX_LATE:
                    r.status = "missed"
                    r.escalated_at = now
                    advance_recurrence(r)
                    await db.commit()
                # else: phone offline — retry next tick
