"""
Test Suite for Dynamic Multi-Personality Routing & Zero-Hardcoded Creator Resolution
"""

import sys
import os
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

# Ensure UTF-8 output on Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.personality import Personality
from app.models.user import User
from app.services.ai.context_builder import (
    extract_clean_personality_tokens,
    match_personality_in_message,
    match_personality_by_identity,
    resolve_creator_name,
    build_grounding_context,
)


def test_token_extraction():
    print("[1] Testing Personality Token Extraction...", flush=True)
    p1_tokens = extract_clean_personality_tokens("توت (Default)")
    assert "توت" in p1_tokens, f"Expected 'توت' in {p1_tokens}"
    assert "default" not in p1_tokens, f"Noise word 'default' should be excluded: {p1_tokens}"

    p2_tokens = extract_clean_personality_tokens("سارة / Sara (AI Assistant)")
    assert "ساره" in p2_tokens, f"Expected normalized 'ساره' in {p2_tokens}"
    assert "sara" in p2_tokens, f"Expected 'sara' in {p2_tokens}"

    p3_tokens = extract_clean_personality_tokens("د. أحمد فتحي")
    assert "احمد" in p3_tokens or "د. احمد فتحي" in p3_tokens

    p4_tokens = extract_clean_personality_tokens("Alex-Dev")
    assert "alex" in p4_tokens
    print("  -> Token extraction passed successfully!")


def test_message_personality_matching():
    print("[2] Testing Dynamic Personality Routing from User Message...", flush=True)
    p_tut = Personality(id=1, name="توت (Default)", is_active=True)
    p_sara = Personality(id=2, name="سارة (AI Assistant)", is_active=False)
    p_ahmed = Personality(id=3, name="أحمد فتحي", is_active=False)
    p_alex = Personality(id=4, name="Alex", is_active=False)
    p_omar = Personality(id=5, name="المهندس عمر", is_active=False)

    personalities = [p_tut, p_sara, p_ahmed, p_alex, p_omar]

    # Test Arabic vocative and spelling variants (Alef/Taa Marbuta)
    m1 = match_personality_in_message("إزيك يا سارة؟", personalities)
    assert m1 and m1.id == 2, f"Failed matching 'يا سارة': got {m1}"

    m2 = match_personality_in_message("كلمني يا ساره ضروري", personalities)
    assert m2 and m2.id == 2, f"Failed matching normalized 'يا ساره': got {m2}"

    m3 = match_personality_in_message("عايز أسأل احمد فتحي في حاجة", personalities)
    assert m3 and m3.id == 3, f"Failed matching 'احمد فتحي': got {m3}"

    m4 = match_personality_in_message("يا عمر ساعدني", personalities)
    assert m4 and m4.id == 5, f"Failed matching 'يا عمر': got {m4}"

    # Test English
    m5 = match_personality_in_message("Hey Alex, what is today's schedule?", personalities)
    assert m5 and m5.id == 4, f"Failed matching 'Alex': got {m5}"

    # Test no mention
    m6 = match_personality_in_message("الطقس عامل إيه النهاردة؟", personalities)
    assert m6 is None, f"Expected None for generic message, got {m6}"

    print("  -> Dynamic message routing passed successfully!")


def test_biometric_identity_matching():
    print("[3] Testing Biometric Identity Matching (Face ID / Voice Speaker)...", flush=True)
    p_sara = Personality(id=2, name="سارة", is_active=False)
    p_omar = Personality(id=5, name="عمر علي", is_active=False)
    personalities = [p_sara, p_omar]

    # Face ID camera matches personality
    m_face = match_personality_by_identity("سارة", personalities)
    assert m_face and m_face.id == 2, f"Failed face match: {m_face}"

    # Speaker ID from audio matches first name
    m_spk = match_personality_by_identity("عمر علي", personalities)
    assert m_spk and m_spk.id == 5, f"Failed speaker match: {m_spk}"

    m_none = match_personality_by_identity("شخص غريب", personalities)
    assert m_none is None, f"Expected None for unknown identity, got {m_none}"
    print("  -> Biometric matching passed successfully!")


async def test_dynamic_creator_resolution():
    print("[4] Testing Dynamic Creator Resolution (Zero Hardcoded Names)...", flush=True)
    db_mock = AsyncMock()

    # Case 1: Owner user linked via user_id
    p_with_user = Personality(id=10, name="روبوت تجريبي", user_id=42)
    fake_user = User(id=42, full_name="د. كريم محمود", email="karim@nebula.ai", hashed_password="x")
    db_mock.get.return_value = fake_user

    creator1 = await resolve_creator_name(p_with_user, [], db_mock, is_arabic=True)
    assert creator1 == "د. كريم محمود", f"Expected owner user 'د. كريم محمود', got '{creator1}'"

    # Case 2: Extracted from system_prompt via regex
    p_with_prompt = Personality(
        id=11,
        name="نيبولا",
        user_id=None,
        system_prompt="أنت مساعد رقمي ذكي صممه وطوره المهندس كمال إبراهيم ليساعد المستخدمين.",
    )
    creator2 = await resolve_creator_name(p_with_prompt, [], db_mock, is_arabic=True)
    assert creator2 == "كمال إبراهيم", f"Expected regex extracted 'كمال إبراهيم', got '{creator2}'"

    # Case 3: Digital Twin personality name
    p_twin = Personality(id=12, name="نوران (توأم رقمي)", user_id=None, system_prompt="")
    creator3 = await resolve_creator_name(p_twin, [], db_mock, is_arabic=True)
    assert creator3 == "نوران", f"Expected digital twin name 'نوران', got '{creator3}'"

    # Case 4: First registered face
    p_generic = Personality(id=13, name="توت (Default)", user_id=None, system_prompt="")
    creator4 = await resolve_creator_name(p_generic, ["زياد طارق"], db_mock, is_arabic=True)
    assert creator4 == "زياد طارق", f"Expected registered face 'زياد طارق', got '{creator4}'"

    # Case 5: Zero-record generic fallback
    creator5_ar = await resolve_creator_name(p_generic, [], db_mock, is_arabic=True)
    assert creator5_ar == "فريق التطوير والمهندسين", f"Expected generic Arabic team, got '{creator5_ar}'"

    creator5_en = await resolve_creator_name(p_generic, [], db_mock, is_arabic=False)
    assert creator5_en == "the engineering team", f"Expected generic English team, got '{creator5_en}'"

    print("  -> Dynamic creator resolution passed with ZERO hardcoded names!")


async def test_full_context_builder_flow():
    print("[5] Testing Full Context Builder Flow with Dynamic Hybrid Routing...", flush=True)
    db_mock = AsyncMock()

    p_default = Personality(id=1, name="توت (Default)", is_active=True, dialect="cairo", system_prompt="")
    p_sara = Personality(id=2, name="سارة", is_active=False, dialect="cairo", system_prompt="أنت سارة المهندسة.")

    all_personalities = [p_default, p_sara]

    def mock_db_execute(stmt):
        mock_result = MagicMock()
        stmt_str = str(stmt).lower()
        if "personalities" in stmt_str:
            mock_result.scalars.return_value.all.return_value = all_personalities
            mock_result.scalar_one_or_none.return_value = p_default
        else:
            mock_result.scalars.return_value.all.return_value = []
            mock_result.scalar_one_or_none.return_value = None
        return mock_result

    db_mock.execute = AsyncMock(side_effect=mock_db_execute)

    mock_face_svc = MagicMock()
    mock_face_svc.get_current_face_info.return_value = {"detected": False, "face_id": None}
    mock_face_svc._known_embeddings = {}

    with patch("app.services.ai.context_builder._rag_service.retrieve", new_callable=AsyncMock) as mock_rag, \
         patch("app.services.memory.person_retriever.PersonImageRetriever.get_all_registered_names", new_callable=AsyncMock) as mock_names, \
         patch("app.services.vision.face_service.get_face_service", return_value=mock_face_svc):
        mock_rag.return_value = []
        mock_names.return_value = []

        # Scenario A: User mentions "سارة" in message -> should route to Sara (ID: 2)
        prompt_a, _, grounding_a, pid_a = await build_grounding_context(
            db=db_mock,
            personality_id=None,
            message="يا سارة ممكن تساعديني؟",
            verified_speaker=None,
        )
        assert pid_a == 2, f"Expected routed to personality 2 (Sara), got {pid_a}"
        assert "سارة" in prompt_a, f"Expected Sara in system prompt: {prompt_a[:150]}"

        # Scenario B: User does NOT mention any name, but camera detects "سارة"
        prompt_b, _, grounding_b, pid_b = await build_grounding_context(
            db=db_mock,
            personality_id=None,
            message="الجو عامل إيه؟",
            verified_speaker="سارة",
        )
        assert pid_b == 2, f"Expected biometric routing to 2 (Sara), got {pid_b}"

        # Scenario C: User asks generic question with no speaker -> routes to default active personality (ID: 1)
        prompt_c, _, grounding_c, pid_c = await build_grounding_context(
            db=db_mock,
            personality_id=None,
            message="الساعة كام دلوقتي؟",
            verified_speaker=None,
        )
        assert pid_c == 1, f"Expected active personality 1 (Default), got {pid_c}"

    print("  -> Full context builder flow passed successfully!", flush=True)


async def main():
    print("=" * 70)
    print("NEBULA AI - DYNAMIC MULTI-PERSONALITY & ZERO-HARDCODING TEST SUITE")
    print("=" * 70)
    test_token_extraction()
    test_message_personality_matching()
    test_biometric_identity_matching()
    await test_dynamic_creator_resolution()
    await test_full_context_builder_flow()
    print("=" * 70)
    print("ALL TESTS PASSED 100%! ZERO FALLBACK MODEL, FULLY DYNAMIC.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
