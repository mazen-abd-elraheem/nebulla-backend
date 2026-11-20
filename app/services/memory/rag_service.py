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
from app.utils.masri_normalizer import normalize_masri_orthography

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
                "SELECT id, content, personality_id, embedding, source, importance, is_active FROM memories WHERE (is_active = 1 OR is_active IS NULL) AND (personality_id = ? OR personality_id IS NULL)",
                (personality_id,),
            )
            rows = cursor.fetchall()
        else:
            cursor.execute("SELECT id, content, personality_id, embedding, source, importance, is_active FROM memories WHERE (is_active = 1 OR is_active IS NULL)")
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
                is_active=bool(r[6]) if len(r) > 6 and r[6] is not None else True,
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
        if should_use_person and clean_person and personality_id is None:
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

            # Persona Hierarchy Boost: if personality_id is specified and memory belongs specifically to this persona, prioritize it
            persona_boost = 0.15 if (personality_id is not None and getattr(mem, "personality_id", None) == personality_id) else 0.0

            combined = (score_rrf * 10.0) + (raw_sem * 0.6) + (raw_lex * 0.5) + importance_boost + persona_boost
            sq_candidates[mid] = combined

        return sq_candidates

    async def _get_personality_names_map(self, db: AsyncSession | None = None) -> dict[int, str]:
        """Loads a map of personality_id -> clean first name (e.g. 1: 'مازن', 2: 'أحمد')."""
        p_map: dict[int, str] = {}
        if db is not None:
            try:
                from app.models.personality import Personality
                res = await db.execute(select(Personality))
                for p in res.scalars().all():
                    if "مازن" in p.name or p.id == 1:
                        clean_name = "مازن"
                    else:
                        clean_name = p.name.split()[0].replace("(", "").replace(")", "").strip()
                    p_map[p.id] = clean_name
            except Exception as e:
                logger.debug(f"Could not load personality map from async db: {e}")

        if not p_map:
            try:
                db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
                if db_path.startswith("./"):
                    db_path = db_path[2:]
                if not os.path.isabs(db_path):
                    db_path = os.path.abspath(db_path)
                conn = sqlite3.connect(db_path, timeout=5.0)
                cur = conn.cursor()
                for pid, pname in cur.execute("SELECT id, name FROM personalities"):
                    if "مازن" in pname or pid == 1:
                        clean_name = "مازن"
                    else:
                        clean_name = pname.split()[0].replace("(", "").replace(")", "").strip()
                    p_map[pid] = clean_name
                conn.close()
            except Exception:
                pass

        return p_map

    @classmethod
    def attribute_memory_content(cls, content: str, persona_name: Optional[str], query: str = "") -> str:
        """
        Attributes memory content to persona name if not already mentioned,
        dynamically supporting any item noun (e.g., 'الكراسه علي الارض' + 'أحمد' -> 'كراسة أحمد علي الارض').
        Never adds awkward robotic prefixes like 'عند فلان:'.
        """
        if not persona_name or not content:
            return content
        clean_p = persona_name.strip()
        norm_c = QueryDecomposer._norm(content)
        norm_p = QueryDecomposer._norm(clean_p)
        if norm_p in norm_c:
            return content

        # Check if memory describes an item or physical location
        m = re.match(r'^(?:ال)?([^\s]+)\b\s*(.*)', content)
        if m:
            raw_item = m.group(1).strip()
            rest = m.group(2).strip()
            norm_raw = QueryDecomposer._norm(raw_item)

            non_items = {
                "هو", "هي", "هم", "انا", "احنا", "انت", "انتي",
                "في", "على", "علي", "من", "عن", "الى", "إلى", "مع", "عند", "فوق", "تحت", "ورا", "قدام", "جنب",
                "كان", "كانت", "يكون", "مش", "مش مسجل", "فيه", "شغال", "شغالة", "شغاله", "بيشتغل", "بتشتغل",
                "عايش", "ساكن", "ساكنة", "ساكنه", "اتولد", "مواليد", "بيحب", "بتحب", "عنده", "عندها", "معاه", "معاها"
            }
            if norm_raw not in non_items and len(raw_item) >= 2:
                is_loc = QueryDecomposer.is_location_fact(content)
                q_items = QueryDecomposer.extract_subject_items(query, clean_p) if query else set()
                item_matches_query = bool(q_items and (norm_raw in q_items or any(qi in norm_raw for qi in q_items)))

                if is_loc or item_matches_query:
                    item = raw_item
                    if item.startswith("ال") and len(item) > 3:
                        item = item[2:]
                    if item.endswith(('ه', 'ة')):
                        item = item[:-1] + 'ة'
                    return f"{item} {clean_p} {rest}".strip()

        return content

    @classmethod
    def _is_memory_entity_match(
        cls,
        mem_content: str,
        mem_pid: Optional[int],
        target_persona_name: Optional[str],
        target_pid: Optional[int],
        p_map: Optional[dict[int, str]] = None,
    ) -> bool:
        """
        Strict Entity Isolation:
        When a query targets persona X (e.g. 'مازن' or 'أحمد' or 'مصعب'):
        - Returns True if content explicitly mentions target persona.
        - Returns False if content explicitly names another person and NOT target persona.
        - Returns False if memory's explicit personality_id is different from target_pid.
        - Returns False if memory belongs to a specific persona (mem_pid is not None)
          whose name is different from target_persona_name, UNLESS target persona is mentioned in content.
        - Returns True for shared or persona-scoped memories that have no conflicting entity names.
        """
        if not target_persona_name:
            return True

        norm_content = QueryDecomposer._norm(mem_content)
        norm_target = QueryDecomposer._norm(target_persona_name)

        # 1. Target persona explicitly named in content -> direct match
        if norm_target in norm_content:
            return True

        # 2. Extract conflicting persona names in content
        mentioned_names = QueryDecomposer.extract_mentioned_person_names(mem_content)
        conflicting = {QueryDecomposer._norm(n) for n in mentioned_names} - {norm_target}
        if conflicting:
            return False

        # 3. Explicit personality_id mismatch
        if mem_pid is not None and target_pid is not None and mem_pid != target_pid:
            return False

        # 4. Memory belongs to a specific system persona, but query targets another entity (e.g. Mosaab)
        if mem_pid is not None and p_map:
            mem_owner_name = p_map.get(mem_pid)
            if mem_owner_name and QueryDecomposer._norm(mem_owner_name) != norm_target:
                return False
        elif mem_pid is not None and target_pid is None:
            return False

        return True

        return True

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

        # Load personality name mappings to detect targeted personas
        p_map = await self._get_personality_names_map(db)

        # Multi-Hop Relational Intent Decomposition (e.g. 'عربية صاحب أحمد نوعها ايه؟')
        rel_info = QueryDecomposer.decompose_multihop_relational(query)

        # Detect if query explicitly targets a specific persona (e.g. 'ساعة أحمد فين', 'يا مازن الساعة فين', 'مازن شغال ايه')
        # In multi-hop relational questions, we do not restrict to origin person only since downstream hop queries a related entity.
        target_persona_name = None if rel_info else QueryDecomposer.extract_target_persona_name(query, list(p_map.values()))
        if target_persona_name:
            norm_target = QueryDecomposer._norm(target_persona_name)
            for pid, pname in p_map.items():
                if QueryDecomposer._norm(pname) == norm_target or (norm_target in ("مازن", "mazen") and pid == 1):
                    personality_id = pid
                    logger.info(f"Targeted persona '{target_persona_name}' detected in query -> Scoping RAG to PID {pid}.")
                    break

        # Load memories from DB matching personality, shared, or explicitly mentioning the targeted persona
        if db is not None:
            stmt = select(Memory).where((Memory.is_active == True) | (Memory.is_active.is_(None)))
            if personality_id is not None and not rel_info:
                conditions = (Memory.personality_id == personality_id) | (Memory.personality_id.is_(None))
                if target_persona_name:
                    p1 = f"%{target_persona_name}%"
                    p2 = f"%{target_persona_name.replace('أ', 'ا')}%"
                    conditions = conditions | (Memory.content.like(p1)) | (Memory.content.like(p2))
                stmt_p = stmt.where(conditions)
                res = await db.execute(stmt_p)
                memories = list(res.scalars().all())
            else:
                res = await db.execute(stmt)
                memories = list(res.scalars().all())
        else:
            memories = self._load_memories_sync(None if rel_info else personality_id)

        if not memories:
            return []

        # Strict Entity-Level Subject Isolation:
        # If targeting a specific persona (e.g. Mazen), exclude memories about other entities (e.g. Omar the driver, Ahmed)
        if target_persona_name and not rel_info:
            memories = [
                m for m in memories
                if self._is_memory_entity_match(m.content, m.personality_id, target_persona_name, personality_id, p_map=p_map)
            ]
            if not memories:
                return []

        if not memories:
            return []

        # Strict Semantic Aspect Filtering (Age, Job, Location, Hobby, Schedule, Residence, Clothing, Contact)
        # Guarantees that if a specific aspect is inquired, ONLY facts matching that exact aspect are retained.
        # If no fact in memory matches the requested aspect, returns [] so the assistant truthfully refuses.
        inquiry_aspect = QueryDecomposer.get_inquiry_aspect(query)
        if inquiry_aspect and not rel_info:
            matching_aspect_mems = [m for m in memories if QueryDecomposer.fact_has_aspect(m.content, inquiry_aspect)]
            if matching_aspect_mems:
                memories = matching_aspect_mems
            else:
                logger.info(f"RAG: Query requested aspect '{inquiry_aspect}', but no candidate memory has this aspect. Enforcing empty context.")
                return []

        if not memories:
            return []

        # Strict Subject Item Isolation:
        # If the user asks about a specific object/item (e.g. 'قلم احمد فين' or 'ساعة احمد فين'),
        # candidate memories MUST contain the requested item (or its morphological stem/synonym).
        # NEVER substitute a watch when asked about a pen, or vice-versa!
        query_items = QueryDecomposer.extract_subject_items(query, target_persona_name)
        if query_items and not rel_info and inquiry_aspect == "location":
            item_filtered = []
            for m in memories:
                norm_m = normalize_masri_orthography(m.content).lower()
                m_tokens = set(re.findall(r"[\w\d]+", norm_m))
                for w in list(m_tokens):
                    if w.startswith("ال") and len(w) > 3:
                        m_tokens.add(w[2:])
                if query_items & m_tokens:
                    item_filtered.append(m)
            if item_filtered:
                memories = item_filtered
            else:
                logger.info(f"RAG: Query asked for item(s) {query_items}, but no candidate memory contains this item. Returning empty.")
                return []

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

        # Decompose query into sub-queries and strip vocatives & targeted persona name from search targets
        sub_queries = QueryDecomposer.decompose(query)
        cleaned_subqueries: list[str] = []
        for sq in sub_queries:
            c_sq = QueryDecomposer.clean_vocative(sq)
            if target_persona_name:
                c_sq = re.sub(
                    rf'\b(?:عند|بتاع|بتاعة|بتاعت|تبع)?\s*(?:{re.escape(target_persona_name)}|احمد|أحمد|مازن|توت)\b',
                    ' ',
                    c_sq,
                    flags=re.IGNORECASE,
                )
                c_sq = re.sub(r'\s+', ' ', c_sq).strip()
            if c_sq and len(c_sq) >= 2:
                cleaned_subqueries.append(c_sq)
            else:
                cleaned_subqueries.append(sq)
        if query not in cleaned_subqueries:
            cleaned_subqueries.insert(0, query)

        # Multi-Hop Relational Intent Decomposition (e.g. 'عربية صاحب أحمد نوعها ايه؟')
        rel_info = QueryDecomposer.decompose_multihop_relational(query)
        if rel_info:
            step1_q = rel_info["step1_query"]
            step1_scores = bm25.get_scores(step1_q)
            best_idx = max(range(len(step1_scores)), key=lambda i: step1_scores[i]) if step1_scores else None
            if best_idx is not None and step1_scores[best_idx] > 0.0:
                hop1_mem = memories[best_idx].content
                dyn_names = QueryDecomposer.extract_mentioned_person_names(hop1_mem)
                origin_norm = QueryDecomposer._norm(rel_info["origin_person"])
                intermediate = dyn_names - {origin_norm}
                if intermediate:
                    resolved_person = list(intermediate)[0]
                    hop2_q = f"{rel_info['downstream_attr']} {resolved_person}"
                    logger.info(f"Multi-Hop resolved '{step1_q}' -> '{resolved_person}'. Generated Step 2: '{hop2_q}'")
                    if hop2_q not in cleaned_subqueries:
                        cleaned_subqueries.append(hop2_q)

        sub_queries = cleaned_subqueries if cleaned_subqueries else [query]
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

        # Adaptive Fast-Path:
        # If top candidate is dominant (single match >= 0.60 or dominant margin >= 0.18 over second with score >= 0.78),
        # bypass Cross-Encoder completely for instant sub-80ms response on CPU!
        sorted_accum = sorted(accumulated_candidates.items(), key=lambda x: x[1], reverse=True)
        is_clear_match = False
        if len(sorted_accum) == 1 and sorted_accum[0][1] >= 0.60:
            is_clear_match = True
        elif len(sorted_accum) > 1 and sorted_accum[0][1] >= 0.78:
            gap = sorted_accum[0][1] - sorted_accum[1][1]
            if gap >= 0.18:
                is_clear_match = True

        if (is_clear_match and len(sub_queries) <= 2) or rel_info:
            reason = "Multi-Hop Relational Fast-Path" if rel_info else f"Score: {sorted_accum[0][1]:.3f}"
            logger.info(f"Adaptive Fast-Path engaged: bypassing Cross-Encoder ({reason})")
            final_scored = [(sc, mem_by_id[mid]) for mid, sc in sorted_accum[:20]]
            return final_scored

        # Multithreaded Cross-Encoder / Alignment Re-ranking using attributed content
        candidate_items = [
            (
                score,
                mem_by_id[mid],
                self.attribute_memory_content(mem_by_id[mid].content, p_map.get(mem_by_id[mid].personality_id), query),
            )
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

        is_loc_q = QueryDecomposer.is_location_query(query)
        rel_info = QueryDecomposer.decompose_multihop_relational(query)
        atomic_subs = QueryDecomposer.get_atomic_subqueries(query)
        effective_top_k = top_k or (2 if rel_info else len(atomic_subs))
        # If cross-persona search (personality_id is None) and asking about location/item, allow multiple personas (up to 3)
        if personality_id is None and is_loc_q:
            effective_top_k = max(effective_top_k, 3)
        effective_top_k = max(effective_top_k, 2 if rel_info else 1)
        effective_top_k = min(effective_top_k, 6)

        # For composite/multi-part questions or cross-persona searches, use a balanced margin threshold
        # so valid facts across sub-queries or personas are retained while unrelated noise (< 0.50) is strictly filtered.
        if rel_info:
            cutoff = max(0.40, top_score * 0.50)
        elif len(atomic_subs) > 1 or personality_id is None:
            cutoff = max(0.45, top_score * 0.55)
        else:
            cutoff = max(0.50, top_score * 0.85)

        seen_contents: set[str] = set()
        seen_personas: set[int] = set()
        unique_top: list[Memory] = []

        for score, mem in scored:
            if score < cutoff:
                break
            norm_content = self._normalize_for_dedup(mem.content)
            if norm_content in seen_contents:
                continue

            # In cross-persona search for single-intent queries: allow at most 1 fact per distinct persona
            if personality_id is None and len(atomic_subs) <= 1:
                mem_pid = mem.personality_id or 0
                if mem_pid in seen_personas:
                    continue

            # Temporal suppression: if an already-accepted memory supersedes/conflicts with this one for the SAME persona, skip obsolete memory
            is_conflicted = any(
                (m.personality_id == mem.personality_id) and self._is_conflicting_fact(m.content, mem.content)
                for m in unique_top
            )
            if not is_conflicted:
                seen_contents.add(norm_content)
                if personality_id is None and len(atomic_subs) <= 1:
                    seen_personas.add(mem.personality_id or 0)
                unique_top.append(mem)
                if len(unique_top) >= effective_top_k:
                    break

        if unique_top:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(_RAG_EXECUTOR, self._update_access_times_sync, [m.id for m in unique_top])

        # Apply Context Re-ordering to eliminate 'Lost in the Middle'
        reordered_mems = self._reorder_context(unique_top)

        # Persona Attribution: if memory does not explicitly mention the persona name, attribute it clearly
        p_map = await self._get_personality_names_map(db)
        attributed_memories = [
            self.attribute_memory_content(m.content, p_map.get(m.personality_id), query)
            for m in reordered_mems
        ]
        return attributed_memories

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

        atomic_subs = QueryDecomposer.get_atomic_subqueries(query)
        effective_top_k = top_k or max(len(atomic_subs), 2)
        effective_top_k = min(effective_top_k, 6)

        if len(atomic_subs) > 1:
            cutoff = max(0.52, top_score * 0.70)
        else:
            cutoff = max(0.50, top_score * 0.85)

        seen_contents: set[str] = set()
        unique_scored: list[tuple[float, Memory]] = []

        for score, mem in scored:
            if score < cutoff:
                break
            norm_content = self._normalize_for_dedup(mem.content)
            if norm_content not in seen_contents:
                seen_contents.add(norm_content)
                unique_scored.append((score, mem))
                if len(unique_scored) >= effective_top_k:
                    break

        if unique_scored:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(_RAG_EXECUTOR, self._update_access_times_sync, [m.id for _, m in unique_scored])

        p_map = await self._get_personality_names_map(db)
        return [
            {
                "id": m.id,
                "content": m.content,
                "attributed_content": self.attribute_memory_content(m.content, p_map.get(m.personality_id), query),
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
          new: "أحمد نقل الكتاب وحطه علي المكتب"
          -> Returns True (supersedes old location).
        """
        if not new_text or not old_text:
            return False

        norm_new = self._normalize_arabic(new_text).lower()
        norm_old = self._normalize_arabic(old_text).lower()
        if norm_new == norm_old:
            return True

        # 1. Location facts conflict check:
        # If both describe physical locations, they conflict IF and ONLY IF they share the subject item!
        # (e.g. 'كراسة أحمد على المكتب' conflicts with 'الكراسة على الأرض', but 'ساعة أحمد' does NOT conflict with 'شنطة أحمد').
        is_loc_new = QueryDecomposer.is_location_fact(new_text)
        is_loc_old = QueryDecomposer.is_location_fact(old_text)
        if is_loc_new and is_loc_old:
            items_new = QueryDecomposer.extract_subject_items(new_text)
            items_old = QueryDecomposer.extract_subject_items(old_text)
            shared_items = items_new & items_old
            if shared_items:
                return True
            # If both are location facts but have completely different subject items, they never conflict!
            if items_new and items_old and not shared_items:
                return False

        # 2. Job facts conflict check:
        # If both describe a profession/job for the same person, they conflict!
        if QueryDecomposer.is_job_fact(new_text) and QueryDecomposer.is_job_fact(old_text):
            names_new = QueryDecomposer.extract_mentioned_person_names(new_text)
            names_old = QueryDecomposer.extract_mentioned_person_names(old_text)
            if (names_new & names_old) or (not names_new and not names_old):
                return True

        def _get_stems(text: str) -> set[str]:
            raw = re.findall(r"[\u0600-\u06FF\w]{3,}", text)
            stems = set()
            for w in raw:
                stems.add(w)
                if w.startswith("ال") and len(w) >= 4:
                    stems.add(w[2:])
            return stems

        tokens_new = _get_stems(norm_new)
        tokens_old = _get_stems(norm_old)

        stopwords = {
            "على", "علي", "الي", "الى", "عن", "مع", "عند", "كان", "كانت", "يكون",
            "اللي", "ذلك", "هذا", "هذه", "عشان", "علشان", "خلاص", "تمام",
            "نيبولا", "وبعدين", "حيث", "حتى", "اكتر", "اكثر", "في", "من",
            "انا", "أنا", "انت", "أنت", "هو", "هي", "احنا", "هما", "انو", "انه"
        }
        content_new = tokens_new - stopwords
        content_old = tokens_old - stopwords

        common_entities = content_new & content_old
        if not common_entities:
            return False

        update_indicators = {
            "نقل", "نقله", "نقلت", "حط", "حطه", "حطيت", "شال", "شاله", "شلت",
            "غير", "غيره", "غيرت", "بدل", "بدله", "بقا", "بقى", "بقت", "اصبح", "أصبح",
            "اتأجل", "اتاجل", "تأجل", "تاجيل", "تاخر", "اتأخر", "دلوقتي", "حاليا",
            "افتكر", "جديد", "جديده"
        }
        has_update_cue = bool((tokens_new | tokens_old) & update_indicators)

        # If they share an entity and an update cue is present (e.g. نقل، غير، بدل، بقى)
        if common_entities and has_update_cue:
            return True

        # If they share 2 or more entities (e.g. مصعب + شغال, or أحمد + كتاب)
        if len(common_entities) >= 2 and len(common_entities) / min(len(content_new), len(content_old)) >= 0.4:
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
        cursor.execute(
            "INSERT INTO memories (content, personality_id, user_id, embedding, source, importance, created_at, is_active) VALUES (?, ?, ?, ?, ?, ?, ?, 1)",
            (content, personality_id, user_id, embedding, source, importance, datetime.now(timezone.utc).isoformat()),
        )
        mid = cursor.lastrowid

        for oid in obsolete_ids:
            cursor.execute("UPDATE memories SET is_active = 0, superseded_by_id = ? WHERE id = ?", (mid, oid))
            self._vstore.delete(oid)
            logger.info(f"Auto-resolved conflicting memory: safely archived obsolete memory ID {oid} (superseded by {mid}) in favor of: '{content}'")

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
            # Automatic Conflict Resolution: detect & archive obsolete conflicting memories (preserve history)
            stmt = select(Memory).where(Memory.is_active == True)
            if isinstance(personality_id, int):
                stmt = stmt.where((Memory.personality_id == personality_id) | (Memory.personality_id.is_(None)))
            res = await db.execute(stmt)
            existing_mems = res.scalars().all()
            obsolete_found = False
            obsolete_mems = []
            for ex in existing_mems:
                if self._is_conflicting_fact(content.strip(), ex.content):
                    logger.info(f"Auto-resolving conflicting memory: archiving obsolete memory {ex.id} ('{ex.content}') in favor of: '{content.strip()}'")
                    ex.is_active = False
                    self._vstore.delete(ex.id)
                    obsolete_mems.append(ex)
                    obsolete_found = True

            mem = Memory(
                user_id=user_id,
                content=content.strip(),
                personality_id=personality_id,
                embedding=embedding_bytes,
                source=source,
                importance=importance,
                is_active=True,
            )
            db.add(mem)
            await db.commit()
            await db.refresh(mem)
            for ex in obsolete_mems:
                ex.superseded_by_id = mem.id
            if obsolete_mems:
                await db.commit()
            self._vstore.add_or_update(mem, vec=vec_array)
            if obsolete_found:
                with RAGService._cache_lock:
                    RAGService._shared_cache.clear()

            logger.info(f"Memory {mem.id} added via db session (personality: {personality_id}, user: {user_id})")
            return mem


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
                mem.is_active = False
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
                cursor.execute("UPDATE memories SET is_active = 0 WHERE id = ?", (memory_id,))
                conn.commit()
                conn.close()
                return True
            except Exception as e:
                logger.warning(f"Could not soft-delete memory sync from SQLite: {e}")
                return False

        return True

    async def find_matching_memory_for_action(
        self,
        query: str,
        personality_id: int | None = None,
        db: AsyncSession | None = None,
    ) -> Optional[Memory]:
        """
        Finds the single best existing memory in the database matching a target subject/phrase
        for in-chat modification or deletion.
        """
        if not query or not query.strip():
            return None

        # Resolve targeted persona if present in query (e.g. 'شغل احمد' -> Ahmed PID: 2)
        p_map = await self._get_personality_names_map(db)
        target_persona_name = QueryDecomposer.extract_target_persona_name(query, list(p_map.values()))
        if target_persona_name:
            norm_target = QueryDecomposer._norm(target_persona_name)
            for pid, pname in p_map.items():
                if QueryDecomposer._norm(pname) == norm_target or (norm_target in ("مازن", "mazen") and pid == 1):
                    personality_id = pid
                    break

        if db is not None:
            stmt = select(Memory).where((Memory.is_active == True) | (Memory.is_active.is_(None)))
            if isinstance(personality_id, int):
                stmt = stmt.where((Memory.personality_id == personality_id) | (Memory.personality_id.is_(None)))
            res = await db.execute(stmt)
            memories = list(res.scalars().all())
        else:
            memories = self._load_memories_sync(personality_id)

        if not memories:
            return None

        # Strict entity isolation
        if target_persona_name:
            memories = [
                m for m in memories
                if self._is_memory_entity_match(m.content, m.personality_id, target_persona_name, personality_id, p_map=p_map)
            ]
            if not memories:
                return None

        # Subject item priority matching:
        # If the target query specifies an item (e.g. 'كراسة' or 'ساعة'), find the candidate memory
        # whose subject item matches, preventing cross-item mismatch (e.g. updating watch instead of bag).
        q_items = QueryDecomposer.extract_subject_items(query, target_persona_name)
        if q_items:
            for m in memories:
                m_items = QueryDecomposer.extract_subject_items(m.content, target_persona_name)
                if q_items & m_items:
                    return m

        norm_q = self._normalize_arabic(query).lower()
        stopwords = {
            "في", "على", "علي", "ان", "إن", "هو", "هي", "من", "عن", "بتاع",
            "بتاعة", "معلومة", "معلومه", "حاجة", "حاجه", "مكان", "مكانها", "مكانه",
            "كان", "بقى", "بقت", "اصبح", "اصبحت", "خليها", "خليه", "مش", "ده", "دي", "اللي"
        }
        q_tokens = set(re.findall(r"[\w\d]+", norm_q)) - stopwords
        if not q_tokens:
            q_tokens = set(re.findall(r"[\w\d]+", norm_q))

        best_mem: Optional[Memory] = None
        best_score = 0.0

        for m in memories:
            norm_m = self._normalize_arabic(m.content).lower()
            m_tokens = set(re.findall(r"[\w\d]+", norm_m)) - stopwords
            overlap = q_tokens & m_tokens
            if overlap:
                score = len(overlap) / max(len(q_tokens), 1)
                if norm_q in norm_m or norm_m in norm_q:
                    score += 0.3
                if score > best_score:
                    best_score = score
                    best_mem = m

        if best_mem and best_score >= 0.25:
            return best_mem
        return None

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

    async def archive_and_replace_memory(
        self,
        old_memory_id: int,
        new_content: str,
        personality_id: int | None = None,
        source: str = "chat",
        importance: int = 8,
        user_id: int | None = None,
        db: AsyncSession | None = None,
    ) -> int:
        """
        Soft-deactivates the old memory (is_active = False, superseded_by_id = new_id),
        and creates the new active memory (is_active = True), keeping historical provenance.
        """
        # 1. Soft-deactivate old memory first so add_memory treats it as non-active
        if db is not None:
            old_mem = await db.get(Memory, old_memory_id)
            if old_mem:
                old_mem.is_active = False
                await db.commit()
                self._vstore.delete(old_memory_id)
        else:
            db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
            if db_path.startswith("./"):
                db_path = db_path[2:]
            if not os.path.isabs(db_path):
                db_path = os.path.abspath(db_path)
            conn = sqlite3.connect(db_path, timeout=5.0)
            cur = conn.cursor()
            cur.execute("UPDATE memories SET is_active = 0 WHERE id = ?", (old_memory_id,))
            conn.commit()
            conn.close()
            self._vstore.delete(old_memory_id)

        # 2. Add new active memory
        new_res = await self.add_memory(
            content=new_content,
            personality_id=personality_id,
            source=source,
            importance=importance,
            user_id=user_id,
            db=db,
        )
        new_mid = new_res.id if hasattr(new_res, "id") else int(new_res)

        # 3. Link superseded_by_id on old memory
        if db is not None:
            old_mem = await db.get(Memory, old_memory_id)
            if old_mem:
                old_mem.superseded_by_id = new_mid
                await db.commit()
                await db.refresh(old_mem)
        else:
            conn = sqlite3.connect(db_path, timeout=5.0)
            cur = conn.cursor()
            cur.execute("UPDATE memories SET superseded_by_id = ? WHERE id = ?", (new_mid, old_memory_id))
            conn.commit()
            conn.close()

        # Clear query cache
        with RAGService._cache_lock:
            RAGService._shared_cache.clear()

        logger.info(f"Safely archived memory {old_memory_id} (superseded by {new_mid}): '{new_content}'")
        return new_mid

    async def retrieve_historical_contrast(
        self,
        query: str,
        personality_id: int | None = None,
        db: AsyncSession | None = None,
    ) -> list[str]:
        """
        For past-tense inquiries (e.g. 'كراسة أحمد كانت فين قبل كده؟'):
        Finds the archived/previous memory and the current active memory for the inquired item/entity,
        and constructs a historical contrast context:
        'مكان كراسة أحمد السابق كان [المكان القديم]، وحالياً اتنقلت وبقت [المكان الحالي].'
        """
        p_map = await self._get_personality_names_map(db)
        target_persona_name = QueryDecomposer.extract_target_persona_name(query, list(p_map.values()))
        if target_persona_name:
            norm_target = QueryDecomposer._norm(target_persona_name)
            for pid, pname in p_map.items():
                if QueryDecomposer._norm(pname) == norm_target or (norm_target in ("مازن", "mazen") and pid == 1):
                    personality_id = pid
                    break

        query_items = QueryDecomposer.extract_subject_items(query, target_persona_name)
        if not query_items:
            return []

        if db is not None:
            stmt = select(Memory).order_by(Memory.id.desc())
            if isinstance(personality_id, int):
                stmt = stmt.where((Memory.personality_id == personality_id) | (Memory.personality_id.is_(None)))
            res = await db.execute(stmt)
            all_mems = list(res.scalars().all())
        else:
            all_mems = self._load_memories_sync(personality_id)

        if target_persona_name:
            all_mems = [
                m for m in all_mems
                if self._is_memory_entity_match(m.content, m.personality_id, target_persona_name, personality_id, p_map=p_map)
            ]

        matching_inactive = []
        matching_active = []

        for m in all_mems:
            m_items = QueryDecomposer.extract_subject_items(m.content, target_persona_name)
            if query_items & m_items:
                if m.is_active:
                    matching_active.append(m)
                else:
                    matching_inactive.append(m)

        if not matching_inactive and not matching_active:
            return []

        # Format historical contrast
        if matching_inactive and matching_active:
            old_mem = matching_inactive[0]
            new_mem = None
            if old_mem.superseded_by_id:
                new_mem = next((m for m in matching_active if m.id == old_mem.superseded_by_id), None)
            if not new_mem:
                new_mem = matching_active[0]

            effective_pid = old_mem.personality_id or new_mem.personality_id or personality_id
            persona_label = target_persona_name or (p_map.get(effective_pid) if effective_pid else "")
            old_attr = self.attribute_memory_content(old_mem.content, persona_label, query)
            new_attr = self.attribute_memory_content(new_mem.content, persona_label, query)

            loc_old_m = re.search(r"\b(?:على|علي|في|فوق|تحت|جوه|داخل|برا|خارج|عند|جنب|بجانب)\s+[\w\s]+$", old_attr)
            loc_new_m = re.search(r"\b(?:على|علي|في|فوق|تحت|جوه|داخل|برا|خارج|عند|جنب|بجانب)\s+[\w\s]+$", new_attr)
            loc_old = loc_old_m.group(0).strip() if loc_old_m else old_attr
            loc_new = loc_new_m.group(0).strip() if loc_new_m else new_attr

            loc_old = re.sub(r'[.,،!\s]+$', '', loc_old)
            loc_new = re.sub(r'[.,،!\s]+$', '', loc_new)

            m_items = QueryDecomposer.extract_subject_items(new_mem.content, persona_label)
            overlap = query_items & m_items
            if overlap:
                item_name = list(overlap)[0]
            else:
                item_name = list(query_items)[0] if query_items else ""

            if item_name:
                if persona_label and persona_label not in item_name:
                    if item_name.startswith("ال") and len(item_name) > 3:
                        base = item_name[2:]
                        if base.endswith(('ه', 'ة')):
                            base = base[:-1] + 'ة'
                        entity_label = f"{base} {persona_label}"
                    else:
                        entity_label = f"{item_name} {persona_label}"
                else:
                    entity_label = item_name
                contrast_text = f"مكان {entity_label} السابق كان {loc_old}، وحالياً اتنقلت وبقت {loc_new}"
            else:
                contrast_text = f"المكان السابق كان {loc_old}، وحالياً اتنقلت وبقت {loc_new}"
            return [contrast_text]

        elif matching_active:
            new_mem = matching_active[0]
            effective_pid = new_mem.personality_id or personality_id
            persona_label = target_persona_name or (p_map.get(effective_pid) if effective_pid else "")
            new_attr = self.attribute_memory_content(new_mem.content, persona_label, query)
            return [f"{new_attr}، ومفيش مكان سابق متسجل ليها."]
        elif matching_inactive:
            old_mem = matching_inactive[0]
            effective_pid = old_mem.personality_id or personality_id
            persona_label = target_persona_name or (p_map.get(effective_pid) if effective_pid else "")
            old_attr = self.attribute_memory_content(old_mem.content, persona_label, query)
            return [f"مكان سابق مسجل: {old_attr}."]

        return []

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
