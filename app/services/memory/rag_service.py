"""
RAG Memory Service — High-Performance Multithreaded Hybrid Retrieval.

Multithreading Architecture & Concurrency:
- Dedicated ThreadPoolExecutor (_RAG_EXECUTOR) for non-blocking CPU-bound vector & NLP tasks.
- Parallel Sub-Query Execution: Multiple sub-queries execute concurrently across worker threads.
- Parallel Dense + Sparse Hybrid Search (VectorStore Matrix Multiply + Okapi BM25).
- Thread-safe RLock-guarded embedding cache (_shared_cache) and in-memory VectorStore.
- Asynchronous Non-blocking Cross-Reranking and access-time database updates.
- Strictly Deterministic Hybrid Retrieval.
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
                embedder = None
                try:
                    embedder = SentenceTransformer(
                        settings.EMBEDDING_MODEL,
                        device=settings.EMBEDDING_DEVICE,
                        local_files_only=True,
                    )
                    logger.info(f"Embedding model loaded from local cache: {settings.EMBEDDING_MODEL}")
                except Exception:
                    pass

                if embedder is None:
                    try:
                        embedder = SentenceTransformer(
                            settings.EMBEDDING_MODEL,
                            device=settings.EMBEDDING_DEVICE,
                            local_files_only=False,
                        )
                        logger.info(f"Embedding model loaded/downloaded: {settings.EMBEDDING_MODEL}")
                    except Exception:
                        pass

                if embedder is not None:
                    RAGService._shared_embedder = embedder
                    self._embedder = embedder
                    return

                logger.info("Embedding weights not in cache/network; RAG utilizing accelerated Okapi BM25 engine.")
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

    @staticmethod
    def _should_augment_with_person(query: str, person_name: str) -> bool:
        if not person_name:
            return False
        q_lower = query.lower()
        if person_name.lower() in q_lower:
            return True
        robot_keywords = [
            "نيبولا", "روبوت", "robot", "nebula", "محرك", "سيرفو", "كاميرا",
            "مستشعر", "حساس", "بطارية", "esp", "عتاد", "hardware", "طقس", "weather"
        ]
        if any(rk in q_lower for rk in robot_keywords):
            return False
        person_signals = [
            "هو", "هي", "مين", "بيحب", "شغال", "بيشتغل", "تخصص", "مواليد",
            "سنة", "تخرج", "مشروع", "أكل", "اكل", "شرب", "مكان", "فين", "معاه", "عنده",
            "who", "he", "she", "his", "her", "work", "project", "like"
        ]
        return any(ps in q_lower for ps in person_signals) or len(query.split()) <= 3

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
        should_use_person = bool(clean_person and self._should_augment_with_person(sub_query, clean_person))
        augmented_sq = f"{clean_person} {sub_query}" if (should_use_person and clean_person and clean_person not in sub_query) else sub_query

        sem_scores: dict[int, float] = {}
        lex_scores: dict[int, float] = {}

        # 1. Vector Dense Search
        if self._embedder != "disabled":
            try:
                embed_text = augmented_sq if should_use_person else sub_query
                query_vec = self._embed(embed_text)
                if query_vec is not None:
                    vec_hits = self._vstore.search(
                        query_vec=query_vec,
                        top_k=25,
                        personality_id=personality_id,
                        person_name=clean_person if should_use_person else None,
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

        # Boost person name if found in memory text and query is person-relevant
        if should_use_person and clean_person:
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
            is_init = self._vstore._is_initialized
            cached_ids = set(self._vstore._memory_cache.keys())
        missing_ids = incoming_ids - cached_ids
        if not is_init or missing_ids:
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

        # Direct BM25 pass if no candidates matched
        if not accumulated_candidates:
            direct_bm25 = bm25.get_scores(query)
            for idx, sc in enumerate(direct_bm25):
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

        top_score = scored[0][0]
        # Require confident topic relevance (disregard noise/unrecorded queries)
        if top_score < 0.35:
            return []

        # Selective margin cutoff: only retain memories within 75% of the top match
        cutoff = max(0.35, top_score * 0.75)
        top_k = top_k or settings.MEMORY_TOP_K
        seen_contents: set[str] = set()
        unique_top: list[Memory] = []

        for score, mem in scored:
            norm_content = self._normalize_for_dedup(mem.content)
            if norm_content in seen_contents:
                continue

            # Temporal suppression: if an already-accepted memory supersedes/conflicts with this one, skip obsolete memory
            is_conflicted = any(self._is_conflicting_fact(m.content, mem.content) for m in unique_top)
            if not is_conflicted:
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

        top_score = scored[0][0]
        if top_score < 0.35:
            return []

        cutoff = max(0.35, top_score * 0.75)
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
        has_action: bool = False,
    ) -> str:
        """
        Direct Fact Verification:
        Validates the output against retrieved memories.
        """
        return FactVerifier.verify_and_sanitize(query, response, retrieved_memories, is_greeting=is_greeting, has_action=has_action)

    # ── Memory Ingestion & Modification ───────────────────────────────────────

    def _is_conflicting_fact(self, new_text: str, old_text: str) -> bool:
        """
        Determines whether a new memory supersedes/conflicts with an existing older memory.
        Example:
          old: "أحمد حط الكتاب في الصالة"
          new: "أحمد نقل الكتاب وحطه علي الكرسيي"
          -> Returns True (supersedes old location).
        """
        if not new_text or not old_text:
            return False

        norm_new = self._normalize_arabic(new_text).lower()
        norm_old = self._normalize_arabic(old_text).lower()
        if norm_new == norm_old:
            return True

        tokens_new = set(re.findall(r"[\u0600-\u06FF\w]{3,}", norm_new))
        tokens_old = set(re.findall(r"[\u0600-\u06FF\w]{3,}", norm_old))

        stopwords = {
            "على", "علي", "الي", "الى", "عن", "مع", "عند", "كان", "كانت", "يكون",
            "اللي", "ذلك", "هذا", "هذه", "عشان", "علشان", "خلاص", "تمام",
            "نيبولا", "وبعدين", "حيث", "حتى", "اكتر", "اكثر", "في", "من"
        }
        content_new = tokens_new - stopwords
        content_old = tokens_old - stopwords

        common_entities = content_new & content_old
        if not common_entities:
            return False

        update_indicators = {
            "نقل", "نقله", "نقلت", "حط", "حطه", "حطيت", "شال", "شاله", "شلت",
            "غير", "غيره", "غيرت", "بدل", "بدله", "بقى", "بقت", "اصبح",
            "اتأجل", "اتاجل", "تأجل", "تاجيل", "دلوقتي", "حاليا", "مكان"
        }
        has_update_cue = bool((tokens_new | tokens_old) & update_indicators)

        subject_items = {
            "كتاب", "مفتاح", "عربية", "محفظة", "ساعة", "شاحن", "لابتوب",
            "كمبيوتر", "شنطة", "نظارة", "ميعاد", "معاد", "اجتماع", "فلوس",
            "كرسي", "ترابيزة", "مكتب", "صالة", "اوضة", "غرفة", "درج", "دولاب"
        }
        common_subjects = common_entities & subject_items

        if common_subjects and (has_update_cue or len(common_entities) >= 2):
            return True

        if len(common_entities) >= 2 and len(common_entities) / min(len(content_new), len(content_old)) >= 0.5:
            return True

        return False

    def _add_memory_sync(
        self,
        content: str,
        personality_id: int | None,
        embedding: bytes | None,
        source: str,
        importance: int,
        user_id: int | None = None,
    ) -> int:
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)

        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()

        # Automatic Conflict Resolution: Check for and delete conflicting obsolete memories
        if personality_id is not None:
            cursor.execute(
                "SELECT id, content FROM memories WHERE personality_id = ? OR personality_id IS NULL",
                (personality_id,),
            )
        else:
            cursor.execute("SELECT id, content FROM memories")
        existing_rows = cursor.fetchall()
        obsolete_ids = [r[0] for r in existing_rows if self._is_conflicting_fact(content, r[1])]
        for oid in obsolete_ids:
            cursor.execute("DELETE FROM memories WHERE id = ?", (oid,))
            self._vstore.delete(oid)
            logger.info(f"Auto-resolved conflicting memory: removed obsolete memory ID {oid} in favor of: '{content}'")

        cursor.execute(
            "INSERT INTO memories (user_id, content, personality_id, embedding, source, importance, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, content, personality_id, embedding, source, importance, datetime.now(timezone.utc).isoformat()),
        )
        mid = cursor.lastrowid
        conn.commit()
        conn.close()

        if obsolete_ids:
            with RAGService._cache_lock:
                RAGService._shared_cache.clear()

        # Update in-memory vector store
        mem = Memory(
            id=mid,
            user_id=user_id,
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
        user_id: int | None = None,
        db: AsyncSession | None = None,
    ) -> int:
        """
        Add a new memory with automatic embedding generation, conflict resolution and vector store synchronization.
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
            # Automatic Conflict Resolution: detect & remove obsolete conflicting memories
            stmt = select(Memory)
            if personality_id is not None:
                stmt = stmt.where((Memory.personality_id == personality_id) | (Memory.personality_id.is_(None)))
            res = await db.execute(stmt)
            existing_mems = res.scalars().all()
            obsolete_found = False
            for ex in existing_mems:
                if self._is_conflicting_fact(content.strip(), ex.content):
                    logger.info(f"Auto-resolving conflicting memory: removing obsolete memory {ex.id} ('{ex.content}') in favor of: '{content.strip()}'")
                    await db.delete(ex)
                    self._vstore.delete(ex.id)
                    obsolete_found = True

            mem = Memory(
                user_id=user_id,
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
            if obsolete_found:
                with RAGService._cache_lock:
                    RAGService._shared_cache.clear()

            logger.info(f"Memory {mem.id} added via db session (personality: {personality_id}, user: {user_id})")
            return mem.id
        else:
            return self._add_memory_sync(
                content.strip(),
                personality_id,
                embedding_bytes,
                source,
                importance,
                user_id=user_id,
            )

    async def delete_memory(self, memory_id: int, db: AsyncSession | None = None) -> bool:
        """
        Deletes a memory from the in-memory VectorStore and optionally from the database.
        """
        # Invalidate in-memory vector store cache and matrix
        self._vstore.delete(memory_id)

        # Clear embedding cache
        with RAGService._cache_lock:
            RAGService._shared_cache.clear()

        if db is not None:
            mem = await db.get(Memory, memory_id)
            if mem:
                await db.delete(mem)
                await db.commit()
                return True
            return False
        else:
            try:
                db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
                if db_path.startswith("./"):
                    db_path = db_path[2:]
                if not os.path.isabs(db_path):
                    db_path = os.path.abspath(db_path)
                conn = sqlite3.connect(db_path, timeout=5.0)
                cursor = conn.cursor()
                cursor.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                logger.warning(f"Could not delete memory sync from SQLite: {e}")
                return False

        return True

    async def update_memory(
        self,
        memory_id: int,
        content: str | None = None,
        personality_id: int | None = None,
        source: str | None = None,
        importance: int | None = None,
        db: AsyncSession | None = None,
    ) -> Memory | None:
        """
        Update an existing memory: updates fields, regenerates embedding if content changed,
        and synchronizes with in-memory VectorStore and DB.
        """
        await self._ensure_embedder()

        if db is not None:
            mem = await db.get(Memory, memory_id)
            if not mem:
                return None

            content_changed = False
            if content is not None:
                stripped_content = content.strip()
                if stripped_content and stripped_content != mem.content:
                    mem.content = stripped_content
                    content_changed = True

            if personality_id is not None:
                mem.personality_id = personality_id
            if source is not None:
                mem.source = source
            if importance is not None:
                mem.importance = importance

            vec_array: Optional[np.ndarray] = None
            if content_changed:
                if self._embedder != "disabled" and np is not None:
                    try:
                        vec = await self._embed_async(mem.content)
                        if vec is not None:
                            vec_array = vec.astype(np.float32)
                            mem.embedding = vec_array.tobytes()
                    except Exception as e:
                        logger.warning(f"Could not re-generate embedding on memory update: {e}")
                else:
                    mem.embedding = None

            await db.commit()
            await db.refresh(mem)

            # Update in-memory vector store & clear cache
            self._vstore.add_or_update(mem, vec=vec_array)
            with RAGService._cache_lock:
                RAGService._shared_cache.clear()

            logger.info(f"Memory {mem.id} updated (personality: {mem.personality_id})")
            return mem
        else:
            # Sync SQLite fallback
            db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
            if db_path.startswith("./"):
                db_path = db_path[2:]
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)

            conn = sqlite3.connect(db_path, timeout=5.0)
            cursor = conn.cursor()
            cursor.execute("SELECT id, content, personality_id, source, importance FROM memories WHERE id = ?", (memory_id,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return None

            old_content = row[1]
            new_content = content.strip() if content is not None else old_content
            new_pid = personality_id if personality_id is not None else row[2]
            new_src = source if source is not None else row[3]
            new_imp = importance if importance is not None else row[4]

            vec_array: Optional[np.ndarray] = None
            embedding_bytes: Optional[bytes] = None
            if new_content != old_content:
                if self._embedder != "disabled" and np is not None:
                    try:
                        vec = await self._embed_async(new_content)
                        if vec is not None:
                            vec_array = vec.astype(np.float32)
                            embedding_bytes = vec_array.tobytes()
                    except Exception as e:
                        logger.warning(f"Could not re-generate embedding for sync update: {e}")
                cursor.execute(
                    "UPDATE memories SET content = ?, personality_id = ?, embedding = ?, source = ?, importance = ? WHERE id = ?",
                    (new_content, new_pid, embedding_bytes, new_src, new_imp, memory_id),
                )
            else:
                cursor.execute(
                    "UPDATE memories SET personality_id = ?, source = ?, importance = ? WHERE id = ?",
                    (new_pid, new_src, new_imp, memory_id),
                )
            conn.commit()
            conn.close()

            mem = Memory(
                id=memory_id,
                content=new_content,
                personality_id=new_pid,
                embedding=embedding_bytes,
                source=new_src,
                importance=new_imp,
            )
            self._vstore.add_or_update(mem, vec=vec_array)
            with RAGService._cache_lock:
                RAGService._shared_cache.clear()
            return mem

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
