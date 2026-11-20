"""
Unit tests for Nebula Compass (بوصلة نيبولا) Question Bank, Engine, Memory Extractor,
and API Endpoints.
"""

try:
    import pytest
except ImportError:
    class _MockPytest:
        class mark:
            @staticmethod
            def asyncio(fn):
                return fn
    pytest = _MockPytest()
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.session import init_db
from app.services.onboarding.compass_question_bank import (
    QUESTION_BANK,
    CompassQuestion,
    get_all_questions,
    get_core_questions,
    get_balanced_questions,
    get_questions_by_dimension,
    get_question_by_id,
)
from app.services.onboarding.nebula_compass_engine import NebulaCompassEngine
from app.services.onboarding.memory_extractor import CompassMemoryExtractor


def test_question_bank_structure():
    """Verify exactly 50 total questions with 10 questions per each of the 5 dimensions."""
    all_qs = get_all_questions()
    assert len(all_qs) == 50
    assert len(QUESTION_BANK) == 50

    dimensions = ["work_tech", "routine", "social", "preferences", "mindset"]
    for dim in dimensions:
        dim_qs = get_questions_by_dimension(dim)
        assert len(dim_qs) == 10
        # Exactly 3 core questions per dimension
        core_dim = [q for q in dim_qs if q.is_core]
        assert len(core_dim) == 3

    assert len(get_core_questions()) == 15


def test_balanced_questions_selection():
    """Verify balanced mode picks 2 to 3 questions per dimension (10-15 total)."""
    # 2 questions per dimension -> 10 total
    balanced_2 = get_balanced_questions(per_dimension=2)
    assert len(balanced_2) == 10

    # 3 questions per dimension -> 15 total
    balanced_3 = get_balanced_questions(per_dimension=3)
    assert len(balanced_3) == 15

    # Verify all 5 dimensions are evenly represented
    dimensions = ["work_tech", "routine", "social", "preferences", "mindset"]
    for dim in dimensions:
        dim_in_b2 = [q for q in balanced_2 if q.dimension == dim]
        assert len(dim_in_b2) == 2

        dim_in_b3 = [q for q in balanced_3 if q.dimension == dim]
        assert len(dim_in_b3) == 3


def test_compass_engine_modes():
    """Verify engine returns correct counts and structure for balanced, quick, and full modes."""
    # Balanced mode (default)
    balanced_res = NebulaCompassEngine.get_questions(mode="balanced", per_dimension=2)
    assert len(balanced_res) == 10
    assert all("id" in q and "dimension" in q and "text" in q for q in balanced_res)

    # Quick mode (15 core questions)
    quick_res = NebulaCompassEngine.get_questions(mode="quick")
    assert len(quick_res) == 15
    assert all(q["is_core"] for q in quick_res)

    # Full mode (50 questions)
    full_res = NebulaCompassEngine.get_questions(mode="full")
    assert len(full_res) == 50


def test_answer_weights_parsing():
    """Verify 5-point scale parsing for Arabic and English answers."""
    assert NebulaCompassEngine.parse_answer_weight("نعم") == 1.0
    assert NebulaCompassEngine.parse_answer_weight("yes") == 1.0
    assert NebulaCompassEngine.parse_answer_weight("في الغالب نعم") == 0.75
    assert NebulaCompassEngine.parse_answer_weight("لا أعلم / محايد") == 0.0
    assert NebulaCompassEngine.parse_answer_weight("في الغالب لا") == -0.75
    assert NebulaCompassEngine.parse_answer_weight("لا") == -1.0
    assert NebulaCompassEngine.parse_answer_weight("unknown") == 0.0


def test_archetype_determination():
    """Verify archetype deduction reflects dimension polarity."""
    scores = {
        "work_tech": 2.5,
        "routine": 2.0,
        "social": 1.5,
        "preferences": 0.5,
        "mindset": 2.0,
    }
    archetype = NebulaCompassEngine.determine_archetype(scores)
    assert "مطور شغوف بالتكنولوجيا" in archetype
    assert "إنتاجي ليلي" in archetype
    assert "مباشر ويفضل النبرة المصرية" in archetype


def test_memory_extraction_rules():
    """Verify extraction produces affirmative/negative facts and dimension scores."""
    answers = {
        "q1_software_builder": "نعم",
        "q3_data_driven": "في الغالب نعم",
        "q11_night_owl": "لا",
    }
    facts, scores = CompassMemoryExtractor.extract_via_rules(answers)
    assert any("البرمجيات" in f for f in facts)
    assert any("البيانات" in f or "الأرقام" in f or "المنطقية" in f for f in facts)
    assert scores["work_tech"] > 1.5
    assert scores["routine"] < -0.5


@pytest.mark.asyncio
async def test_compass_api_endpoints():
    """Integration test for /api/v1/auth/compass/questions and /answers."""
    await init_db()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Test GET /compass/questions in balanced mode
        resp_q = await client.get("/api/v1/auth/compass/questions?mode=balanced&per_dimension=2")
        assert resp_q.status_code == 200
        data_q = resp_q.json()
        assert data_q["mode"] == "balanced"
        assert data_q["total_questions"] == 10
        assert len(data_q["questions"]) == 10
        assert "بوصلة نيبولا" in data_q["title"]

        # 2. Test POST /compass/answers
        ans_payload = {
            "answers": {
                "q1_software_builder": "نعم",
                "q21_direct_talker": "نعم",
                "q50_founder_ambition": "نعم",
            },
            "mode": "balanced",
        }
        resp_a = await client.post("/api/v1/auth/compass/answers", json=ans_payload)
        assert resp_a.status_code == 200
        data_a = resp_a.json()
        assert "archetype" in data_a
        assert data_a["memories_created"] >= 3
        assert any("البرمجيات" in m for m in data_a["memories"])

        # 3. Test Backward compatibility alias /onboarding/questions
        resp_alias = await client.get("/api/v1/auth/onboarding/questions")
        assert resp_alias.status_code == 200
        data_alias = resp_alias.json()
        assert len(data_alias["questions"]) == 10

        # 4. Test Backward compatibility alias /onboarding/answers
        resp_ans_alias = await client.post("/api/v1/auth/onboarding/answers", json=ans_payload)
        assert resp_ans_alias.status_code == 200
        data_ans_alias = resp_ans_alias.json()
        assert data_ans_alias["success"] is True
        assert data_ans_alias["saved_memories_count"] >= 3
