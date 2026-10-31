"""
Unit tests for Chapter 14 Phone Actions System:
- ActionPlanner (deterministic intent extraction)
- ActionGuard (4-tier security evaluation)
- RandomChallengeService (anti-replay Egyptian challenge)
- Contacts resolution and phone normalization
- PhoneActionService state machine & verbal confirmation
"""

import asyncio
from datetime import datetime, timezone
import pytest

from app.models.contact import Contact
from app.services.phone_action.challenge import RandomChallengeService
from app.services.phone_action.contacts import (
    contact_keys,
    extract_number,
    mask_number,
    match_contact,
    normalize_phone,
)
from app.services.phone_action.guard import (
    ALLOW,
    CHALLENGE,
    DENY,
    ActionGuard,
)
from app.services.phone_action.planner import (
    APP_OPEN,
    CALL,
    MSG,
    READ_NOTIFICATIONS,
    REMINDER,
    SENSITIVE,
    ActionPlanner,
)
from app.services.phone_action.service import PhoneActionService
from app.services.voice_verification.speaker_service import VerificationResult


# ── ActionPlanner Tests ───────────────────────────────────────────────────────

class TestActionPlanner:
    def setup_method(self):
        self.planner = ActionPlanner()

    def test_call_intent_extraction(self):
        # Direct calls
        i1 = self.planner.plan("كلّم ماما")
        assert i1 is not None and i1.kind == CALL
        assert "ماما" in i1.raw_light

        i2 = self.planner.plan("اتصل بـ بابا")
        assert i2 is not None and i2.kind == CALL

        i3 = self.planner.plan("لو سمحت رن على أحمد")
        assert i3 is not None and i3.kind == CALL

        # Direct phone number call
        i4 = self.planner.plan("كلّم 01012345678")
        assert i4 is not None and i4.kind == CALL

    def test_app_and_navigation_intent(self):
        # Open maps
        i1 = self.planner.plan("افتح الخرايط")
        assert i1 is not None and i1.kind == APP_OPEN
        assert i1.params.get("app") == "maps"

        # Open maps with destination
        i2 = self.planner.plan("افتح الخرايط ووديني الشغل")
        assert i2 is not None and i2.kind == APP_OPEN
        assert i2.params.get("app") == "maps"
        assert "الشغل" in i2.params.get("query", "")

        # Direct navigation verb
        i3 = self.planner.plan("وديني المطار")
        assert i3 is not None and i3.kind == APP_OPEN
        assert i3.params.get("app") == "maps"
        assert "المطار" in i3.params.get("query", "")

        # Open WhatsApp
        i4 = self.planner.plan("افتح الواتساب")
        assert i4 is not None and i4.kind == APP_OPEN
        assert i4.params.get("app") == "whatsapp"

        # Play Quran/music hint
        i5 = self.planner.plan("شغّل قرآن")
        assert i5 is not None and i5.kind == APP_OPEN
        assert i5.params.get("app") == "music"

    def test_message_intent(self):
        i1 = self.planner.plan("ابعت لأحمد إني جاي متأخر")
        assert i1 is not None and i1.kind == MSG
        assert "أحمد" in i1.raw_light

        i2 = self.planner.plan("ارسل رسالة لماما هتاخر نص ساعة")
        assert i2 is not None and i2.kind == MSG

    def test_reminder_intent(self):
        i1 = self.planner.plan("فكّرني بالدوا الساعة 8")
        assert i1 is not None and i1.kind == REMINDER
        assert "دوا" in i1.params.get("title", "")

        i2 = self.planner.plan("فكّرني بالميتنج كمان 15 دقيقة")
        assert i2 is not None and i2.kind == REMINDER
        assert "الميتنج" in i2.params.get("title", "")

    def test_read_notifications_intent(self):
        i1 = self.planner.plan("اقرألي الرسايل الجديدة")
        assert i1 is not None and i1.kind == READ_NOTIFICATIONS

        i2 = self.planner.plan("اقرالي الإشعارات")
        assert i2 is not None and i2.kind == READ_NOTIFICATIONS

    def test_sensitive_operation_intent(self):
        i1 = self.planner.plan("امسح كل الذكريات")
        assert i1 is not None and i1.kind == SENSITIVE
        assert i1.params.get("op") == "memory_wipe"

        i2 = self.planner.plan("ادفع 500 جنيه لمحمد")
        assert i2 is not None and i2.kind == SENSITIVE
        assert i2.params.get("op") == "payment"

    def test_conversational_queries_not_planned(self):
        # General conversational input must return None so LLM handles it
        assert self.planner.plan("الجو عامل إيه في القاهرة؟") is None
        assert self.planner.plan("إزيك يا نيبولا عامل إيه؟") is None
        assert self.planner.plan("مين هو مازن؟") is None


# ── Contacts & Phone Resolution Tests ─────────────────────────────────────────

class TestContactsResolution:
    def test_contact_matching_with_aliases(self):
        c_mama = Contact(
            id=1,
            name="ماما",
            aliases="مامي,ماميتي,الوالدة",
            phone_number="+201012345678",
            is_allowlisted=True,
        )
        c_ahmed = Contact(
            id=2,
            name="أحمد",
            aliases="حمادة",
            phone_number="+201087654321",
            is_allowlisted=True,
        )
        contacts = [c_mama, c_ahmed]

        # Exact match
        m1 = match_contact("ماما", "ماما", contacts, require_full=True)
        assert m1.contact is not None and m1.contact.id == 1

        # Alias match
        m2 = match_contact("الوالده", "الوالدة", contacts, require_full=True)
        assert m2.contact is not None and m2.contact.id == 1

        # Prefix match for messages
        m3 = match_contact("احمد اني جاي", "أحمد إني جاي", contacts, require_full=False)
        assert m3.contact is not None and m3.contact.id == 2
        assert "إني جاي" in m3.remainder_light

    def test_phone_normalization_and_masking(self):
        assert normalize_phone("01012345678") == "01012345678"
        assert normalize_phone("+20 10 1234 5678") == "+201012345678"
        assert normalize_phone("invalid-num") is None
        assert normalize_phone("123") is None  # Too short

        masked = mask_number("+201012345678")
        assert masked.startswith("+2010")
        assert masked.endswith("5678")
        assert "*" in masked

    def test_extract_spoken_number(self):
        num = extract_number("كلم 01012345678")
        assert num == "01012345678"


# ── Random Challenge Service Tests ────────────────────────────────────────────

class TestRandomChallengeService:
    def setup_method(self):
        self.svc = RandomChallengeService()

    def test_challenge_generation_and_matching(self):
        ch = self.svc.issue()
        assert ch.spoken.startswith("قول:")
        assert ch.phrase

        # Exact match
        assert self.svc.text_matches(ch, ch.spoken)
        assert self.svc.text_matches(ch, ch.phrase)

        # Gibberish or mismatch
        assert not self.svc.text_matches(ch, "كلام تاني خالص غير التحدي")


# ── ActionGuard Security Tier Tests ───────────────────────────────────────────

class TestActionGuard:
    def setup_method(self):
        self.guard = ActionGuard()

    def test_level_0_app_open_allowed_without_voiceprint(self):
        # Level 0 actions (music) are allowed even for unverified guest
        ver = VerificationResult(available=False, enrolled=False)
        intent = ActionPlanner().plan("شغّل قرآن")
        dec = self.guard.evaluate(intent, ver)
        assert dec.action == ALLOW
        assert dec.required_level == 0

    def test_level_1_call_allowlisted_requires_voiceprint(self):
        c_mama = Contact(
            id=1,
            name="ماما",
            phone_number="+201012345678",
            is_allowlisted=True,
            required_level=1,
            requires_confirmation=True,
        )
        intent = ActionPlanner().plan("كلّم ماما")
        # Unverified voice -> fails closed (DENY)
        unverified = VerificationResult(available=True, enrolled=True, passed_l1=False)
        dec_fail = self.guard.evaluate(intent, unverified, contact=c_mama)
        assert dec_fail.action == DENY

        # Verified voice (passed L1) -> ALLOW with verbal confirmation
        verified = VerificationResult(
            available=True, enrolled=True, passed_l1=True, user_id=1, speaker_name="مازن", max_level=2
        )
        dec_ok = self.guard.evaluate(intent, verified, contact=c_mama)
        assert dec_ok.action == ALLOW
        assert dec_ok.needs_confirmation is True

    def test_level_2_unlisted_target_triggers_challenge(self):
        # Calling an unlisted contact or non-allowlisted number is Level 2
        verified = VerificationResult(
            available=True, enrolled=True, passed_l1=True, user_id=1, speaker_name="مازن", max_level=2
        )
        intent = ActionPlanner().plan("كلّم 01099998888")
        dec = self.guard.evaluate(intent, verified, contact=None, unlisted_number=True)
        assert dec.action == CHALLENGE
        assert dec.required_level == 2

    def test_level_3_sensitive_requires_external_confirmation(self):
        verified = VerificationResult(
            available=True,
            enrolled=True,
            passed_l1=True,
            passed_l2=True,
            user_id=1,
            speaker_name="مازن",
            max_level=3,
        )
        intent = ActionPlanner().plan("امسح كل الذكريات")
        dec = self.guard.evaluate(intent, verified)
        # Level 3 requires challenge first then external confirmation
        assert dec.required_level == 3
        assert dec.needs_external is True


# ── PhoneActionService State Machine Tests ────────────────────────────────────

@pytest.mark.asyncio
class TestPhoneActionServiceFlow:
    async def test_full_verbal_confirmation_flow(self):
        dispatched_messages = []

        class DummyManager:
            phone_connected = True

            async def send_to_phone(self, msg):
                dispatched_messages.append(msg)

            async def broadcast_to_desks(self, msg):
                pass

        class DummySession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            def add(self, obj):
                if hasattr(obj, "id") and obj.id is None:
                    obj.id = 1

            async def commit(self):
                pass

            async def get(self, model, ident):
                return None

            async def execute(self, stmt):
                class DummyResult:
                    def scalars(self):
                        class DummyScalars:
                            def all(self):
                                return [
                                    Contact(
                                        id=1,
                                        name="ماما",
                                        slug="mama",
                                        phone_number="+201012345678",
                                        is_allowlisted=True,
                                        requires_confirmation=True,
                                        required_level=1,
                                    )
                                ]
                        return DummyScalars()
                return DummyResult()

        svc = PhoneActionService(
            session_factory=DummySession,
            ws_manager=DummyManager(),
        )

        ver = VerificationResult(
            available=True,
            enrolled=True,
            passed_l1=True,
            user_id=1,
            speaker_name="مازن",
            max_level=2,
        )

        # 1. User says "كلّم ماما"
        out1 = await svc.handle_utterance("كلّم ماما", ver)
        assert out1.handled is True
        assert "أكلّم ماما؟" in (out1.speech or "")

        # 2. User confirms with "أيوه"
        out2 = await svc.handle_utterance("أيوه", ver)
        assert out2.handled is True
        assert "بكلّم ماما" in (out2.speech or "")

        # Verify command dispatched to phone
        assert len(dispatched_messages) == 1
        cmd = dispatched_messages[0]
        assert cmd.get("t") == "call"
        assert cmd.get("contact") == "mama"
        assert cmd.get("number") == "+201012345678"

    async def test_verbal_rejection_flow(self):
        class DummyManager:
            phone_connected = True

            async def send_to_phone(self, msg):
                pass

            async def broadcast_to_desks(self, msg):
                pass

        class DummySession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            def add(self, obj):
                if hasattr(obj, "id") and obj.id is None:
                    obj.id = 1

            async def commit(self):
                pass

            async def get(self, model, ident):
                return None

            async def execute(self, stmt):
                class DummyResult:
                    def scalars(self):
                        class DummyScalars:
                            def all(self):
                                return [
                                    Contact(
                                        id=1,
                                        name="ماما",
                                        slug="mama",
                                        phone_number="+201012345678",
                                        is_allowlisted=True,
                                        requires_confirmation=True,
                                        required_level=1,
                                    )
                                ]
                        return DummyScalars()
                return DummyResult()

        svc = PhoneActionService(
            session_factory=DummySession,
            ws_manager=DummyManager(),
        )

        ver = VerificationResult(
            available=True, enrolled=True, passed_l1=True, user_id=1, speaker_name="مازن", max_level=2
        )

        # Step 1: Request
        await svc.handle_utterance("كلّم ماما", ver)

        # Step 2: Cancel with "لأ"
        out2 = await svc.handle_utterance("لأ خلاص", ver)
        assert out2.handled is True
        assert "لغيت الطلب" in (out2.speech or "")
