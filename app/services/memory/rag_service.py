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
            self._embedder = SentenceTransformer(
                settings.EMBEDDING_MODEL,
                device=settings.EMBEDDING_DEVICE,
            )
            logger.info(f"Embedding model loaded: {settings.EMBEDDING_MODEL}")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed. RAG will use keyword/lexical fallback. "
                "To enable semantic search: pip install sentence-transformers numpy"
            )
            self._embedder = "disabled"
        except Exception as e:
            logger.warning(
                f"Failed to load embedding model ({e}). RAG will use keyword/lexical fallback."
            )
            self._embedder = "disabled"

    # ── Public API ────────────────────────────────────────────────────────────

    async def retrieve(
        self,
        query: str,
        personality_id: int | None = None,
        top_k: int | None = None,
    ) -> list[str]:
        """
        Return the top-K most relevant memory texts for *query*.
        Uses semantic cosine similarity when embedding model is loaded,
        and falls back to lexical/keyword matching otherwise.
        """
        await self._ensure_embedder()
        top_k = top_k or settings.MEMORY_TOP_K

        if self._embedder == "disabled":
            # Fallback to lexical overlap and importance when sentence-transformers is absent
            async with AsyncSessionLocal() as session:
                stmt = select(Memory)
                if personality_id is not None:
                    stmt = stmt.where(Memory.personality_id == personality_id)
                result = await session.execute(stmt)
                memories: list[Memory] = list(result.scalars().all())

            if not memories:
                return []

            query_words = set(query.lower().split())
            scored = []
            for mem in memories:
                mem_words = set(mem.content.lower().split())
                overlap = len(query_words.intersection(mem_words))
                scored.append((overlap, mem))
            scored.sort(key=lambda x: (x[0], x[1].importance or 0.5), reverse=True)
            top = [m for score, m in scored if score > 0][:top_k]
            if not top and memories:
                memories.sort(key=lambda m: m.importance or 0.5, reverse=True)
                top = memories[:top_k]
            return [m.content for m in top]

        # Embed the query
        loop = asyncio.get_event_loop()
        query_vec = await loop.run_in_executor(None, self._embed, query)

        # Load all memories from DB
        async with AsyncSessionLocal() as session:
            stmt = select(Memory)
            if personality_id is not None:
                stmt = stmt.where(
                    or_(
                        Memory.personality_id == personality_id,
                        Memory.personality_id.is_(None),
                    )
                )
            result = await session.execute(stmt)
            memories: list[Memory] = list(result.scalars().all())

        if not memories:
            return []

        scored: list[tuple[float, Memory]] = []

        if self._embedder != "disabled":
            # Semantic search via cosine similarity
            loop = asyncio.get_event_loop()
            try:
                query_vec = await loop.run_in_executor(None, self._embed, query)
                for mem in memories:
                    if mem.embedding:
                        mem_vec = np.frombuffer(mem.embedding, dtype=np.float32)
                        norm_prod = (np.linalg.norm(query_vec) * np.linalg.norm(mem_vec)) + 1e-9
                        score = float(np.dot(query_vec, mem_vec) / norm_prod)
                        scored.append((score, mem))
                    else:
                        # Fallback for un-embedded row: lexical score
                        score = self._lexical_score(query, mem.content)
                        if score > 0:
                            scored.append((score * 0.5, mem))
            except Exception as e:
                logger.error(f"Error during semantic embedding search: {e}. Using lexical fallback.")
                scored = []

        # If semantic returned nothing or embedder is disabled, run lexical matching
        if not scored:
            for mem in memories:
                score = self._lexical_score(query, mem.content)
                if score > 0:
                    scored.append((score, mem))

        if not scored:
            return []

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        # Update last_accessed timestamp async (fire and forget)
        if top:
            asyncio.create_task(self._update_access_times([m.id for _, m in top]))

        return [
            {
                "id": m.id,
                "content": m.content,
                "score": round(score, 4),
                "source": m.source,
                "personality_id": m.personality_id,
            }
            for score, m in top
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
        text = re.sub(r"[إأآا]", "ا", text)
        text = re.sub(r"ى", "ي", text)
        text = re.sub(r"ة", "ه", text)
        text = re.sub(r"[\u064B-\u065F]", "", text)  # Tashkeel
        return text.lower()

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
                        mem.last_accessed = datetime.now(timezone.utc)
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to update memory last_accessed: {e}")
