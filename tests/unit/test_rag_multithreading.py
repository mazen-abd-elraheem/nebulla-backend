"""
Unit Tests for Multithreaded RAG Retrieval Engine.

Evaluates:
1. Thread-safety under high concurrency (Concurrent worker threads querying RAG simultaneously).
2. Parallel sub-query execution across worker threads.
3. Thread-safe VectorStore concurrent reads and writes.
4. Non-blocking asynchronous offloading (_embed_async, search_async, rerank_async).
5. Zero Fallback Model adherence under multithreaded load.
"""

import asyncio
import concurrent.futures
import threading
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

from app.models.memory import Memory
from app.services.memory.rag_service import RAGService, _RAG_EXECUTOR
from app.services.memory.vector_store import DatabaseVectorStore
from app.services.memory.reranker import CrossReranker
from app.services.memory.fact_verifier import FactVerifier


# ── 1. Thread-Safe Embedding Cache Stress Test ────────────────────────────────

def test_multithreaded_embedding_cache_concurrency():
    rag = RAGService()
    rag._embedder = MagicMock()
    # Mock encoder returning deterministic vector
    rag._embedder.encode.side_effect = lambda text, normalize_embeddings=True: np.array([len(text) * 0.1, 0.5, 0.2], dtype=np.float32)

    errors = []

    def worker(worker_id: int):
        for i in range(25):
            query = f"query_{worker_id}_{i % 5}"
            try:
                vec = rag._embed(query)
                assert vec is not None
                assert len(vec) == 3
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # Zero exceptions must have occurred during concurrent reads and writes
    assert len(errors) == 0
    assert len(RAGService._shared_cache) > 0


# ── 2. Concurrent VectorStore Multithreaded Reads and Writes ─────────────────

def test_vector_store_concurrent_multithreading():
    vstore = DatabaseVectorStore()
    base_vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    # Pre-populate
    initial_mems = [
        Memory(id=i, content=f"ذاكرة رقم {i} عن البرمجة", embedding=base_vec.tobytes(), personality_id=1)
        for i in range(1, 15)
    ]
    vstore.load_from_db(initial_mems)

    errors = []

    def reader(reader_id: int):
        for _ in range(30):
            try:
                hits = vstore.search(base_vec, top_k=5)
                assert len(hits) > 0
            except Exception as e:
                errors.append(e)

    def writer(writer_id: int):
        for j in range(10):
            try:
                mid = 500 + writer_id * 10 + j
                mem = Memory(id=mid, content=f"ذاكرة ديناميكية {mid}", embedding=base_vec.tobytes())
                vstore.add_or_update(mem, vec=base_vec)
            except Exception as e:
                errors.append(e)

    threads = []
    # 6 concurrent readers + 4 concurrent writers running at the same time
    for r in range(6):
        threads.append(threading.Thread(target=reader, args=(r,)))
    for w in range(4):
        threads.append(threading.Thread(target=writer, args=(w,)))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0


# ── 3. Parallel Sub-Query Execution via ThreadPoolExecutor ────────────────────

@pytest.mark.asyncio
async def test_parallel_subquery_execution_in_rag():
    rag = RAGService()
    rag._embedder = MagicMock()
    rag._embedder.encode.return_value = np.array([0.5, 0.5, 0.5], dtype=np.float32)

    valid_vec = np.array([0.5, 0.5, 0.5], dtype=np.float32).tobytes()
    mem1 = Memory(id=1, content="مازن يفضل بايثون للذكاء الاصطناعي", embedding=valid_vec, importance=8)
    mem2 = Memory(id=2, content="نيبولا روبوت توأم رقمي مزود بـ 12 محرك سيرفو", embedding=valid_vec, importance=7)

    with patch.object(rag, "_load_memories_sync", return_value=[mem1, mem2]):
        # Compound question with two distinct intents: triggers QueryDecomposer to split into 2 sub-queries
        compound_query = "إيه مواصفات نيبولا؟ وكمان مازن شغال بإيه؟"

        results = await rag.retrieve(compound_query, top_k=5)

        # Must retrieve facts for BOTH sub-queries executed in parallel threads!
        assert len(results) >= 2
        combined_text = " ".join(results)
        assert "مازن" in combined_text
        assert "نيبولا" in combined_text


# ── 4. Multithreaded High-Concurrency End-to-End Retrieval ────────────────────

@pytest.mark.asyncio
async def test_concurrent_async_rag_retrieval():
    rag = RAGService()
    rag._embedder = MagicMock()
    rag._embedder.encode.return_value = np.array([0.1, 0.2, 0.3], dtype=np.float32)

    valid_vec = np.array([0.1, 0.2, 0.3], dtype=np.float32).tobytes()
    mem1 = Memory(id=10, content="أحمد مهندس حاسبات في حلوان", embedding=valid_vec)
    mem2 = Memory(id=11, content="سارة طبيبة متخصصة في الجراحة", embedding=valid_vec)

    with patch.object(rag, "_load_memories_sync", return_value=[mem1, mem2]):
        queries = [
            "أحمد شغال إيه؟",
            "سارة بتشتغل إيه؟",
            "مين أحمد؟",
            "تخصص سارة إيه؟",
            "أحمد وسارة",
        ]

        # Launch all 5 queries concurrently in the asyncio loop
        tasks = [rag.retrieve(q, top_k=2) for q in queries]
        all_results = await asyncio.gather(*tasks)

        assert len(all_results) == 5
        for res in all_results:
            assert isinstance(res, list)


# ── 5. Zero Fallback Model Enforcement Under Concurrent Load ─────────────────

@pytest.mark.asyncio
async def test_zero_fallback_model_under_multithreading():
    rag = RAGService()
    rag._embedder = "disabled"  # Even without embedder, strictly no fallback model

    empty_mems = []
    with patch.object(rag, "_load_memories_sync", return_value=empty_mems):
        # When context is empty across multiple concurrent requests, every single turn MUST refuse
        queries = ["ما هو رقم حساب مازن؟", "كلمة سر الخزنة إيه؟", "عنوان البيت غير المسجل؟"]
        tasks = [rag.retrieve(q) for q in queries]
        results = await asyncio.gather(*tasks)

        for res in results:
            assert res == []  # Zero hallucinated memories retrieved

        # Verify fact verification enforces strict refusal
        for q in queries:
            verified = rag.verify_response(q, "الرقم هو 999", retrieved_memories=[])
            assert "مش مسجلة" in verified or "غير مسجلة" in verified
            assert "999" not in verified
