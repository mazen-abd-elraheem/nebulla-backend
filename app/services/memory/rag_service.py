"""
RAG Memory Service — retrieves relevant memories to ground LLM responses.

Architecture (doc §1 RAG, §6 personality & memory):
  1. Memories stored in SQL with pre-computed embedding vectors
  2. On each query: embed the transcript, cosine-search the memory store
  3. Top-K memories injected into LLM context
  4. Robot's responses feel personal and contextually aware
"""

import asyncio
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone
from typing import List, Optional, Set, Tuple

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

logger = get_logger(__name__)


class RAGService:
    """
    Embedding-based memory retrieval.
    Pre-warms/caches the embedding model in memory, with lexical search if unavailable.
    """

    _shared_embedder = None
    _thread_lock = threading.Lock()
    _shared_cache: dict = {}

    def __init__(self):
        self._embedder = RAGService._shared_embedder

    async def _ensure_embedder(self):
        if RAGService._shared_embedder is not None:
            self._embedder = RAGService._shared_embedder
            return
        with RAGService._thread_lock:
            if RAGService._shared_embedder is None:
                self._load_embedder()
            self._embedder = RAGService._shared_embedder

    def _load_embedder(self):
        if np is None:
            logger.warning("numpy is not installed. RAG will use keyword/lexical search.")
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

            # If not cached locally, use instant high-speed lexical & keyword matching
            logger.info("Embedding model weights not in local cache; RAG using instant keyword & BM25 search.")
            RAGService._shared_embedder = "disabled"
            self._embedder = "disabled"
        except Exception as e:
            logger.warning(f"Could not initialize SentenceTransformer ({e}). Using keyword search.")
            RAGService._shared_embedder = "disabled"
            self._embedder = "disabled"

    def _load_memories_sync(self, personality_id: int | None = None) -> list[Memory]:
        """Load memories synchronously via sqlite3 for instant, non-blocking execution when db is None."""
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

    # ── Public API ────────────────────────────────────────────────────────────

    async def _get_scored_memories(
        self,
        query: str,
        personality_id: int | None = None,
        db: AsyncSession | None = None,
        person_name: str | None = None,
    ) -> list[tuple[float, Memory]]:
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

        # ── Hybrid Retrieval: Dense Embedding + Egyptian Lexical RRF ──────────
        sem_scores: dict[int, float] = {}
        lex_scores: dict[int, float] = {}

        clean_person = person_name.strip() if person_name else None
        augmented_query = f"{clean_person} {query}" if clean_person and clean_person not in query else query

        # 1. Fast Vectorized Semantic Scoring (when SentenceTransformer is active)
        if self._embedder != "disabled":
            try:
                embed_text = augmented_query if clean_person else query
                query_vec = self._embed(embed_text)

                valid_mems = [m for m in memories if m.embedding]
                if valid_mems and query_vec is not None and np is not None:
                    mem_matrix = np.vstack([np.frombuffer(m.embedding, dtype=np.float32) for m in valid_mems])
                    dot_sims = np.dot(mem_matrix, query_vec)
                    for m, sim_val in zip(valid_mems, dot_sims):
                        cos_sim = float(sim_val)
                        if cos_sim >= 0.25:
                            sem_scores[m.id] = cos_sim
            except Exception as e:
                logger.error(f"Error during semantic embedding search: {e}. Using lexical search.")

        # 2. Egyptian Lexical & Keyword Matching (Topic-Focused)
        for mem in memories:
            l_score = self._lexical_score(query, mem.content)
            if augmented_query != query:
                l_score = max(l_score, self._lexical_score(augmented_query, mem.content))

            # Only boost person_name if there is already topical overlap to prevent irrelevant memory pollution
            if clean_person and clean_person.lower() in mem.content.lower():
                if l_score > 0.05 or sem_scores.get(mem.id, 0.0) >= 0.25:
                    l_score += 0.15

            if l_score >= 0.06:
                lex_scores[mem.id] = l_score

        # 3. Reciprocal Rank Fusion (RRF) with Balanced Scoring
        sorted_sem = sorted(sem_scores.items(), key=lambda x: x[1], reverse=True)
        sem_ranks = {mid: rank for rank, (mid, _) in enumerate(sorted_sem, start=1)}

        sorted_lex = sorted(lex_scores.items(), key=lambda x: x[1], reverse=True)
        lex_ranks = {mid: rank for rank, (mid, _) in enumerate(sorted_lex, start=1)}

        all_matched_ids = set(sem_scores.keys()).union(set(lex_scores.keys()))
        mem_by_id = {m.id: m for m in memories}

        scored: list[tuple[float, Memory]] = []
        k_rrf = 60.0

        for mid in all_matched_ids:
            mem = mem_by_id[mid]
            score_rrf = 0.0
            if mid in sem_ranks:
                score_rrf += 1.0 / (k_rrf + sem_ranks[mid])
            if mid in lex_ranks:
                score_rrf += 1.0 / (k_rrf + lex_ranks[mid])

            raw_sem = sem_scores.get(mid, 0.0)
            raw_lex = lex_scores.get(mid, 0.0)

            importance_boost = (getattr(mem, "importance", 5) / 10.0) * 0.03
            combined_score = (score_rrf * 10.0) + (raw_sem * 0.6) + (raw_lex * 0.5) + importance_boost

            if raw_lex >= 0.06 or raw_sem >= 0.25 or combined_score >= 0.12:
                scored.append((combined_score, mem))

        # Additional fallback lexical pass if no memories scored yet
        if not scored:
            for mem in memories:
                score = self._lexical_score(query, mem.content)
                if augmented_query != query:
                    score = max(score, self._lexical_score(augmented_query, mem.content))
                if score > 0.0:
                    scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    def _normalize_for_dedup(self, text: str) -> str:
        """Normalized string for deduplicating repeated memory contents."""
        norm = self._normalize_arabic(text)
        norm = norm.replace("نيبيولا", "نيبولا").replace("nebula", "نيبولا")
        return re.sub(r"\s+", " ", norm).strip()

    async def retrieve(
        self,
        query: str,
        personality_id: int | None = None,
        top_k: int | None = None,
        db: AsyncSession | None = None,
        person_name: str | None = None,
    ) -> list[str]:
        """
        Return the top-K most relevant distinct memory texts for *query*.
        Uses hybrid search (semantic cosine similarity + lexical Arabic keyword match + importance).
        Deduplicates memory content before taking top-K to ensure diverse, non-redundant results.
        """
        scored = await self._get_scored_memories(query, personality_id, db, person_name=person_name)
        if not scored:
            return []

        top_k = top_k or settings.MEMORY_TOP_K
        seen_contents: set[str] = set()
        unique_top: list[Memory] = []

        # Deduplicate BEFORE cutting off at top_k so duplicate rows in DB don't starve out other memories
        for score, mem in scored:
            norm_content = self._normalize_for_dedup(mem.content)
            if norm_content not in seen_contents:
                seen_contents.add(norm_content)
                unique_top.append(mem)
                if len(unique_top) >= top_k:
                    break

        if unique_top:
            self._update_access_times_sync([m.id for m in unique_top])

        return [m.content for m in unique_top]

    async def retrieve_detailed(
        self,
        query: str,
        personality_id: int | None = None,
        top_k: int | None = None,
        db: AsyncSession | None = None,
        person_name: str | None = None,
    ) -> list[dict]:
        """Return top-K relevant distinct memories with scores and metadata."""
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
            self._update_access_times_sync([m.id for _, m in unique_scored])

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

    def format_rag_prompt(
        self,
        query: str,
        memories: list[str],
        instructions: str | None = None,
        person_name: str | None = None,
        robot_name: str = "نيبولا",
    ) -> str:
        """
        Builds a clean, optimized textual Prompt (NOT JSON) combining:
        1. Instructions from control DB / Personality directives.
        2. Verified RAG Context & personalized memories (e.g. from Face Recognition).
        3. Clear operational directives (Egyptian dialect, conciseness, zero hallucination).
        4. User query.
        """
        prompt_parts: list[str] = []

        # 1. System Persona & Core Instructions
        base_inst = instructions or f"أنت '{robot_name}'، توأم رقمي مصري ذكي وودود."
        prompt_parts.append(base_inst.strip())

        # 2. Operational Directives
        prompt_parts.append(
            "\n[توجيهات التشغيل والرد]:\n"
            "- أجب حصراً بلهجة مصرية قاهرية طبيعية ومهذبة ومباشرة (جملة أو جملتين كحد أقصى).\n"
            "- اعتمد بدقة وحصرياً على حقائق الذاكرة المسترجعة أدناه لتجنب أي هلوسة.\n"
            "- اختم ردك دائماً وبشكل إلزامي بوسم مشاعر مناسب في النهاية مثل: [happy] أو [wave] أو [like]."
        )

        # 3. Personalized Context from Face Recognition
        if person_name and person_name.strip():
            prompt_parts.append(
                f"\n[بيانات الشخص الحاضر / التعرف على الوجه]:\n"
                f"الشخص الذي تتحدث معه الآن هو: {person_name.strip()}."
            )

        # 4. Verified RAG Context (Textual prompt bullets, NOT JSON)
        if memories:
            mem_bullets = "\n".join(f"• {m.strip()}" for m in memories if m.strip())
            prompt_parts.append(
                f"\n--- [سياق الذاكرة المسترجع (Verified RAG Context)] ---\n"
                f"{mem_bullets}\n"
                f"--------------------------------------------------"
            )
        else:
            prompt_parts.append(
                "\n--- [سياق الذاكرة المسترجع (Verified RAG Context)] ---\n"
                "لا توجد معلومات مسجلة في الذاكرة بخصوص هذا الاستفسار.\n"
                "تنبيه: إذا كان السؤال يتطلب معلومة شخصية غير مسجلة، وضح بأدب أن المعلومة غير مسجلة حالياً.\n"
                "--------------------------------------------------"
            )

        # 5. User Query
        prompt_parts.append(f"\n[سؤال المستخدم]:\n{query.strip()}\n\n[الرد]:")

        return "\n".join(prompt_parts)

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
        Add a new memory and pre-compute its embedding if SentenceTransformer is enabled.
        Returns the new memory ID.
        """
        await self._ensure_embedder()

        embedding_bytes: bytes | None = None
        if self._embedder != "disabled" and np is not None:
            try:
                vec = self._embed(content)
                if vec is not None:
                    embedding_bytes = vec.astype(np.float32).tobytes()
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
        if text in RAGService._shared_cache:
            return RAGService._shared_cache[text]
        vec = self._embedder.encode(text, normalize_embeddings=True)
        if len(RAGService._shared_cache) > 2048:
            RAGService._shared_cache.clear()
        RAGService._shared_cache[text] = vec
        return vec

    def _normalize_arabic(self, text: str) -> str:
        from app.utils.masri_normalizer import normalize_masri_orthography
        return normalize_masri_orthography(text)

    def _tokenize(self, text: str) -> set[str]:
        if not text:
            return set()
        stopwords = {
            "في", "من", "على", "الى", "إلى", "عن", "مع", "هذا", "هذه", "ذلك", "تلك",
            "هو", "هي", "هم", "هن", "انتم", "نحن",
            "ان", "أن", "انها", "انه", "كان", "كانت", "يكون", "تكون",
            "ما", "ماذا", "متى", "اين", "أين", "كيف", "كم", "هل", "لماذا", "ايه", "إيه",
            "التي", "الذي", "الذين", "اللاتي", "كل", "بعض", "غير", "حيث", "ثم", "او", "أو"
        }
        norm = self._normalize_arabic(text)
        norm = norm.replace("نيبيولا", "نيبولا").replace("nebula", "نيبولا")
        raw_tokens = re.findall(r"\w+", norm)
        tokens = set()
        for t in raw_tokens:
            if t in stopwords:
                continue
            tokens.add(t)
            # Prefix stemming (ال, و, ب, ل, ف, ك)
            if len(t) > 3 and t.startswith("ال"):
                tokens.add(t[2:])
            if len(t) > 3 and t.startswith("و"):
                tokens.add(t[1:])
            if len(t) > 3 and t.startswith("ب"):
                tokens.add(t[1:])
            if len(t) > 3 and t.startswith("ل"):
                tokens.add(t[1:])
            if len(t) > 3 and t.startswith("ف"):
                tokens.add(t[1:])
            # Suffix stemming (ات, ين, ون, ان, ية, ك, ي, نا, ها, هم, كم)
            if len(t) > 4 and t.endswith("ات"):
                tokens.add(t[:-2])
            if len(t) > 4 and t.endswith("ين"):
                tokens.add(t[:-2])
            if len(t) > 4 and t.endswith("ون"):
                tokens.add(t[:-2])
            if len(t) > 4 and t.endswith("ية"):
                tokens.add(t[:-2])
            if len(t) > 4 and t.endswith("ان"):
                tokens.add(t[:-2])
            if len(t) > 3 and t.endswith("ك"):
                tokens.add(t[:-1])
            if len(t) > 3 and t.endswith("ي"):
                tokens.add(t[:-1])
            if len(t) > 4 and t.endswith("نا"):
                tokens.add(t[:-2])
            if len(t) > 4 and t.endswith("ها"):
                tokens.add(t[:-2])
            if len(t) > 4 and t.endswith("هم"):
                tokens.add(t[:-2])
            if len(t) > 4 and t.endswith("كم"):
                tokens.add(t[:-2])

        # Query Intent / Identity expansions for natural questions
        if "مين" in raw_tokens or "انت" in raw_tokens:
            tokens.add("اسم")
            tokens.add("روبوت")
            tokens.add("نيبولا")
        return tokens

    def _lexical_score(self, query: str, document: str) -> float:
        """
        Token-overlap lexical scoring with Arabic morphology, prefix stripping,
        and stopword filtering for high-precision retrieval.
        """
        if not document:
            return 0.0
        q_tokens = self._tokenize(query)
        d_tokens = self._tokenize(document)
        if not q_tokens or not d_tokens:
            return 0.0
        overlap = q_tokens.intersection(d_tokens)
        if not overlap:
            return 0.0
        jaccard = len(overlap) / len(q_tokens.union(d_tokens))
        coverage = len(overlap) / len(q_tokens)
        return float(jaccard * 0.4 + coverage * 0.6)

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
