"""
Unit Tests for Akinator-Style Onboarding Questionnaire & Memory Ingestion.
"""

try:
    import pytest
except ImportError:
    class _MockMark:
        @staticmethod
        def asyncio(f):
            return f
    class _MockPytest:
        mark = _MockMark()
    pytest = _MockPytest()

from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.onboarding.question_bank import (
    get_all_questions,
    get_core_questions,
    get_questions_by_dimension,
    QUESTION_BANK,
)
from app.services.onboarding.akinator_engine import AkinatorEngine
from app.services.onboarding.memory_extractor import MemoryExtractor


def test_question_bank_structure():
    """Verify the question bank holds exactly 50 questions with 15 core questions across 5 dimensions."""
    all_q = get_all_questions()
    core_q = get_core_questions()

    assert len(all_q) == 50, f"Expected 50 questions, got {len(all_q)}"
    assert len(core_q) == 15, f"Expected 15 core questions, got {len(core_q)}"

    dimensions = {"work_tech", "routine", "social", "preferences", "mindset"}
    for dim in dimensions:
        dim_qs = get_questions_by_dimension(dim)
        assert len(dim_qs) == 10, f"Dimension {dim} should have exactly 10 questions, got {len(dim_qs)}"
        dim_core = [q for q in dim_qs if q.is_core]
        assert len(dim_core) == 3, f"Dimension {dim} should have exactly 3 core questions, got {len(dim_core)}"

    for q in all_q:
        assert q.id, "Question must have an ID"
        assert len(q.options) == 5, f"Question {q.id} must have 5 options"
        assert q.affirmative_fact, f"Question {q.id} must have an affirmative fact"


def test_akinator_engine_filtering():
    """Verify AkinatorEngine question retrieval modes."""
    full_list = AkinatorEngine.get_questions(mode="full")
    assert len(full_list) == 50

    quick_list = AkinatorEngine.get_questions(mode="quick")
    assert len(quick_list) == 15

    dim_list = AkinatorEngine.get_questions(dimension="social")
    assert len(dim_list) == 10


def test_rule_based_memory_extraction():
    """Verify deterministic rule extraction from user answers."""
    sample_answers = {
        "q1_software_builder": "نعم",
        "q4_ai_enthusiast": "في الغالب نعم",
        "q11_night_owl": "نعم",
        "q12_coffee_lover": "نعم",
        "q21_concise_replies": "نعم",
        "q37_physical_robot_companion": "نعم",
    }

    facts, dim_scores = MemoryExtractor.extract_via_rules(sample_answers)

    assert len(facts) == 6
    assert any("برمجيات" in f for f in facts)
    assert any("كائن ليلي" in f for f in facts)
    assert any("قهوة" in f or "القهوة" in f for f in facts)
    assert any("المباشرة" in f for f in facts)
    assert any("نيبولا الفيزيائي" in f for f in facts)

    assert dim_scores["work_tech"] > 1.5
    assert dim_scores["routine"] > 1.5

    archetype = AkinatorEngine.determine_archetype(dim_scores)
    assert "مطور" in archetype or "ليلي" in archetype


@pytest.mark.asyncio
async def test_hybrid_memory_extractor():
    """Verify hybrid extraction combines rule facts and archetype."""
    sample_answers = {
        "q1_software_builder": "نعم",
        "q3_data_driven": "نعم",
        "q11_night_owl": "نعم",
        "q15_hyperfocus": "نعم",
        "q22_humorous_tone": "نعم",
    }

    res = await MemoryExtractor.hybrid_extract(
        answers=sample_answers,
        user_name="مازن",
        use_llm=False,  # Test deterministic mode
    )

    assert res["user_name"] == "مازن"
    assert len(res["memories"]) >= 5
    assert any("بروفايل مازن" in m for m in res["memories"])


@pytest.mark.asyncio
async def test_akinator_api_endpoints():
    """Verify GET questions and POST submit endpoints via HTTP client."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # 1. Test GET questions (quick mode)
        resp_quick = await ac.get("/api/v1/auth/onboarding/akinator/questions?mode=quick")
        assert resp_quick.status_code == 200
        data_quick = resp_quick.json()
        assert data_quick["total"] == 15
        assert len(data_quick["questions"]) == 15

        # 2. Test GET questions (full mode)
        resp_full = await ac.get("/api/v1/auth/onboarding/akinator/questions?mode=full")
        assert resp_full.status_code == 200
        data_full = resp_full.json()
        assert data_full["total"] == 50
        assert len(data_full["questions"]) == 50

        # 3. Test POST submit answers
        submit_payload = {
            "answers": {
                "q1_software_builder": "نعم",
                "q3_data_driven": "في الغالب نعم",
                "q11_night_owl": "نعم",
                "q12_coffee_lover": "نعم",
                "q21_concise_replies": "نعم",
                "q37_physical_robot_companion": "نعم",
                "q43_prototype_fast": "نعم"
            },
            "auto_create_personality": True,
            "use_llm": False
        }

        resp_submit = await ac.post("/api/v1/auth/onboarding/akinator/submit", json=submit_payload)
        assert resp_submit.status_code == 200
        result = resp_submit.json()
        assert result["success"] is True
        assert result["personality_id"] > 0
        assert result["memories_count"] >= 7
        assert len(result["memories_saved"]) >= 7
        assert "archetype" in result
