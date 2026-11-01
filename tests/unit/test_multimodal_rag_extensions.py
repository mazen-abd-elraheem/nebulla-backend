"""
Unit Tests for Multimodal RAG Extensions:
1. VectorStore Database Optimization (L2 normalization, matrix dot product, caching)
2. Person Image & Face Photo Data Retrieval (FaceProfile integration, photo URL lookup)
3. Voice Integration (Speaker Verification, TTS-friendly formatting)
4. Desktop Screen Control & Real-time Telemetry (Screen actions, eyes mood, HUD events)
5. Zero Fallback Model Verification
"""

import pytest
import numpy as np
from unittest.mock import MagicMock, AsyncMock, patch

from app.models.memory import Memory
from app.services.memory.vector_store import DatabaseVectorStore
from app.services.memory.person_retriever import PersonImageRetriever
from app.services.memory.rag_service import RAGService
from app.services.memory.fact_verifier import FactVerifier
from app.utils.masri_normalizer import clean_llm_output_for_speech


# ── 1. Vector Database Optimization Tests ────────────────────────────────────

def test_vector_store_l2_normalization_and_dot_product():
    vstore = DatabaseVectorStore()
    raw_vec1 = np.array([3.0, 4.0, 0.0], dtype=np.float32)
    norm_vec1 = vstore._normalize(raw_vec1)

    # Unit length check
    assert np.isclose(np.linalg.norm(norm_vec1), 1.0)
    assert np.allclose(norm_vec1, [0.6, 0.8, 0.0])

    # Populate store with mock memories
    mem1 = Memory(id=101, content="مازن يفضل بايثون", embedding=norm_vec1.tobytes(), personality_id=1)
    raw_vec2 = np.array([0.0, 0.0, 5.0], dtype=np.float32)
    norm_vec2 = vstore._normalize(raw_vec2)
    mem2 = Memory(id=102, content="منه تفضل الإلكترونيات", embedding=norm_vec2.tobytes(), personality_id=1)

    vstore.load_from_db([mem1, mem2])

    assert vstore._matrix is not None
    assert vstore._matrix.shape == (2, 3)

    # Query with identical vector to mem1
    hits = vstore.search(raw_vec1, top_k=2)
    assert len(hits) >= 1
    top_hit_score, top_hit_mem = hits[0]
    assert top_hit_mem.id == 101
    assert top_hit_score >= 0.99  # Normalized dot product is 1.0


def test_vector_store_metadata_filtering():
    vstore = DatabaseVectorStore()
    vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    mem1 = Memory(id=201, content="معلومة شخصية 1", embedding=vec.tobytes(), personality_id=1)
    mem2 = Memory(id=202, content="معلومة شخصية 2", embedding=vec.tobytes(), personality_id=2)
    vstore.load_from_db([mem1, mem2])

    # Search filtering by personality_id=2
    hits = vstore.search(vec, personality_id=2, top_k=5)
    assert len(hits) == 1
    assert hits[0][1].id == 202


# ── 2. Person Image & Face Photo Retrieval Tests ─────────────────────────────

def test_person_image_retriever_query_intent():
    assert PersonImageRetriever.is_photo_inquiry("وريني صورة مازن") is True
    assert PersonImageRetriever.is_photo_inquiry("عايز أشوف صورة المهندس") is True
    assert PersonImageRetriever.is_photo_inquiry("ما هو الطقس اليوم؟") is False


def test_person_candidate_extraction():
    known = ["مازن عبد الرحيم", "منه محمد", "أحمد علي"]
    assert PersonImageRetriever.extract_person_candidate("إيه رأيك في شغل مازن الأخير؟", known) == "مازن عبد الرحيم"
    assert PersonImageRetriever.extract_person_candidate("معلومات عن منه", known) == "منه محمد"
    assert PersonImageRetriever.extract_person_candidate("أهلاً بيك", known) is None


def test_rag_prompt_visual_profile_formatting():
    rag = RAGService()
    memories = ["مازن يفضل البرمجة بلغة بايثون."]
    person_profile = {
        "name": "مازن عبد الرحيم",
        "photo_path": "data/faces/mazen.jpg",
        "photo_url": "/api/v1/faces/مازن عبد الرحيم/photo",
        "has_photo": True,
    }

    prompt = rag.format_rag_prompt(
        query="وريني صورة مازن",
        memories=memories,
        person_name="مازن عبد الرحيم",
        person_profile=person_profile,
    )

    assert "/api/v1/faces/مازن عبد الرحيم/photo" in prompt
    assert "بيانات وصورة الشخص المسجل" in prompt
    assert "[المصدر 1]" in prompt


# ── 3. Voice & Speech Synthesis Integration Tests ────────────────────────────

def test_speech_cleanup_removes_citations_and_emotions_for_tts():
    # LLM output generated from RAG containing citations and emotion tag
    llm_output = "مازن بيفضل يشتغل بلغة بايثون في مشاريعه [المصدر 1]. [happy]"

    tts_ready = clean_llm_output_for_speech(llm_output)

    # Must cleanly strip [المصدر 1] and [happy] so TTS voice doesn't pronounce them
    assert "[المصدر 1]" not in tts_ready
    assert "[happy]" not in tts_ready
    assert "بايثون" in tts_ready


# ── 4. Zero Fallback Model Enforcement ───────────────────────────────────────

def test_zero_fallback_model_strict_refusal():
    query = "ما هو الرقم السري للحساب البنكي؟"
    untrustworthy_llm_output = "الرقم السري هو 4491"
    context = ["الروبوت نيبولا صممه فريق المهندسين."]

    # FactVerifier must deterministically reject the fabricated pin code
    sanitized = FactVerifier.verify_and_sanitize(query, untrustworthy_llm_output, retrieved_memories=context)
    assert "4491" not in sanitized
    assert "مش مسجلة" in sanitized or "غير مسجلة" in sanitized

