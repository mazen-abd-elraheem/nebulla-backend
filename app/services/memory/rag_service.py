"""
RAG Memory Service — retrieves relevant memories to ground LLM responses.

Architecture (doc §1 RAG, §6 personality & memory):
  1. Memories stored in SQL with pre-computed embedding vectors
  2. On each query: embed the transcript, cosine-search the memory store
  3. Top-K memories injected into LLM context
  4. Robot's responses feel personal and contextually aware
"""

import asyncio
import re
from datetime import datetime, timezone
from typing import List

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
    Lazy-loads the embedding model on first use, with lexical fallback if unavailable.
    """

    def __init__(self):
        self._embedder = None
        self._lock = asyncio.Lock()

    async def _ensure_embedder(self):
        if self._embedder is not None:
            return
        async with self._lock:
            if self._embedder is None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._load_embedder)

    def _load_embedder(self):
        if np is None:
            logger.warning("numpy is not installed. RAG will use keyword/lexical fallback.")
            self._embedder = "disabled"
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
            try:
                self._embedder = SentenceTransformer(
                    settings.EMBEDDING_MODEL,
                    device=settings.EMBEDDING_DEVICE,
                    local_files_only=True,
                )
                logger.info(f"Embedding model loaded from local cache: {settings.EMBEDDING_MODEL}")
                return
            except Exception:
                pass

            # If not cached locally, use instant high-speed lexical & keyword matching
            logger.info("Embedding model weights not in local cache; RAG using instant keyword & BM25 search.")
            self._embedder = "disabled"
        except Exception as e:
            logger.warning(f"Could not initialize SentenceTransformer ({e}). Using keyword search.")
            self._embedder = "disabled"

    # ── Public API ────────────────────────────────────────────────────────────

    async def _get_scored_memories(
        self,
        query: str,
        personality_id: int | None = None,
        db: AsyncSession | None = None,
    ) -> list[tuple[float, Memory]]:
        await self._ensure_embedder()

        # Load memories from DB with personality fallback
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
            async with AsyncSessionLocal() as session:
                stmt = select(Memory)
                if personality_id is not None:
                    stmt_p = stmt.where((Memory.personality_id == personality_id) | (Memory.personality_id.is_(None)))
                    res = await session.execute(stmt_p)
                    memories = list(res.scalars().all())
                    if not memories:
                        res_all = await session.execute(stmt)
                        memories = list(res_all.scalars().all())
                else:
                    res = await session.execute(stmt)
                    memories = list(res.scalars().all())

        if not memories:
            return []

        # ── Hybrid Retrieval: Dense Embedding + Egyptian Lexical RRF ──────────
        sem_scores: dict[int, float] = {}
        lex_scores: dict[int, float] = {}

        # 1. Dense Semantic Scoring
        if self._embedder != "disabled":
            loop = asyncio.get_event_loop()
            try:
                query_vec = await loop.run_in_executor(None, self._embed, query)
                for mem in memories:
                    if mem.embedding:
                        mem_vec = np.frombuffer(mem.embedding, dtype=np.float32)
                        norm_prod = (np.linalg.norm(query_vec) * np.linalg.norm(mem_vec)) + 1e-9
                        cos_sim = float(np.dot(query_vec, mem_vec) / norm_prod)
                        if cos_sim > 0.05:
                            sem_scores[mem.id] = cos_sim
            except Exception as e:
                logger.error(f"Error during semantic embedding search: {e}. Using lexical search.")

        # 2. Egyptian Lexical & Keyword Matching
        for mem in memories:
            l_score = self._lexical_score(query, mem.content)
            if l_score > 0.0:
                lex_scores[mem.id] = l_score

        # 3. Reciprocal Rank Fusion (RRF)
        # Sort each list to obtain ranks
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

            # Blend with raw semantic similarity and importance weight
            raw_sem = sem_scores.get(mid, 0.0)
            raw_lex = lex_scores.get(mid, 0.0)
            importance_boost = (getattr(mem, "importance", 5) / 10.0) * 0.05
            combined_score = (score_rrf * 10.0) + (raw_sem * 0.5) + (raw_lex * 0.3) + importance_boost
            scored.append((combined_score, mem))

        # Fallback if neither dense nor lexical matched anything
        if not scored:
            for mem in memories:
                score = self._lexical_score(query, mem.content)
                if score > 0:
                    scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored

    async def retrieve(
        self,
        query: str,
        personality_id: int | None = None,
        top_k: int | None = None,
        db: AsyncSession | None = None,
    ) -> list[str]:
        """
        Return the top-K most relevant memory texts for *query*.
        Uses hybrid search (semantic cosine similarity + lexical Arabic keyword match + importance).
        Falls back smoothly if embedder is unavailable.
        """
        scored = await self._get_scored_memories(query, personality_id, db)
        if not scored:
            return []

        top_k = top_k or settings.MEMORY_TOP_K
        top = [mem for score, mem in scored if score >= 0.12][:top_k]
        if top:
            asyncio.create_task(self._update_access_times([m.id for m in top]))

        unique_contents = []
        for m in top:
            if m.content not in unique_contents:
                unique_contents.append(m.content)

        return unique_contents

    async def retrieve_detailed(
        self,
        query: str,
        personality_id: int | None = None,
        top_k: int | None = None,
        db: AsyncSession | None = None,
    ) -> list[dict]:
        """Return top-K relevant memories with scores and metadata."""
        scored = await self._get_scored_memories(query, personality_id, db)
        if not scored:
            return []

        top_k = top_k or settings.MEMORY_TOP_K
        top_scored = [(score, mem) for score, mem in scored if score >= 0.12][:top_k]
        if top_scored:
            asyncio.create_task(self._update_access_times([m.id for _, m in top_scored]))

        return [
            {
                "id": m.id,
                "content": m.content,
                "score": round(score, 4),
                "source": m.source,
                "personality_id": m.personality_id,
            }
            for score, m in top_scored
        ]

    async def add_memory(
        self,
        content: str,
        personality_id: int | None = None,
        source: str = "conversation",
        importance: int = 5,
    ) -> int:
        """
        Add a new memory and pre-compute its embedding.
        Returns the new memory ID.
        """
        await self._ensure_embedder()

        embedding_bytes: bytes | None = None
        if self._embedder != "disabled":
            try:
                loop = asyncio.get_event_loop()
                vec = await loop.run_in_executor(None, self._embed, content)
                embedding_bytes = vec.astype(np.float32).tobytes()
            except Exception as e:
                logger.warning(f"Could not generate embedding for new memory: {e}")

        async with AsyncSessionLocal() as session:
            mem = Memory(
                content=content.strip(),
                personality_id=personality_id,
                embedding=embedding_bytes,
                source=source,
                importance=importance,
            )
            session.add(mem)
            await session.commit()
            await session.refresh(mem)
            logger.info(f"Memory {mem.id} added (personality: {personality_id})")
            return mem.id

    # ── Internals ─────────────────────────────────────────────────────────────

    def _embed(self, text: str):
        return self._embedder.encode(text, normalize_embeddings=True)

    def _normalize_arabic(self, text: str) -> str:
        from app.utils.masri_normalizer import normalize_masri_orthography
        return normalize_masri_orthography(text)

    def _tokenize(self, text: str) -> set[str]:
        if not text:
            return set()
        stopwords = {
            "في", "من", "على", "الى", "إلى", "عن", "مع", "هذا", "هذه", "ذلك", "تلك",
            "هو", "هي", "هم", "هن", "انت", "انتم", "انا", "نحن",
            "ان", "أن", "انها", "انه", "كان", "كانت", "يكون", "تكون",
            "ما", "ماذا", "متى", "اين", "أين", "كيف", "كم", "هل", "لماذا", "ايه", "إيه",
            "التي", "الذي", "الذين", "اللاتي", "كل", "بعض", "غير", "حيث", "ثم", "او", "أو"
        }
        norm = self._normalize_arabic(text)
        raw_tokens = re.findall(r"\w+", norm)
        tokens = set()
        for t in raw_tokens:
            if t in stopwords:
                continue
            tokens.add(t)
            # Prefix stemming (ال, و, ب, ل)
            if len(t) > 3 and t.startswith("ال"):
                tokens.add(t[2:])
            if len(t) > 3 and t.startswith("و"):
                tokens.add(t[1:])
            if len(t) > 3 and t.startswith("ب"):
                tokens.add(t[1:])
            # Suffix stemming (ات, ين, ون, ه, ها)
            if len(t) > 4 and t.endswith("ات"):
                tokens.add(t[:-2])
            if len(t) > 4 and t.endswith("ين"):
                tokens.add(t[:-2])
            if len(t) > 4 and t.endswith("ون"):
                tokens.add(t[:-2])
        return tokens

    def _lexical_score(self, query: str, document: str) -> float:
        """
        Token-overlap lexical scoring with Arabic morphology, prefix stripping,
        and stopword filtering for high-precision fallback.
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

    async def _update_access_times(self, memory_ids: list[int]) -> None:
        try:
            async with AsyncSessionLocal() as session:
                for mid in memory_ids:
                    mem = await session.get(Memory, mid)
                    if mem:
                        mem.last_accessed = datetime.utcnow()
                await session.commit()
        except Exception as e:
            logger.debug(f"Could not update last_accessed: {e}")

    async def _backfill_embeddings(self, items: list[tuple[int, str]]) -> None:
        """Asynchronously compute and store embeddings for memories missing them."""
        try:
            loop = asyncio.get_event_loop()
            async with AsyncSessionLocal() as session:
                for mid, text in items[:10]:
                    try:
                        vec = await loop.run_in_executor(None, self._embed, text)
                        mem = await session.get(Memory, mid)
                        if mem and not mem.embedding:
                            mem.embedding = vec.astype(np.float32).tobytes()
                    except Exception:
                        continue
                await session.commit()
                logger.info(f"Backfilled embeddings for {len(items[:10])} memories")
        except Exception as e:
            logger.warning(f"Could not backfill embeddings: {e}")

