"""
ActionGuard — the security policy for phone actions
(benefits_section.docx §14.3 levels + §14.5 "Guard Action").

Pure and side-effect free: given an intent, its resolved target and the speaker's
verified identity, it answers "may this run, and what extra proof is needed?".
Everything stateful (pending confirmations, lockouts, DB) lives in the service.

Levels
  0  guest            — no verification (general chat, media)
  1  voiceprint       — allow-listed calls/messages, apps, reminders
  2  voice+challenge  — unknown numbers, reading notifications, sensitive apps
  3  L2 + external    — payments, memory wipe, add user, change permissions

The policy FAILS CLOSED: unknown apps/operations are denied, and any request at
Level ≥ 1 is denied outright when no verified identity exists.
"""

from dataclasses import dataclass
from typing import Optional

from app.services.phone_action.planner import (
    APP_OPEN,
    CALL,
    MSG,
    READ_NOTIFICATIONS,
    REMINDER,
    SENSITIVE,
    Intent,
)
from app.services.voice_verification.speaker_service import VerificationResult

# App id → minimum level. Anything not listed is refused (allow-list, not deny-list).
APP_LEVELS = {
    "music": 0,
    "maps": 1,
    "whatsapp": 1,
    "telegram": 1,
    "youtube": 1,
    "spotify": 1,
    "camera": 1,
}

ALLOW = "allow"
CHALLENGE = "challenge"
DENY = "deny"


@dataclass(frozen=True)
class GuardDecision:
    action: str                      # allow | challenge | deny
    required_level: int = 0
    reason: str = ""                 # machine code for logs
    needs_confirmation: bool = False  # verbal «أكلّم ماما؟»
    needs_external: bool = False      # Level-3 control-room approval


def required_level(intent: Intent, *, contact=None, unlisted_number: bool = False) -> Optional[int]:
    """Minimum level for this intent, or None if the intent is never permitted."""
    if intent.kind == SENSITIVE:
        return 3
    if intent.kind == READ_NOTIFICATIONS:
        return 2
    if intent.kind == REMINDER:
        return 1
    if intent.kind == APP_OPEN:
        app = intent.params.get("app")
        return APP_LEVELS.get(app) if app else None
    if intent.kind in (CALL, MSG):
        if contact is not None:
            return max(1, int(getattr(contact, "required_level", 1) or 1))
        if unlisted_number and intent.kind == CALL:
            return 2
        return None  # unknown contact → never
    return None


class ActionGuard:
    def evaluate(
        self,
        intent: Intent,
        ident: Optional[VerificationResult],
        *,
        contact=None,
        unlisted_number: bool = False,
    ) -> GuardDecision:
        req = required_level(intent, contact=contact, unlisted_number=unlisted_number)
        if req is None:
            return GuardDecision(DENY, reason="not_allowed")

        if req == 0:
            return GuardDecision(ALLOW, required_level=0)

        # ── identity gates (Level ≥ 1) ────────────────────────────────────
        if ident is None or not ident.available or not ident.enrolled:
            return GuardDecision(DENY, required_level=req, reason="no_voiceprint")
        if not ident.passed_l1 or ident.user_id is None:
            return GuardDecision(DENY, required_level=req, reason="not_verified")
        if ident.max_level < req:
            return GuardDecision(DENY, required_level=req, reason="permission")

        # ── step-up for Level ≥ 2 ─────────────────────────────────────────
        if req >= 2:
            return GuardDecision(
                CHALLENGE,
                required_level=req,
                needs_confirmation=intent.kind in (CALL, MSG),
                needs_external=req >= 3,
            )

        # ── Level 1 ───────────────────────────────────────────────────────
        needs_confirm = False
        if intent.kind == MSG:
            needs_confirm = True  # message body is read back; always confirmed
        elif intent.kind == CALL:
            needs_confirm = bool(getattr(contact, "requires_confirmation", True)) if contact is not None else True
        return GuardDecision(ALLOW, required_level=req, needs_confirmation=needs_confirm)
