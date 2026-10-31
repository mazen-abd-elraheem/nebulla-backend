"""
RAG Memory Service — High-Performance Multithreaded Hybrid Retrieval.

Multithreading Architecture & Concurrency:
- Dedicated ThreadPoolExecutor (_RAG_EXECUTOR) for non-blocking CPU-bound vector & NLP tasks.
- Parallel Sub-Query Execution: Multiple sub-queries execute concurrently across worker threads.
- Parallel Dense + Sparse Hybrid Search (VectorStore Matrix Multiply + Okapi BM25).
- Thread-safe RLock-guarded embedding cache (_shared_cache) and in-memory VectorStore.
- Asynchronous Non-blocking Cross-Reranking and access-time database updates.
- Strictly Deterministic: ZERO Fallback Model.
"""

import asyncio
import concurrent.futures
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple, Dict, Any

try:
    import numpy as np  # type: ignore[import]
except ImportError:
    np = None
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import AsyncSessionLocal
from app.models.memory import Memory
from app.services.memory.bm25 import BM25Okapi, ArabicBM25Tokenizer
from app.services.memory.reranker import CrossReranker
from app.services.memory.query_decomposer import QueryDecomposer
from app.services.memory.fact_verifier import FactVerifier
from app.services.memory.vector_store import DatabaseVectorStore
from app.services.memory.person_retriever import PersonImageRetriever

logger = get_logger(__name__)

# Dedicated high-throughput thread pool for RAG operations
_RAG_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=min(32, (os.cpu_count() or 4) + 4),
    thread_name_prefix="rag-worker"
)


class RAGService:
    """
    Multithreaded Production-Grade RAG Memory Service.
    Combines In-Memory Vector Matrix Store + Okapi BM25 + Parallel Sub-Queries + Cross-Reranker.
    """

    _shared_embedder = None
    _init_lock = threading.RLock()
    _cache_lock = threading.RLock()
    _shared_cache: dict = {}

    def __init__(self):
        self._embedder = RAGService._shared_embedder
        self._vstore = DatabaseVectorStore.get_instance()

    async def _ensure_embedder(self):
        if self._embedder is not None:
            return
        if RAGService._shared_embedder is not None:
            self._embedder = RAGService._shared_embedder
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_RAG_EXECUTOR, self._load_embedder)
        self._embedder = RAGService._shared_embedder

    def _load_embedder(self):
        with RAGService._init_lock:
            if RAGService._shared_embedder is not None:
                self._embedder = RAGService._shared_embedder
                return
            if np is None:
                logger.warning("numpy is not installed. RAG will use pure BM25 search.")
                RAGService._shared_embedder = "disabled"
                self._embedder = "disabled"
                return
            try:
                from sentence_transformers import SentenceTransformer  # type: ignore[import]
                try:
                    embedder = SentenceTransformer(
                        settings.EMBEDDING_MODEL,
                        device=settings.EMBEDDING_DEVICE,
                        local_files_only=True,
                    )
                    logger.info(f"Embedding model loaded from local cache: {settings.EMBEDDING_MODEL}")
                    RAGService._shared_embedder = embedder
                    self._embedder = embedder
                    return
                except Exception:
                    pass

                logger.info("Embedding weights not in local cache; RAG utilizing accelerated Okapi BM25 engine.")
                RAGService._shared_embedder = "disabled"
                self._embedder = "disabled"
            except Exception as e:
                logger.warning(f"SentenceTransformer notice: ({e}). Utilizing accelerated BM25 engine.")
                RAGService._shared_embedder = "disabled"
                self._embedder = "disabled"

    def _load_memories_sync(self, personality_id: int | None = None) -> list[Memory]:
        """Load memories synchronously via sqlite3 for instant execution when session is None."""
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)

        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        if personality_id is not None:
            cursor.execute(
                "SELECT id, content, personality_id, embedding, source, importance FROM memories WHERE personality_id = ? OR personality_id IS NULL",
                (personality_id,),
            )
            rows = cursor.fetchall()
            if not rows:
                cursor.execute("SELECT id, content, personality_id, embedding, source, importance FROM memories")
                rows = cursor.fetchall()
        else:
            cursor.execute("SELECT id, content, personality_id, embedding, source, importance FROM memories")
            rows = cursor.fetchall()
        conn.close()

        memories = []
        for r in rows:
            mem = Memory(
                id=r[0],
                content=r[1],
                personality_id=r[2],
                embedding=r[3],
                source=r[4],
                importance=r[5],
            )
            memories.append(mem)
        return memories

    # ── Core Multithreaded Retrieval Engine ───────────────────────────────────

    def _score_single_subquery_sync(
        self,
        sub_query: str,
        bm25: BM25Okapi,
        memories: list[Memory],
        id_by_index: list[int],
        mem_by_id: dict[int, Memory],
        clean_person: Optional[str],
        personality_id: Optional[int],
    ) -> dict[int, float]:
        """
        Worker function executed inside thread pool for each sub-query:
        1. Encodes sub-query embedding and runs fast matrix vector search.
        2. Computes Okapi BM25 lexical scores.
        3. Fuses scores using Reciprocal Rank Fusion (RRF).
        """
        augmented_sq = f"{clean_person} {sub_query}" if clean_person and clean_person not in sub_query else sub_query

        sem_scores: dict[int, float] = {}
        lex_scores: dict[int, float] = {}

        # 1. Vector Dense Search
        if self._embedder != "disabled":
            try:
                embed_text = augmented_sq if clean_person else sub_query
                query_vec = self._embed(embed_text)
                if query_vec is not None:
                    vec_hits = self._vstore.search(
                        query_vec=query_vec,
                        top_k=25,
                        personality_id=personality_id,
                        person_name=clean_person,
                        min_similarity=0.20,
                    )
                    for sim_val, mem_hit in vec_hits:
                        sem_scores[mem_hit.id] = sim_val
            except Exception as e:
                logger.debug(f"Sub-query vector search notice: {e}")

        # 2. Okapi BM25 Lexical Search
        bm25_scores = bm25.get_scores(augmented_sq)
        for idx, b_score in enumerate(bm25_scores):
            mid = id_by_index[idx]
            if b_score > 0.05:
                lex_scores[mid] = b_score

        # Boost person name if found in memory text
        if clean_person:
            p_lower = clean_person.lower()
            for m in memories:
                if p_lower in m.content.lower():
                    if m.id in lex_scores or m.id in sem_scores:
                        lex_scores[m.id] = lex_scores.get(m.id, 0.0) + 0.15

        # 3. Reciprocal Rank Fusion (RRF)
        sorted_sem = sorted(sem_scores.items(), key=lambda x: x[1], reverse=True)
        sem_ranks = {mid: rank for rank, (mid, _) in enumerate(sorted_sem, start=1)}

        sorted_lex = sorted(lex_scores.items(), key=lambda x: x[1], reverse=True)
        lex_ranks = {mid: rank for rank, (mid, _) in enumerate(sorted_lex, start=1)}

        sq_matched_ids = set(sem_scores.keys()).union(set(lex_scores.keys()))
        k_rrf = 60.0
        sq_candidates: dict[int, float] = {}

        for mid in sq_matched_ids:
            mem = mem_by_id.get(mid)
            if not mem:
                continue

            score_rrf = 0.0
            if mid in sem_ranks:
                score_rrf += 1.0 / (k_rrf + sem_ranks[mid])
            if mid in lex_ranks:
                score_rrf += 1.0 / (k_rrf + lex_ranks[mid])

            raw_sem = sem_scores.get(mid, 0.0)
            raw_lex = lex_scores.get(mid, 0.0)
            imp = getattr(mem, "importance", 5)
            imp_val = 5 if imp is None else imp
            importance_boost = (float(imp_val) / 10.0) * 0.03

            combined = (score_rrf * 10.0) + (raw_sem * 0.6) + (raw_lex * 0.5) + importance_boost
            sq_candidates[mid] = combined

        return sq_candidates

    async def _get_scored_memories(
        self,
        query: str,
        personality_id: int | None = None,
        db: AsyncSession | None = None,
        person_name: str | None = None,
    ) -> list[tuple[float, Memory]]:
        """
        Executes Advanced Multithreaded Hybrid Retrieval:
        1. Thread-safe VectorStore synchronization.
        2. Decomposes query into sub-queries.
        3. Spawns parallel worker threads for each sub-query (Concurrent RRF).
        4. Multithreaded Cross-Encoder / Deep Alignment Reranking.
        """
        await self._ensure_embedder()

        # Load memories from DB matching personality or shared
        if db is not None:
            stmt = select(Memory)
            if personality_id is not None:
                stmt_p = stmt.where((Memory.personality_id == personality_id) | (Memory.personality_id.is_(None)))
                res = await db.execute(stmt_p)
                memories = list(res.scalars().all())
                if not memories:
                    res_all = await db.execute(stmt)
                    memories = list(res_all.scalars().all())
            else:
                res = await db.execute(stmt)
                memories = list(res.scalars().all())
        else:
            memories = self._load_memories_sync(personality_id)

        if not memories:
            return []

        # Synchronize in-memory VectorStore
        incoming_ids = {m.id for m in memories}
        with self._vstore._lock:
            current_ids = set(self._vstore._memory_cache.keys())
        if not self._vstore._is_initialized or current_ids != incoming_ids:
            active_emb = self._embedder if self._embedder != "disabled" else None
            self._vstore.load_from_db(memories, embedder=active_emb)

        mem_by_id = {m.id: m for m in memories}
        doc_texts = [m.content for m in memories]
        id_by_index = [m.id for m in memories]

        # Initialize Okapi BM25 Index on corpus
        bm25 = BM25Okapi(doc_texts)

        # Decompose query into sub-queries
        sub_queries = QueryDecomposer.decompose(query)
        clean_person = person_name.strip() if person_name else None

        loop = asyncio.get_running_loop()

        # Multithreaded Parallel Execution of Sub-Queries across Worker Threads
        tasks = [
            loop.run_in_executor(
                _RAG_EXECUTOR,
                self._score_single_subquery_sync,
                sq,
                bm25,
                memories,
                id_by_index,
                mem_by_id,
                clean_person,
                personality_id,
            )
            for sq in sub_queries
        ]

        sub_results = await asyncio.gather(*tasks)

        # Merge candidate scores across parallel sub-query results
        accumulated_candidates: dict[int, float] = {}
        for sq_res in sub_results:
            for mid, score in sq_res.items():
                accumulated_candidates[mid] = max(accumulated_candidates.get(mid, 0.0), score)

        # Fallback BM25 pass if no candidates matched
        if not accumulated_candidates:
            fallback_bm25 = bm25.get_scores(query)
            for idx, sc in enumerate(fallback_bm25):
                if sc > 0.0:
                    accumulated_candidates[id_by_index[idx]] = sc

        if not accumulated_candidates:
            return []

        # Multithreaded Cross-Encoder / Alignment Re-ranking
        candidate_items = [
            (score, mem_by_id[mid], mem_by_id[mid].content)
            for mid, score in accumulated_candidates.items()
        ]

        reranked = await CrossReranker.rerank_async(
            query,
            candidate_items,
            top_k=min(20, len(candidate_items)),
            executor=_RAG_EXECUTOR,
        )

        final_scored = [(score, mem) for score, mem, _ in reranked]
        return final_scored

    def _normalize_for_dedup(self, text: str) -> str:
        """Normalized string for deduplicating repeated memory contents."""
        norm = self._normalize_arabic(text)
        norm = norm.replace("نيبيولا", "نيبولا").replace("nebula", "نيبولا")
        return re.sub(r"\s+", " ", norm).strip()

    @staticmethod
    def _reorder_context(items: List[Any]) -> List[Any]:
        """
        Solves the 'Lost in the Middle' problem.
        Reorders ranked items such that the most relevant items are placed
        at the very beginning and the very end of the prompt:
        Input: [1, 2, 3, 4, 5] -> Output: [1, 3, 5, 4, 2]
        """
        if len(items) <= 2:
            return items

        reordered = [None] * len(items)
        left = 0
        right = len(items) - 1

        for idx, item in enumerate(items):
            if idx % 2 == 0:
                reordered[left] = item
                left += 1
            else:
                reordered[right] = item
                right -= 1

        return [it for it in reordered if it is not None]

    # ── Public APIs ───────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        personality_id: int | None = None,
        top_k: int | None = None,
        db: AsyncSession | None = None,
        person_name: str | None = None,
    ) -> list[str]:
        """
        Return top-K relevant distinct memories for *query*.
        Uses Multithreaded Hybrid Search (BM25 + Dense) + Cross-Reranker + Context Reordering.
        """
        scored = await self._get_scored_memories(query, personality_id, db, person_name=person_name)
        if not scored:
            return []

        top_k = top_k or settings.MEMORY_TOP_K
        seen_contents: set[str] = set()
        unique_top: list[Memory] = []

        for score, mem in scored:
            norm_content = self._normalize_for_dedup(mem.content)
            if norm_content not in seen_contents:
                seen_contents.add(norm_content)
                unique_top.append(mem)
                if len(unique_top) >= top_k:
                    break

        if unique_top:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(_RAG_EXECUTOR, self._update_access_times_sync, [m.id for m in unique_top])

        # Apply Context Re-ordering to eliminate 'Lost in the Middle'
        reordered_mems = self._reorder_context(unique_top)
        return [m.content for m in reordered_mems]

    async def retrieve_detailed(
        self,
        query: str,
        personality_id: int | None = None,
        top_k: int | None = None,
        db: AsyncSession | None = None,
        person_name: str | None = None,
    ) -> list[dict]:
        """Return top-K relevant distinct memories with scores and provenance metadata."""
        scored = await self._get_scored_memories(query, personality_id, db, person_name=person_name)
        if not scored:
            return []

        top_k = top_k or settings.MEMORY_TOP_K
        seen_contents: set[str] = set()
        unique_scored: list[tuple[float, Memory]] = []

        for score, mem in scored:
            norm_content = self._normalize_for_dedup(mem.content)
            if norm_content not in seen_contents:
                seen_contents.add(norm_content)
                unique_scored.append((score, mem))
                if len(unique_scored) >= top_k:
                    break

        if unique_scored:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(_RAG_EXECUTOR, self._update_access_times_sync, [m.id for _, m in unique_scored])

        return [
            {
                "id": m.id,
                "content": m.content,
                "score": round(score, 4),
                "source": m.source,
                "personality_id": m.personality_id,
            }
            for score, m in unique_scored
        ]

    # ── Person & Visual Image Retrieval ──────────────────────────────────────

    async def retrieve_person_photo(
        self,
        person_name: str,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves visual profile, photo path, and photo URL for a registered person.
        """
        return await PersonImageRetriever.get_person_profile(person_name, db=db)

    async def retrieve_by_face(
        self,
        image_bytes: bytes,
        threshold: float = 0.40,
        db: Optional[AsyncSession] = None,
        top_k: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Visual Face-to-RAG Retrieval:
        1. Identifies people in the image via UniFace face recognition.
        2. Retrieves their registered photo profile.
        3. Retrieves all contextual memories linked to the recognized identities.
        """
        matches = await PersonImageRetriever.match_face_image(image_bytes, threshold=threshold)
        results = []

        for m in matches:
            p_name = m.get("match_name")
            memories = []
            if p_name and p_name != "unknown":
                memories = await self.retrieve(p_name, person_name=p_name, db=db, top_k=top_k)

            results.append({
                "face_id": p_name,
                "confidence": m.get("confidence", 0.0),
                "box": m.get("box"),
                "profile": m.get("profile"),
                "memories": memories,
            })

        return results

    # ── Prompt Generation & Fact Verification ─────────────────────────────────

    def format_rag_prompt(
        self,
        query: str,
        memories: list[str],
        instructions: str | None = None,
        person_name: str | None = None,
        person_profile: Optional[Dict[str, Any]] = None,
        robot_name: str = "نيبولا",
    ) -> str:
        """
        Builds a clean, citation-enforced, and voice-ready prompt:
        - Numbers each memory explicitly: [المصدر 1], [المصدر 2]
        - Integrates Person Visual Profile & Photo URL if available.
        - Directives guarantee TTS-safe speech (no markdown, clean dialect, emotion tag).
        """
        prompt_parts: list[str] = []

        # 1. System Persona & Core Instructions
        base_inst = instructions or f"أنت '{robot_name}'، توأم رقمي مصري ذكي وودود."
        prompt_parts.append(base_inst.strip())

        # 2. Operational Directives for Voice & Interaction
        prompt_parts.append(
            "\n[توجيهات التشغيل والرد الصوتي الصارم (Voice & Operational Directives)]:\n"
            "- أجب حصراً بلهجة مصرية قاهرية طبيعية ومهذبة ومباشرة (جملة أو جملتين كحد أقصى) لتناسب النطق الصوتي (TTS).\n"
            "- يُمنع استخدام أي جداول، علامات نجمية، أو روابط إنترنت في نص الإجابة المنطوقة، لضمان وضوح مخارج الصوت.\n"
            "- اعتمد بدقة وحصرياً على حقائق المصادر المسترجعة أدناه لتجنب أي هلوسة.\n"
            "- إذا كانت المعلومة غير موجودة في المصادر أو طُلب رقم هاتف أو كلمة سر، اذكر بأدب أن المعلومة غير مسجلة حالياً.\n"
            "- اختم ردك دائماً وبشكل إلزامي بوسم مشاعر مناسب في النهاية مثل: [happy] أو [wave] أو [like]."
        )

        # 3. Personalized Context & Face Recognition
        if person_name and person_name.strip():
            prompt_parts.append(
                f"\n[بيانات الشخص الحاضر / التعرف على الوجه]:\n"
                f"الشخص الذي تتحدث معه الآن هو: {person_name.strip()}."
            )

        # 4. Registered Person Visual Profile & Photo (Screen Awareness)
        if person_profile and person_profile.get("photo_url"):
            prompt_parts.append(
                f"\n[بيانات وصورة الشخص المسجل (Visual Profile)]:\n"
                f"- الاسم: {person_profile.get('name')}\n"
                f"- مسار ملف الصورة: {person_profile.get('photo_path')}\n"
                f"- رابط عرض الصورة على الشاشة: {person_profile.get('photo_url')}\n"
                f"- توجيه: إذا سأل المستخدم عن صورة الشخص أو شكله، أكد له أن صورته مسجلة وظاهرة أمامه على الشاشة."
            )

        # 5. Citation-Enforced Verified RAG Context
        if memories:
            formatted_sources = []
            for idx, m in enumerate(memories, 1):
                formatted_sources.append(f"[المصدر {idx}]: {m.strip()}")
            sources_text = "\n".join(formatted_sources)

            prompt_parts.append(
                f"\n--- [المصادر المعتمدة (Verified Grounding Sources)] ---\n"
                f"{sources_text}\n"
                f"----------------------------------------------------"
            )
        else:
            prompt_parts.append(
                "\n--- [المصادر المعتمدة (Verified Grounding Sources)] ---\n"
                "لا توجد مصادر مسجلة في الذاكرة بخصوص هذا الاستفسار.\n"
                "تنبيه صارم: اعتذر فوراً وأكد أن المعلومة غير مسجلة حالياً.\n"
                "----------------------------------------------------"
            )

        # 6. User Query
        prompt_parts.append(f"\n[سؤال المستخدم]:\n{query.strip()}\n\n[الرد]:")
        return "\n".join(prompt_parts)

    def verify_response(
        self,
        query: str,
        response: str,
        retrieved_memories: List[str],
        is_greeting: bool = False,
    ) -> str:
        """
        Direct Fact Verification (No Fallback Model):
        Validates the output against retrieved memories.
        """
        return FactVerifier.verify_and_sanitize(query, response, retrieved_memories, is_greeting=is_greeting)

    # ── Memory Ingestion & Modification ───────────────────────────────────────

    def _add_memory_sync(
        self,
        content: str,
        personality_id: int | None,
        embedding: bytes | None,
        source: str,
        importance: int,
    ) -> int:
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)

        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO memories (content, personality_id, embedding, source, importance, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (content, personality_id, embedding, source, importance, datetime.now(timezone.utc).isoformat()),
        )
        mid = cursor.lastrowid
        conn.commit()
        conn.close()

        # Update in-memory vector store
        mem = Memory(
            id=mid,
            content=content,
            personality_id=personality_id,
            embedding=embedding,
            source=source,
            importance=importance,
        )
        self._vstore.add_or_update(mem)
        return mid

    async def add_memory(
        self,
        content: str,
        personality_id: int | None = None,
        source: str = "conversation",
        importance: int = 5,
        db: AsyncSession | None = None,
    ) -> int:
        """
        Add a new memory with automatic embedding generation and vector store synchronization.
        """
        await self._ensure_embedder()

        embedding_bytes: bytes | None = None
        vec_array: Optional[np.ndarray] = None
        if self._embedder != "disabled" and np is not None:
            try:
                vec = await self._embed_async(content)
                if vec is not None:
                    vec_array = vec.astype(np.float32)
                    embedding_bytes = vec_array.tobytes()
            except Exception as e:
                logger.warning(f"Could not generate embedding for new memory: {e}")

        if db is not None:
            mem = Memory(
                content=content.strip(),
                personality_id=personality_id,
                embedding=embedding_bytes,
                source=source,
                importance=importance,
            )
            db.add(mem)
            await db.commit()
            await db.refresh(mem)
            self._vstore.add_or_update(mem, vec=vec_array)
            logger.info(f"Memory {mem.id} added via db session (personality: {personality_id})")
            return mem.id
        else:
            return self._add_memory_sync(
                content.strip(),
                personality_id,
                embedding_bytes,
                source,
                importance,
            )

    # ── Internals ─────────────────────────────────────────────────────────────

    def _embed(self, text: str):
        """Thread-safe embedding computation with RLock-guarded cache."""
        with RAGService._cache_lock:
            if text in RAGService._shared_cache:
                return RAGService._shared_cache[text]

        vec = self._embedder.encode(text, normalize_embeddings=True)

        with RAGService._cache_lock:
            if len(RAGService._shared_cache) > 2048:
                RAGService._shared_cache.clear()
            RAGService._shared_cache[text] = vec
        return vec

    async def _embed_async(self, text: str):
        """Non-blocking asynchronous embedding offloaded to worker thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_RAG_EXECUTOR, self._embed, text)

    def _normalize_arabic(self, text: str) -> str:
        from app.utils.masri_normalizer import normalize_masri_orthography
        return normalize_masri_orthography(text)

    def _tokenize(self, text: str) -> set[str]:
        """Tokenize with Arabic BM25 tokenizer and conversational expansions for backwards compatibility."""
        tokens = set(ArabicBM25Tokenizer.tokenize(text))
        raw_norm = self._normalize_arabic(text).lower()
        if "اسمك" in raw_norm:
            tokens.add("اسم")
        if "مين" in raw_norm or "انت" in raw_norm:
            tokens.add("اسم")
            tokens.add("روبوت")
            tokens.add("نيبولا")
        return tokens

    def _lexical_score(self, query: str, document: str) -> float:
        """BM25-backed alignment lexical scoring."""
        bm = BM25Okapi([document])
        scores = bm.get_scores(query)
        return scores[0] if scores else 0.0

    def _update_access_times_sync(self, memory_ids: list[int]) -> None:
        if not memory_ids:
            return
        try:
            db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
            if db_path.startswith("./"):
                db_path = db_path[2:]
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)

            conn = sqlite3.connect(db_path, timeout=3.0)
            cursor = conn.cursor()
            now_iso = datetime.now(timezone.utc).isoformat()
            cursor.executemany(
                "UPDATE memories SET last_accessed = ? WHERE id = ?",
                [(now_iso, mid) for mid in memory_ids],
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Could not update last_accessed: {e}")
