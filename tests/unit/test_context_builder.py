"""
Unit tests for context_builder.py — Grounding context builder across Personalities,
Memories (RAG), Vision (FaceProfile & UniFace), Voice Clone, and Diagnostics.

Validates the 6 core specifications from Milestone 4:
1. test_context_builder_grounded_with_memories: Grounded prompt when memories exist
2. test_context_builder_empty_memories_refusal: Deterministic refusal when no memories exist
3. test_context_builder_greeting_and_persona: Welcoming Egyptian persona for greetings & creator queries
4. test_context_builder_vision_and_screen_awareness: Camera face profile and screen photo formatting
5. test_context_builder_hardware_diagnostics_integration: Phone, desktop, and ESP32 states
6. test_context_builder_negative_grounding_directives: Anti-hallucination rules for unrecorded details
"""

import time
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.session import init_db, AsyncSessionLocal
from app.models.personality import Personality
from app.models.face_profile import FaceProfile
from app.models.contact import Contact
from app.models.reminder import Reminder
from app.websocket.manager import manager
from app.services.ai.context_builder import (
    build_grounding_context,
    is_greeting_or_persona_inquiry,
    GroundingInfo,
)


@pytest.mark.asyncio
async def test_context_builder_grounded_with_memories():
    """
    1. test_context_builder_grounded_with_memories:
    Validates prompt assembly when memories are returned by RAG.
    Asserts:
    - 'سياق الذاكرة المعتمدة'
    - '[المصدر 1]' and '[المصدر 2]'
    - 'Strict RAG Grounding'
    - Absence of English instruction templates / translation leakages
    - Presence of system status block ('معلومات النظام والسياق النشط:')
    - Correct GroundingInfo structure and returned memories list
    """
    await init_db()
    async with AsyncSessionLocal() as session:
        p = Personality(
            name=f"نيبولا_تست_{int(time.time()*1000)}",
            system_prompt="أنت روبوت ذكي يتحدث بالعامية المصرية.",
            dialect="cairo",
            language_mix="ar_en",
            is_active=True,
        )
        session.add(p)
        await session.flush()

        retrieved_memories = [
            "أحمد مهندس برمجيات مقيم في حلوان ويعمل على روبوتات الذكاء الاصطناعي.",
            "أحمد يحب شرب القهوة المضبوط صباحاً.",
        ]

        with patch("app.services.ai.context_builder._rag_service.retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = retrieved_memories

            prompt, memories, grounding, p_id = await build_grounding_context(
                db=session,
                personality_id=p.id,
                message="أحمد شغال إيه وبيحب يشرب إيه؟",
            )

            # Grounding and return value verifications
            assert p_id == p.id
            assert memories == retrieved_memories
            assert isinstance(grounding, GroundingInfo)
            assert grounding.memories == retrieved_memories

            # Strict RAG Grounding Header & Directives
            assert "سياق الذاكرة المعتمدة:" in prompt
            assert "[المصدر 1]: أحمد مهندس برمجيات مقيم في حلوان ويعمل على روبوتات الذكاء الاصطناعي." in prompt
            assert "[المصدر 2]: أحمد يحب شرب القهوة المضبوط صباحاً." in prompt
            assert "Strict RAG Grounding" in prompt
            assert "توجيهات التشغيل والاستناد الصارم للذاكرة" in prompt
            assert "استخرج الإجابة حصراً وبدقة متناهية من سياق الذاكرة المعتمدة أدناه" in prompt

            # Presence of system status block
            assert "معلومات النظام والسياق النشط:" in prompt
            assert "الشخصية النشطة:" in prompt
            assert "التشخيص وحالة الأجهزة:" in prompt

            # Absence of legacy English instruction templates / translation leakages
            assert "You are a helpful assistant" not in prompt
            assert "Memory Context:" not in prompt
            assert "to_english_memory" not in prompt
            assert "English Context:" not in prompt


@pytest.mark.asyncio
async def test_context_builder_empty_memories_refusal():
    """
    2. test_context_builder_empty_memories_refusal:
    Validates refusal prompt assembly when no memories exist for an inquiry.
    Asserts:
    - Standard deterministic refusal phrasing: "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
    - Presence of system status block ('معلومات النظام والسياق النشط:')
    - Zero memories returned
    - Strict warning against hallucination and guessing
    """
    await init_db()
    async with AsyncSessionLocal() as session:
        p = Personality(
            name=f"نيبولا_رفض_{int(time.time()*1000)}",
            system_prompt="أنت روبوت ذكي.",
            dialect="cairo",
            is_active=True,
        )
        session.add(p)
        await session.flush()

        with patch("app.services.ai.context_builder._rag_service.retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = []

            # Non-greeting, unrecorded information request
            prompt, memories, grounding, p_id = await build_grounding_context(
                db=session,
                personality_id=p.id,
                message="أحمد مرتبه كام في الشهر بالظبط؟",
            )

            assert memories == []
            assert grounding.memories == []

            # Refusal and anti-hallucination assertions
            assert '"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"' in prompt
            assert "سياق الذاكرة: لا توجد أي معلومات مسجلة متعلقة بهذا السؤال." in prompt
            assert "تنبيه صارم لمنع الهلوسة والتخمين:" in prompt
            assert "يجب الاعتذار فوراً وبدقة بدون أي تأليف بالعبارة المحددة التالية فقط:" in prompt
            assert "يُمنع منعاً باتاً تخمين أو افتراض أي إجابة خارج ما هو مسجل في الذاكرة." in prompt
            assert "اختم ردك دائماً بوسم المشاعر [wave]." in prompt

            # System status block preserved
            assert "معلومات النظام والسياق النشط:" in prompt
            assert "الشخصية النشطة:" in prompt
            assert "التشخيص وحالة الأجهزة:" in prompt


@pytest.mark.asyncio
async def test_context_builder_greeting_and_persona():
    """
    3. test_context_builder_greeting_and_persona:
    Validates prompt assembly for greetings and persona inquiries without memories.
    Asserts:
    - Accuracy of is_greeting_or_persona_inquiry helper
    - Welcoming Egyptian Cairo dialect guidance for greeting inquiries
    - Presence of robot name and creator name in prompt
    - Prompt asks user how to help them
    - Emotion tag recommendation in greeting branch
    - Presence of system status block
    """
    # 1. Helper function checks
    assert is_greeting_or_persona_inquiry("صباح الخير") is True
    assert is_greeting_or_persona_inquiry("مساء الورد") is True
    assert is_greeting_or_persona_inquiry("ازيك عامل ايه") is True
    assert is_greeting_or_persona_inquiry("أنت مين") is True
    assert is_greeting_or_persona_inquiry("مين صممك") is True
    assert is_greeting_or_persona_inquiry("مين برمجك وطورك") is True
    assert is_greeting_or_persona_inquiry("عرف نفسك") is True
    assert is_greeting_or_persona_inquiry("what is your name") is True
    assert is_greeting_or_persona_inquiry("hello") is True
    assert is_greeting_or_persona_inquiry("كم المسافة بين القاهرة والإسكندرية؟") is False

    await init_db()
    async with AsyncSessionLocal() as session:
        p_name = f"نيبولا_تحية_{int(time.time()*1000)}"
        p = Personality(
            name=p_name,
            system_prompt="صممه مازن عبد الرحيم.",
            dialect="cairo",
            is_active=True,
        )
        session.add(p)
        await session.flush()

        with patch("app.services.ai.context_builder._rag_service.retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = []

            # A. Greeting test
            prompt_greet, memories_greet, _, _ = await build_grounding_context(
                db=session,
                personality_id=p.id,
                message="صباح الخير يا نيبولا",
            )
            assert memories_greet == []
            assert "المستخدم يحييك أو يسأل عن هويتك وصانعك:" in prompt_greet
            assert "رحب بالمستخدم بلطف بلهجة مصرية قاهرية ودودة" in prompt_greet
            assert p_name in prompt_greet
            assert "مازن عبد الرحيم" in prompt_greet
            assert "واسأله كيف تساعده اليوم" in prompt_greet
            assert "معلومات النظام والسياق النشط:" in prompt_greet

            # B. Persona identity inquiry test
            prompt_who, memories_who, _, _ = await build_grounding_context(
                db=session,
                personality_id=p.id,
                message="أنت مين ومين اللي صممك؟",
            )
            assert memories_who == []
            assert "المستخدم يحييك أو يسأل عن هويتك وصانعك:" in prompt_who
            assert "عرفه بنفسك كـ" in prompt_who
            assert "مازن عبد الرحيم" in prompt_who
            assert "معلومات النظام والسياق النشط:" in prompt_who


@pytest.mark.asyncio
async def test_context_builder_vision_and_screen_awareness():
    """
    4. test_context_builder_vision_and_screen_awareness:
    Validates camera face profile, verified speaker, and screen photo profile formatting.
    Asserts:
    - Camera face profile line in system status block
    - Verified speaker line in system status block
    - Screen photo display line in system status block
    - Correct population of GroundingInfo.faces (active person, photo URL, detection flags)
    """
    await init_db()
    async with AsyncSessionLocal() as session:
        face_name = f"مازن_شاشة_{int(time.time()*1000)}"
        face = FaceProfile(
            name=face_name,
            embedding=[0.1] * 128,
            photo_path=f"photos/{face_name}.jpg",
        )
        session.add(face)
        await session.flush()

        mock_face_info = {
            "detected": True,
            "is_recent": True,
            "face_id": face_name,
        }

        mock_face_svc = MagicMock()
        mock_face_svc.get_current_face_info.return_value = mock_face_info

        with patch("app.websocket.handlers.get_face_service", return_value=mock_face_svc), \
             patch("app.services.ai.context_builder._rag_service.retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = []

            prompt, _, grounding, _ = await build_grounding_context(
                db=session,
                personality_id=None,
                message=f"وريني صورة {face_name}",
                verified_speaker=face_name,
            )

            # Assertions for system status block
            assert f"- الكاميرا: الشخص أمامك هو {face_name}." in prompt
            assert f"- الصوت: تم التعرف على المتحدث بالبصمة الصوتية: {face_name}." in prompt
            assert f"- شاشة العرض والصور: صورة {face_name} مسجلة في النظام ومتاحة للعرض على الشاشة." in prompt

            # Assertions for GroundingInfo structure
            assert grounding.faces["currently_detected"] is True
            assert grounding.faces["active_person"] == face_name
            assert grounding.faces["photo_url"] == f"/api/v1/faces/{face_name}/photo"
            assert grounding.faces["photo_path"] == f"photos/{face_name}.jpg"
            assert grounding.faces["is_photo_inquiry"] is True
            assert grounding.voice_clone["verified_speaker"] == face_name


@pytest.mark.asyncio
async def test_context_builder_hardware_diagnostics_integration():
    """
    5. test_context_builder_hardware_diagnostics_integration:
    Validates formatting of phone, desktop, and ESP32 hardware states in the system status block.
    Asserts:
    - All-connected state formatting ('الهاتف (متصل) | الحاسوب (متصل) | شريحة الروبوت (متصل)')
    - All-disconnected state formatting ('الهاتف (غير متصل) | الحاسوب (غير متصل) | شريحة الروبوت (غير متصل)')
    - Mixed connection topologies formatting
    - GroundingInfo.diagnostics boolean values match hardware status
    """
    await init_db()
    async with AsyncSessionLocal() as session:
        with patch("app.services.ai.context_builder._rag_service.retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = []

            # Case 1: All hardware connected
            with patch.object(manager, "status", return_value={"phone": True, "desktops": 1, "esp32": True}):
                prompt_all, _, grounding_all, _ = await build_grounding_context(
                    db=session,
                    personality_id=None,
                    message="ما هي حالة الأجهزة الآن؟",
                )
                assert "- التشخيص وحالة الأجهزة: الهاتف (متصل) | الحاسوب (متصل) | شريحة الروبوت (متصل)" in prompt_all
                assert grounding_all.diagnostics["phone_connected"] is True
                assert grounding_all.diagnostics["desktop_connected"] is True
                assert grounding_all.diagnostics["esp_connected"] is True

            # Case 2: All hardware disconnected
            with patch.object(manager, "status", return_value={"phone": False, "desktops": 0, "esp32": False}):
                prompt_none, _, grounding_none, _ = await build_grounding_context(
                    db=session,
                    personality_id=None,
                    message="ما هي حالة الأجهزة الآن؟",
                )
                assert "- التشخيص وحالة الأجهزة: الهاتف (غير متصل) | الحاسوب (غير متصل) | شريحة الروبوت (غير متصل)" in prompt_none
                assert grounding_none.diagnostics["phone_connected"] is False
                assert grounding_none.diagnostics["desktop_connected"] is False
                assert grounding_none.diagnostics["esp_connected"] is False

            # Case 3: Mixed connection (phone connected, desktop disconnected, esp32 connected)
            with patch.object(manager, "status", return_value={"phone": True, "desktops": 0, "esp": True}):
                prompt_mix, _, grounding_mix, _ = await build_grounding_context(
                    db=session,
                    personality_id=None,
                    message="ما هي حالة الأجهزة الآن؟",
                )
                assert "- التشخيص وحالة الأجهزة: الهاتف (متصل) | الحاسوب (غير متصل) | شريحة الروبوت (متصل)" in prompt_mix
                assert grounding_mix.diagnostics["phone_connected"] is True
                assert grounding_mix.diagnostics["desktop_connected"] is False
                assert grounding_mix.diagnostics["esp_connected"] is True


@pytest.mark.asyncio
async def test_context_builder_negative_grounding_directives():
    """
    6. test_context_builder_negative_grounding_directives:
    Validates anti-hallucination rules and strict prohibitions against guessing unrecorded details
    (specifically phone numbers, passwords, and sensitive financial data).
    Asserts:
    - Explicit prohibition against guessing phone numbers and passwords
    - Exemplar direct grounding & refusal Q&A in prompt
    - Contacts privacy enforcement: only names appear, zero phone numbers injected into prompt
    - Active reminders formatted cleanly
    """
    await init_db()
    async with AsyncSessionLocal() as session:
        contact_name = f"د. أحمد مصطفى_{int(time.time()*1000)}"
        private_phone = "01099887766"
        c = Contact(
            name=contact_name,
            slug=f"dr_ahmed_{int(time.time()*1000)}",
            phone_number=private_phone,
            is_allowlisted=True,
        )
        session.add(c)

        reminder_title = f"موعد صيانة المحرك_{int(time.time()*1000)}"
        r = Reminder(
            title=reminder_title,
            reminder_type="task",
            recurrence="once",
            target_time=datetime.now(timezone.utc).replace(tzinfo=None),
            status="pending",
            is_active=True,
        )
        session.add(r)
        await session.flush()

        retrieved_memories = [
            f"{contact_name} هو استشاري المشروع ومقره مدينة نصر.",
        ]

        with patch("app.services.ai.context_builder._rag_service.retrieve", new_callable=AsyncMock) as mock_retrieve:
            mock_retrieve.return_value = retrieved_memories

            prompt, memories, _, _ = await build_grounding_context(
                db=session,
                personality_id=None,
                message=f"ممكن تديني رقم تليفون {contact_name} أو كلمة سر النظام؟",
            )

            # Strict negative grounding and anti-hallucination directives
            assert "ممنوع منعاً باتاً تخمين، تأليف، أو افتراض أي وقائع أو ذكريات أو تفاصيل لم تُذكر صراحة في المصادر." in prompt
            assert "إذا كان السؤال يطلب تفصيلة أو رقماً غير موجود نصاً في الذاكرة أدناه" in prompt
            assert "أرقام الهواتف الشخصية" in prompt
            assert "كلمات السر" in prompt
            assert "البيانات المالية" in prompt
            assert '"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"' in prompt

            # Illustrative few-shot examples embedded in prompt
            assert "أمثلة توضيحية لأسلوب الإجابة المباشر ومنع التأليف:" in prompt
            assert "سؤال: ممكن تديني رقم تليفون أحمد الشخصي؟" in prompt
            assert "إجابة: المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]" in prompt

            # Contact privacy: Contact name is in system status block, but private phone number is NEVER injected
            assert contact_name in prompt
            assert private_phone not in prompt
            assert "- جهات الاتصال المسموحة (أسماء فقط):" in prompt

            # Active reminder is included in system status block
            assert reminder_title in prompt
            assert "- التذكيرات الحالية:" in prompt
