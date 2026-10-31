"""
PhoneActionService — orchestrates Chapter 14 phone actions end to end
(benefits_section.docx §14.5):

    transcript ─► ActionPlanner ─► ActionGuard ─► [challenge] ─► [confirm] ─► phone

  • one pending action at a time (the robot has one face / one owner at the mic)
  • every state transition is time-boxed (TTL) and fails closed
  • the audit log stores EVENTS only — never message text, numbers or audio
  • during a phone call the AI line is muted (privacy; §14.5 "أثناء المكالمة")
"""

import asyncio
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import ValidationError
from sqlalchemy import delete, or_, select

from app.core.config import settings
from app.core.logger import get_logger
from app.models.action_log import ActionLog
from app.models.contact import Contact
from app.models.reminder import Reminder
from app.services.phone_action.challenge import Challenge, RandomChallengeService
from app.services.phone_action.contacts import extract_number, match_contact, normalize_phone
from app.services.phone_action.guard import ALLOW, CHALLENGE, DENY, ActionGuard, GuardDecision
from app.services.phone_action.planner import (
    APP_OPEN,
    CALL,
    MSG,
    READ_NOTIFICATIONS,
    REMINDER,
    SENSITIVE,
    ActionPlanner,
    Intent,
    compute_target_time,
)
from app.services.phone_action.reminders import advance_recurrence
from app.services.phone_action.textutil import fold, is_no, is_yes, sanitize_free_text
from app.services.voice_verification.speaker_service import VerificationResult
from app.websocket.manager import manager as _default_manager
from app.websocket.messages import ActionResultMsg, AppCmdMsg, CallCmdMsg, MsgCmdMsg

logger = get_logger(__name__)

# ── spoken responses (Egyptian Arabic) ───────────────────────────────────────
S_NO_VOICEPRINT = "لازم تسجّل بصمة صوتك الأول من غرفة التحكم عشان أنفّذ الحاجات دي."
S_NOT_VERIFIED = "مش قادر أتأكد إن ده صوتك، فمش هنفّذ الطلب ده."
S_PERMISSION = "الصلاحية بتاعتك مش بتسمح بالطلب ده."
S_LOCKED = "من أجل الأمان، الأوامر دي مقفولة مؤقتًا. جرّب بعد شوية."
S_UNKNOWN_CONTACT = "مش لاقي الاسم ده في جهات الاتصال المسموحة."
S_AMBIGUOUS = "في أكتر من جهة بنفس الاسم، تقصد مين؟"
S_APP_NOT_ALLOWED = "التطبيق ده مش مسموح أفتحه."
S_NOT_ALLOWED = "الطلب ده مش مسموح."
S_NO_BODY = "أقول له إيه؟"
S_PHONE_OFFLINE = "الموبايل مش متصل دلوقتي."
S_CANCELLED = "تمام، لغيت الطلب."
S_VOICE_MISMATCH = "الصوت مش مطابق، لغيت الطلب."
S_CHALLENGE_FAILED = "مقدرتش أتأكد منك، لغيت الطلب."
S_EXTERNAL = "الطلب ده حساس. محتاج تأكيد من غرفة التحكم."
S_EXECUTOR_UNAVAILABLE = "اتأكدت منك، بس العملية دي مش متاحة بالصوت في النسخة دي."
S_INVALID_NUMBER = "الرقم المسجّل للجهة دي مش صالح، راجعه من غرفة التحكم."
S_ERROR = "حصلت مشكلة وأنا بنفّذ الطلب."

_APP_DISPLAY = {
    "maps": "الخرايط", "whatsapp": "واتساب", "youtube": "يوتيوب", "spotify": "سبوتيفاي",
    "camera": "الكاميرا", "telegram": "تيليجرام", "music": "الصوتيات",
}
_LOG_TYPE = {
    CALL: "call", MSG: "msg", APP_OPEN: "app", READ_NOTIFICATIONS: "read_notifications",
    REMINDER: "reminder", SENSITIVE: "sensitive",
}


@dataclass
class ActionOutcome:
    handled: bool
    speech: Optional[str] = None
    mood: Optional[str] = None


NOT_HANDLED = ActionOutcome(False)


@dataclass
class _Pending:
    log_id: int
    intent: Intent
    required_level: int
    user_id: Optional[int]
    stage: str                      # challenge | confirm | external
    expires_at: float
    needs_confirm: bool
    needs_external: bool
    contact_name: Optional[str] = None
    contact_slug: Optional[str] = None
    number: Optional[str] = None    # held in memory only; never logged
    text: Optional[str] = None      # message body: memory only; never logged
    challenge: Optional[Challenge] = None


class PhoneActionService:
    def __init__(
        self,
        *,
        session_factory=None,
        ws_manager=None,
        clock: Optional[Callable[[], float]] = None,
        planner: Optional[ActionPlanner] = None,
        guard: Optional[ActionGuard] = None,
        challenge: Optional[RandomChallengeService] = None,
    ) -> None:
        self._sf = session_factory
        self._mgr = ws_manager or _default_manager
        self._now = clock or time.monotonic
        self._planner = planner or ActionPlanner()
        self._guard = guard or ActionGuard()
        self._challenge = challenge or RandomChallengeService(self._now)

        self._pending: Optional[_Pending] = None
        self._inflight: Dict[int, tuple[float, str]] = {}
        self._fails: List[float] = []
        self._call_state = "idle"
        self._call_since = 0.0
        self._awaiting_ack: List[int] = []
        self._speaker: Optional[Callable[[str, Optional[str]], Awaitable[None]]] = None
        self._lock = asyncio.Lock()

    # ── plumbing ─────────────────────────────────────────────────────────

    def _session(self):
        if self._sf is not None:
            return self._sf()
        from app.db.session import AsyncSessionLocal
        return AsyncSessionLocal()

    def set_speaker(self, fn: Callable[[str, Optional[str]], Awaitable[None]]) -> None:
        """Inject `async fn(text, mood)` that speaks through the TTS pipeline."""
        self._speaker = fn

    async def say(self, text: str, mood: Optional[str] = None) -> None:
        if self._speaker is None:
            return
        try:
            await self._speaker(text, mood)
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not speak action response: %s", e)

    # ── call state (privacy mute) ────────────────────────────────────────

    def set_call_state(self, state: str) -> None:
        self._call_state = state
        self._call_since = self._now()
        logger.info("Phone call state → %s", state)

    def reset_call_state(self) -> None:
        self._call_state = "idle"

    def in_call(self) -> bool:
        """True while ringing/active. Auto-expires so a lost 'ended' can't mute forever."""
        if self._call_state not in ("ringing", "active"):
            return False
        if self._now() - self._call_since > settings.CALL_MAX_SUSPEND_SECONDS:
            logger.warning("Call-state watchdog expired; resuming AI line")
            self._call_state = "idle"
            return False
        return True

    # ── lockout ──────────────────────────────────────────────────────────

    def _prune_fails(self) -> None:
        cutoff = self._now() - settings.ACTION_LOCKOUT_SECONDS
        self._fails = [t for t in self._fails if t >= cutoff]

    def _register_failure(self) -> None:
        self._fails.append(self._now())
        self._prune_fails()

    def is_locked(self) -> bool:
        self._prune_fails()
        return len(self._fails) >= settings.ACTION_MAX_FAILED_CHECKS

    # ── audit log (events only) ──────────────────────────────────────────

    async def _new_log(
        self, *, user_id, action_type, target, level, status, reason=None, score=None
    ) -> int:
        async with self._session() as db:
            row = ActionLog(
                user_id=user_id, action_type=action_type, target=(target or None) and target[:64],
                security_level=level, status=status, reason=reason, speaker_score=score,
            )
            db.add(row)
            await db.commit()
            return row.id

    async def _set_log(self, log_id: int, status: str, reason: Optional[str] = None) -> None:
        async with self._session() as db:
            row = await db.get(ActionLog, log_id)
            if row:
                row.status = status
                if reason:
                    row.reason = reason[:64]
                await db.commit()

    async def purge_old_logs(self) -> int:
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=settings.ACTION_LOG_RETENTION_DAYS)
        async with self._session() as db:
            res = await db.execute(delete(ActionLog).where(ActionLog.created_at < cutoff))
            await db.commit()
            return res.rowcount or 0

    async def _finish(self, p: _Pending, status: str, reason: Optional[str] = None) -> None:
        if self._pending is p:
            self._pending = None
        await self._set_log(p.log_id, status, reason)

    # ── main entry point ─────────────────────────────────────────────────

    async def handle_utterance(
        self, transcript: str, verification: Optional[VerificationResult]
    ) -> ActionOutcome:
        """
        Called by the AI pipeline for every STT transcript, BEFORE the LLM.
        handled=True  → speak `speech`, skip the LLM turn.
        handled=False → ordinary conversation.
        """
        if not settings.PHONE_ACTIONS_ENABLED or not transcript.strip():
            return NOT_HANDLED
        async with self._lock:
            try:
                return await self._handle(transcript, verification)
            except Exception:  # noqa: BLE001 — never log transcript content
                logger.exception("Phone action handling failed; nothing was dispatched")
                self._pending = None
                return NOT_HANDLED

    async def _handle(self, transcript: str, ver: Optional[VerificationResult]) -> ActionOutcome:
        await self._expire_pending()

        if self._pending is not None:
            out = await self._handle_pending(transcript, ver)
            if out is not None:
                return out

        if self._awaiting_ack and is_yes(transcript, allow_ack=True):
            rid = await self.acknowledge_reminder()
            if rid is not None:
                return ActionOutcome(True, "تمام، ربنا يديك الصحة.", "happy")

        intent = self._planner.plan(transcript)
        if intent is None:
            return NOT_HANDLED
        return await self._handle_new_intent(intent, ver)

    # ── pending-action state machine ─────────────────────────────────────

    async def _expire_pending(self) -> None:
        p = self._pending
        if p is not None and self._now() >= p.expires_at:
            await self._finish(p, "expired", "timeout")

    async def _handle_pending(
        self, transcript: str, ver: Optional[VerificationResult]
    ) -> Optional[ActionOutcome]:
        p = self._pending
        assert p is not None

        if is_no(transcript):
            await self._finish(p, "cancelled", "user_declined")
            return ActionOutcome(True, S_CANCELLED, "neutral")

        if p.stage == "confirm":
            if is_yes(transcript):
                # "أيوه" is too short to score reliably; only veto on a clearly wrong *scored* voice.
                if ver is not None and ver.score is not None and (
                    ver.user_id != p.user_id or ver.score < settings.SPEAKER_CONFIRM_MIN_SIMILARITY
                ):
                    self._register_failure()
                    await self._finish(p, "rejected", "voice_mismatch")
                    return ActionOutcome(True, S_VOICE_MISMATCH, "alert")
                return await self._execute(p)
            # Neither a clean yes nor no → fail closed: drop it, treat as a fresh utterance.
            await self._finish(p, "cancelled", "superseded")
            return None

        if p.stage == "challenge":
            ch = p.challenge
            assert ch is not None
            text_ok = self._challenge.text_matches(ch, transcript)
            if not text_ok and self._planner.plan(transcript) is not None:
                await self._finish(p, "cancelled", "superseded")
                return None
            ch.attempts += 1
            voice_ok = (
                ver is not None and ver.passed_l2 and ver.user_id is not None and ver.user_id == p.user_id
            )
            if text_ok and voice_ok:
                return await self._after_challenge(p)
            if ch.attempts >= ch.max_attempts:
                self._register_failure()
                await self._finish(p, "rejected", "challenge_failed")
                return ActionOutcome(True, S_CHALLENGE_FAILED, "alert")
            return ActionOutcome(True, f"مش مظبوطة. جرّب تاني: {ch.spoken}", "neutral")

        # stage == "external": voice can't approve this. Let normal conversation continue.
        return None

    async def _after_challenge(self, p: _Pending) -> ActionOutcome:
        await self._set_log(p.log_id, "challenged")
        if p.needs_external:
            p.stage = "external"
            p.challenge = None
            p.expires_at = self._now() + settings.EXTERNAL_CONFIRM_TTL_SECONDS
            await self._mgr.broadcast_to_desks({
                "t": "action_confirm_request",
                "id": p.log_id,
                "action": _LOG_TYPE.get(p.intent.kind, p.intent.kind),
                "target": p.contact_name,
                "level": p.required_level,
                "expires_in": settings.EXTERNAL_CONFIRM_TTL_SECONDS,
            })
            return ActionOutcome(True, S_EXTERNAL, "alert")
        if p.needs_confirm:
            p.stage = "confirm"
            p.challenge = None
            p.expires_at = self._now() + settings.CONFIRMATION_TTL_SECONDS
            return ActionOutcome(True, self._confirm_prompt(p), "neutral")
        return await self._execute(p)

    async def confirm_external(self, log_id: int, approve: bool) -> bool:
        """Level-3 approval from the control room (REST or desk WebSocket)."""
        async with self._lock:
            await self._expire_pending()
            p = self._pending
            if p is None or p.stage != "external" or p.log_id != log_id:
                return False
            if not approve:
                await self._finish(p, "cancelled", "external_denied")
                await self.say(S_CANCELLED, "neutral")
                return True
            out = await self._execute(p)
        if out.speech:
            await self.say(out.speech, out.mood)
        return True

    # ── new intent ───────────────────────────────────────────────────────

    async def _handle_new_intent(self, intent: Intent, ver: Optional[VerificationResult]) -> ActionOutcome:
        if self._pending is not None:
            await self._finish(self._pending, "cancelled", "superseded")

        score = ver.score if ver else None
        uid = ver.user_id if ver else None

        # Unknown app: explicit refusal (allow-list policy)
        if intent.kind == APP_OPEN and not intent.params.get("app"):
            await self._new_log(user_id=None, action_type="app", target=None, level=0,
                                status="rejected", reason="app_not_allowed")
            return ActionOutcome(True, S_APP_NOT_ALLOWED, "neutral")

        # Level-0 shortcut (media) — no identity needed
        decision0 = self._guard.evaluate(intent, ver) if intent.kind == APP_OPEN else None
        if decision0 is not None and decision0.action == ALLOW and decision0.required_level == 0:
            log_id = await self._new_log(user_id=None, action_type="app",
                                         target=intent.params.get("app"), level=0, status="requested")
            return await self._execute(_Pending(
                log_id=log_id, intent=intent, required_level=0, user_id=None, stage="confirm",
                expires_at=self._now(), needs_confirm=False, needs_external=False,
            ))

        # ── Level ≥ 1: identity first ────────────────────────────────────
        if self.is_locked():
            await self._new_log(user_id=uid, action_type=_LOG_TYPE[intent.kind], target=None,
                                level=1, status="rejected", reason="lockout", score=score)
            return ActionOutcome(True, S_LOCKED, "alert")
        if ver is None or not ver.available or not ver.enrolled:
            await self._new_log(user_id=None, action_type=_LOG_TYPE[intent.kind], target=None,
                                level=1, status="rejected", reason="no_voiceprint", score=score)
            return ActionOutcome(True, S_NO_VOICEPRINT, "neutral")
        if not ver.passed_l1 or ver.user_id is None:
            self._register_failure()
            await self._new_log(user_id=None, action_type=_LOG_TYPE[intent.kind], target=None,
                                level=1, status="rejected", reason="not_verified", score=score)
            return ActionOutcome(True, S_NOT_VERIFIED, "alert")

        # ── resolve target ───────────────────────────────────────────────
        contact: Optional[Contact] = None
        number: Optional[str] = None
        text: Optional[str] = None
        unlisted = False

        if intent.kind in (CALL, MSG):
            contacts = await self._load_contacts(ver.user_id)
            m = match_contact(intent.raw_norm, intent.raw_light, contacts, require_full=(intent.kind == CALL))
            if m.ambiguous:
                return ActionOutcome(True, S_AMBIGUOUS, "neutral")
            if m.contact is not None:
                contact = m.contact
                number = normalize_phone(contact.phone_number)
                if number is None:
                    await self._new_log(user_id=ver.user_id, action_type=_LOG_TYPE[intent.kind],
                                        target=contact.name, level=1, status="rejected",
                                        reason="invalid_contact_number", score=score)
                    return ActionOutcome(True, S_INVALID_NUMBER, "neutral")
                if intent.kind == MSG:
                    text = sanitize_free_text(m.remainder_light, 500)
                    if not text:
                        return ActionOutcome(True, S_NO_BODY, "neutral")
            elif intent.kind == CALL and extract_number(intent.raw_norm):
                number = extract_number(intent.raw_norm)
                unlisted = True
            else:
                await self._new_log(user_id=ver.user_id, action_type=_LOG_TYPE[intent.kind],
                                    target=None, level=1, status="rejected",
                                    reason="contact_unknown", score=score)
                return ActionOutcome(True, S_UNKNOWN_CONTACT, "neutral")

        # ── policy ───────────────────────────────────────────────────────
        decision = self._guard.evaluate(intent, ver, contact=contact, unlisted_number=unlisted)
        log_type = _LOG_TYPE[intent.kind]
        target_label = contact.name if contact else (
            intent.params.get("app") or (intent.params.get("op")) or
            ("unlisted_number" if unlisted else None)
        )
        if decision.action == DENY:
            await self._new_log(user_id=ver.user_id, action_type=log_type, target=target_label,
                                level=decision.required_level, status="rejected",
                                reason=decision.reason, score=score)
            return ActionOutcome(True, _deny_speech(decision), "neutral")

        log_id = await self._new_log(user_id=ver.user_id, action_type=log_type, target=target_label,
                                     level=decision.required_level, status="requested", score=score)
        p = _Pending(
            log_id=log_id, intent=intent, required_level=decision.required_level,
            user_id=ver.user_id, stage="confirm", expires_at=self._now(),
            needs_confirm=decision.needs_confirmation, needs_external=decision.needs_external,
            contact_name=contact.name if contact else None,
            contact_slug=(contact.slug or contact.name) if contact else None,
            number=number, text=text,
        )

        if decision.action == CHALLENGE:
            ch = self._challenge.issue()
            p.stage = "challenge"
            p.challenge = ch
            p.expires_at = ch.expires_at
            self._pending = p
            prefix = "الرقم ده مش في جهاتك. " if unlisted else ""
            return ActionOutcome(True, f"{prefix}للأمان، {ch.spoken}", "neutral")

        if decision.needs_confirmation:
            p.stage = "confirm"
            p.expires_at = self._now() + settings.CONFIRMATION_TTL_SECONDS
            self._pending = p
            return ActionOutcome(True, self._confirm_prompt(p), "neutral")

        return await self._execute(p)

    async def _load_contacts(self, user_id: Optional[int]) -> List[Contact]:
        async with self._session() as db:
            q = select(Contact).where(Contact.is_allowlisted == True)  # noqa: E712
            q = q.where(or_(Contact.user_id == user_id, Contact.user_id.is_(None)))
            return list((await db.execute(q)).scalars().all())

    @staticmethod
    def _confirm_prompt(p: _Pending) -> str:
        if p.intent.kind == CALL:
            if p.contact_name:
                return f"أكلّم {p.contact_name}؟"
            spaced = " ".join(re.sub(r"\D", "", p.number or ""))
            return f"أكلّم الرقم ده؟ {spaced}"
        if p.intent.kind == MSG:
            return f"هبعت لـ{p.contact_name}: {p.text}. أبعت؟"
        return "أنفّذ؟"

    # ── execution ────────────────────────────────────────────────────────

    async def _execute(self, p: _Pending) -> ActionOutcome:
        """Final step. Consumes the pending action first so it can never replay."""
        if self._pending is p:
            self._pending = None
        kind = p.intent.kind
        params = p.intent.params

        if kind == REMINDER:
            return await self._create_reminder(p)
        if kind == SENSITIVE:
            await self._set_log(p.log_id, "rejected", "executor_unavailable")
            return ActionOutcome(True, S_EXECUTOR_UNAVAILABLE, "neutral")

        try:
            if kind == CALL:
                msg = CallCmdMsg(id=p.log_id, contact=(p.contact_slug or "unlisted"),
                                 number=p.number or "", speaker=settings.DEFAULT_CALL_SPEAKERPHONE)
                speech = f"تمام، بكلّم {p.contact_name}" if p.contact_name else "تمام، بتصل بالرقم"
            elif kind == MSG:
                msg = MsgCmdMsg(id=p.log_id, app="whatsapp", to=(p.contact_slug or ""),
                                number=p.number or "", text=p.text or "")
                speech = f"جهّزت الرسالة لـ{p.contact_name}"
            elif kind == APP_OPEN:
                app = params.get("app")
                msg = AppCmdMsg(id=p.log_id, cmd="open", app=app, q=params.get("query"))
                disp = _APP_DISPLAY.get(app, app)
                speech = f"فتحت {disp}" + (f" على {params['query']}" if params.get("query") and app == "maps" else "")
            elif kind == READ_NOTIFICATIONS:
                msg = AppCmdMsg(id=p.log_id, cmd="read_notifications")
                speech = "تمام، بجيب الرسايل."
            else:
                await self._set_log(p.log_id, "failed", "unsupported")
                return ActionOutcome(True, S_NOT_ALLOWED, "neutral")
        except ValidationError:
            await self._set_log(p.log_id, "failed", "invalid_payload")
            return ActionOutcome(True, S_ERROR, "confused")

        if not self._mgr.phone_connected:
            await self._set_log(p.log_id, "failed", "phone_offline")
            return ActionOutcome(True, S_PHONE_OFFLINE, "sad")

        await self._mgr.send_to_phone(msg.model_dump(exclude_none=True))
        self._inflight[p.log_id] = (self._now() + settings.ACTION_RESULT_TTL_SECONDS, kind)
        await self._set_log(p.log_id, "dispatched")
        return ActionOutcome(True, speech, "happy")

    # ── phone → backend ──────────────────────────────────────────────────

    async def on_action_result(self, msg: ActionResultMsg) -> None:
        """Phone reports the outcome. Only ids we actually dispatched are accepted (one-shot)."""
        now = self._now()
        self._inflight = {k: v for k, v in self._inflight.items() if v[0] > now}
        if msg.id not in self._inflight:
            logger.warning("Ignoring action_result for unknown/expired id %s", msg.id)
            return
        del self._inflight[msg.id]
        if msg.ok:
            await self._set_log(msg.id, "completed")
        else:
            await self._set_log(msg.id, "failed", (msg.error or "phone_error"))
            await self.say("الموبايل مقدرش ينفّذ الطلب.", "sad")

    # ── reminders ────────────────────────────────────────────────────────

    async def _create_reminder(self, p: _Pending) -> ActionOutcome:
        params = p.intent.params
        now_local = datetime.now().astimezone()
        target_local = compute_target_time(params, now_local)
        target_utc = target_local.astimezone(timezone.utc).replace(tzinfo=None)
        title = params["title"]
        is_medicine = "دوا" in fold(title)
        async with self._session() as db:
            esc_id = None
            if is_medicine:
                row = (await db.execute(
                    select(Contact).where(
                        Contact.notify_on_missed == True,  # noqa: E712
                        Contact.is_allowlisted == True,    # noqa: E712
                        or_(Contact.user_id == p.user_id, Contact.user_id.is_(None)),
                    ).limit(1)
                )).scalar_one_or_none()
                esc_id = row.id if row else None
            db.add(Reminder(
                user_id=p.user_id, title=title,
                reminder_type="medicine" if is_medicine else "task",
                target_time=target_utc, recurrence="once", escalation_contact_id=esc_id,
            ))
            await db.commit()
        # Log the *type*, never the title (a medicine name is health data).
        await self._set_log(p.log_id, "completed")
        if "rel_minutes" in params:
            when = f"كمان {params['rel_minutes']} دقيقة"
        else:
            when = f"الساعة {target_local.hour % 12 or 12}" + (f":{target_local.minute:02d}" if target_local.minute else "")
        return ActionOutcome(True, f"تمام، هفكرك بـ{title} {when}.", "happy")

    def mark_awaiting_ack(self, reminder_id: int) -> None:
        if reminder_id not in self._awaiting_ack:
            self._awaiting_ack.append(reminder_id)

    async def acknowledge_reminder(
        self, reminder_id: Optional[int] = None, *, user_id: Optional[int] = None
    ) -> Optional[int]:
        rid = reminder_id if reminder_id is not None else (self._awaiting_ack[-1] if self._awaiting_ack else None)
        if rid is None:
            return None
        async with self._session() as db:
            rem = await db.get(Reminder, rid)
            if rem is None or (user_id is not None and rem.user_id not in (None, user_id)):
                return None
            if rem.status in ("announced", "pending"):
                rem.acknowledged_at = datetime.now(timezone.utc).replace(tzinfo=None)
                rem.status = "acknowledged"
                advance_recurrence(rem)
                await db.commit()
        self._awaiting_ack = [i for i in self._awaiting_ack if i != rid]
        return rid

    async def dispatch_escalation(self, contact: Contact, text: str, mode: str) -> bool:
        """
        Notify a family member about an unacknowledged reminder. The recipient was
        chosen by the owner when setting up the reminder (opt-in), so this does not
        go through the voice challenge; it is still audited.
        """
        number = normalize_phone(contact.phone_number)
        if number is None or not self._mgr.phone_connected:
            return False
        log_id = await self._new_log(
            user_id=contact.user_id, action_type="reminder", target=contact.name,
            level=1, status="requested", reason="escalation",
        )
        try:
            if mode == "call":
                msg: Any = CallCmdMsg(id=log_id, contact=(contact.slug or contact.name),
                                      number=number, speaker=settings.DEFAULT_CALL_SPEAKERPHONE)
            else:
                msg = MsgCmdMsg(id=log_id, app="whatsapp", to=(contact.slug or contact.name),
                                number=number, text=sanitize_free_text(text, 500))
        except ValidationError:
            await self._set_log(log_id, "failed", "invalid_payload")
            return False
        await self._mgr.send_to_phone(msg.model_dump(exclude_none=True))
        self._inflight[log_id] = (self._now() + settings.ACTION_RESULT_TTL_SECONDS, "reminder")
        await self._set_log(log_id, "dispatched", "escalation")
        return True

    # ── introspection (REST) ─────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        p = self._pending
        return {
            "in_call": self.in_call(),
            "call_state": self._call_state,
            "locked": self.is_locked(),
            "pending_stage": p.stage if p else None,
            "pending_id": p.log_id if p else None,
            "phone_connected": self._mgr.phone_connected,
        }


def _deny_speech(d: GuardDecision) -> str:
    return {
        "no_voiceprint": S_NO_VOICEPRINT,
        "not_verified": S_NOT_VERIFIED,
        "permission": S_PERMISSION,
        "not_allowed": S_NOT_ALLOWED,
    }.get(d.reason, S_NOT_ALLOWED)
