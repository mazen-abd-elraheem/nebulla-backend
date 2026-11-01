"""
Comprehensive Test Suite for Advanced Production-Grade RAG Pipeline.

Tests solutions for all RAG failure modes without Fallback Models:
1. Lexical BM25 Search with Arabic/Egyptian Normalization
2. Cross-Encoder & Deep Alignment Re-ranking
3. Multi-Hop Query Decomposition
4. Hierarchical Parent-Child Chunking & Table Preservation
5. Deterministic Fact Verification & Anti-Hallucination Guard (Zero Fallback Model)
6. Context Reordering (Lost in the Middle Mitigation)
7. End-to-End RAG Retrieval with Citation Grounding
"""

import pytest
import pytest_asyncio
from typing import List

from app.services.memory.bm25 import BM25Okapi, ArabicBM25Tokenizer
from app.services.memory.reranker import CrossReranker
from app.services.memory.query_decomposer import QueryDecomposer
from app.services.memory.chunker import HierarchicalChunker
from app.services.memory.fact_verifier import FactVerifier
from app.services.memory.rag_service import RAGService
from app.models.memory import Memory


# ── 1. BM25 & Lexical Normalization Tests ────────────────────────────────────

def test_bm25_arabic_tokenizer():
    tokens = ArabicBM25Tokenizer.tokenize("نيبيولا بيحب البرمجة بالبايثون مع المهندسين")
    assert "نيبولا" in tokens
    assert "برمجه" in tokens or "البرمجه" in tokens
    # Prefix stemming should extract 'بايثون' from 'بالبايثون'
    assert "بايثون" in tokens
    # Stopwords should be stripped
    assert "مع" not in tokens


def test_bm25_exact_keyword_and_code_matching():
    corpus = [
        "المهندس مازن يعمل في قسم تطوير الذكاء الاصطناعي برقم الموظف EMP-9921",
        "المهندسة منه تعمل في قسم اختبار الروبوتات وتصميم الدوائر",
        "نيبولا هو روبوت توأم رقمي ذكي مزود بمحركات ومستشعرات صوتية",
    ]
    bm25 = BM25Okapi(corpus)

    # Search by exact code
    scores = bm25.get_scores("EMP-9921")
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]

    # Search with Egyptian verb prefix
    scores_mazen = bm25.get_scores("مازن")
    assert scores_mazen[0] > scores_mazen[1]


# ── 2. Cross-Reranker Tests ──────────────────────────────────────────────────

def test_cross_reranker_phrase_and_proximity():
    candidates = [
        (0.5, 1, "مازن ذهب إلى المتجر واشترى لابتوب جديد ثم تحدث عن بايثون"),
        (0.6, 2, "مازن يفضل لغة بايثون في مشاريعه البرمجية"),
        (0.4, 3, "الطقس اليوم جميل في القاهرة وبايثون لغة برمجة"),
    ]
    # Query has 'مازن' and 'بايثون' close together
    reranked = CrossReranker.rerank("مازن لغة بايثون", candidates, top_k=3)
    # The second candidate has higher density and phrase proximity
    top_item_id = reranked[0][1]
    assert top_item_id == 2


# ── 3. Query Decomposition Tests ─────────────────────────────────────────────

def test_query_decomposition_arabic():
    query = "إيه مواصفات نيبولا؟ وكمان مين اللي صممه؟"
    subs = QueryDecomposer.decompose(query)
    assert len(subs) >= 2
    assert any("مواصفات نيبولا" in s for s in subs)
    assert any("مين اللي صممه" in s for s in subs)


def test_query_decomposition_english():
    query = "What is the CPU specs and also who built the robot?"
    subs = QueryDecomposer.decompose(query)
    assert len(subs) >= 2
    assert any("cpu specs" in s.lower() for s in subs)


# ── 4. Hierarchical Parent-Child & Table Chunker Tests ───────────────────────

def test_chunker_parent_child_and_table_preservation():
    chunker = HierarchicalChunker(parent_chunk_size=300, child_chunk_size=100)
    doc = """
    مقدمة عن الروبوت نيبولا وتاريخ نشأته في مصر.

    | المكون | العدد | الملاحظات |
    | محرك سيرفو | 6 | دقيق جداً |
    | كاميرا | 1 | التعرف على الوجوه |
    | ميكروفون | 2 | تقنية VAD |

    خاتمة التقرير وتفاصيل تشغيل النظام.
    """
    parents, children = chunker.chunk_document("doc_001", doc)

    assert len(parents) > 0
    assert len(children) > 0

    # Ensure table rows remained together in one chunk
    table_parents = [p for p in parents if "| محرك سيرفو |" in p.content]
    assert len(table_parents) == 1
    assert "| كاميرا |" in table_parents[0].content
    assert "| ميكروفون |" in table_parents[0].content


# ── 5. Fact Verifier & Anti-Hallucination Tests (Zero Fallback) ───────────────

def test_fact_verifier_refusal_when_context_empty():
    query = "ما هو رقم هاتف مازن؟"
    model_response = "رقم هاتف مازن هو 01012345678"
    verified = FactVerifier.verify_and_sanitize(query, model_response, retrieved_memories=[])

    # Must refuse strictly!
    assert "مش مسجلة" in verified or "غير مسجلة" in verified
    assert "01012345678" not in verified


def test_fact_verifier_sanitizes_fabricated_sensitive_numbers():
    query = "اديني الباسورد السري لخزنة نيبولا"
    model_response = "كلمة السر هي 998877"
    context = ["نيبولا روبوت تم تصميمه بواسطة فريق المهندسين."]

    verified = FactVerifier.verify_and_sanitize(query, model_response, retrieved_memories=context)
    assert "998877" not in verified
    assert "مش مسجلة" in verified


def test_fact_verifier_allows_grounded_responses():
    query = "مازن بيحب يشرب إيه؟"
    model_response = "مازن بيفضل يشرب شاي بنعناع في الصباح. [happy]"
    context = ["مازن يفضل شرب شاي بالنعناع في الصباح الباكر."]

    verified = FactVerifier.verify_and_sanitize(query, model_response, retrieved_memories=context)
    assert "شاي" in verified
    assert "بنعناع" in verified or "نعناع" in verified


# ── 6. Context Reordering (Lost in the Middle Solution) ──────────────────────

def test_context_reordering():
    rag = RAGService()
    items = ["Doc 1 (Top)", "Doc 2 (Second)", "Doc 3 (Third)", "Doc 4 (Fourth)", "Doc 5 (Fifth)"]
    reordered = rag._reorder_context(items)

    # Edge-centric ordering places Doc 1 at start, Doc 2 at end
    assert reordered[0] == "Doc 1 (Top)"
    assert reordered[-1] == "Doc 2 (Second)"


# ── 7. Citation Formatting in RAG Prompt ─────────────────────────────────────

def test_format_rag_prompt_citations():
    rag = RAGService()
    memories = [
        "مازن يفضل العمل بلغة بايثون في مشاريع الذكاء الاصطناعي.",
        "منه متخصصة في الدوائر الإلكترونية والأنظمة المدمجة.",
    ]
    prompt = rag.format_rag_prompt("مازن شغال في إيه؟", memories=memories)

    assert "[المصدر 1]" in prompt
    assert "[المصدر 2]" in prompt
    assert "المصادر المعتمدة" in prompt
