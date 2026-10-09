"""
RAG Memory Service — retrieves relevant memories to ground LLM responses.

Architecture (doc §1 RAG, §6 personality & memory):
  1. Memories stored in SQL with pre-computed embedding vectors
  2. On each query: embed the transcript, cosine-search the memory store
  3. Top-K memories injected into LLM context
  4. Robot's responses feel personal and contextually aware
"""

import asyncio
from datetime import datetime
from typing import List

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import AsyncSessionLocal
from app.models.memory import Memory

logger = get_logger(__name__)


class RAGService:
    """
    Embedding-based memory retrieval.
    Lazy-loads the embedding model on first use.
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
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore[import]
            self._embedder = SentenceTransformer(
                settings.EMBEDDING_MODEL,
                device=settings.EMBEDDING_DEVICE,
            )
            logger.info(f"Embedding model loaded: {settings.EMBEDDING_MODEL}")
        except ImportError:
            logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
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
        Returns an empty list if the embedder isn't available.
        """
        await self._ensure_embedder()
        if self._embedder == "disabled":
            return []

        top_k = top_k or settings.MEMORY_TOP_K

        # Embed the query
        loop = asyncio.get_event_loop()
        query_vec = await loop.run_in_executor(None, self._embed, query)

        # Load all memories from DB
        async with AsyncSessionLocal() as session:
            stmt = select(Memory)
            if personality_id is not None:
                stmt = stmt.where(Memory.personality_id == personality_id)
            result = await session.execute(stmt)
            memories: list[Memory] = list(result.scalars().all())

        if not memories:
            return []

        # Score each memory
        scored: list[tuple[float, Memory]] = []
        for mem in memories:
            if mem.embedding:
                mem_vec = np.frombuffer(mem.embedding, dtype=np.float32)
                score = float(np.dot(query_vec, mem_vec) /
                              (np.linalg.norm(query_vec) * np.linalg.norm(mem_vec) + 1e-9))
                scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        # Update last_accessed timestamp async (fire and forget)
        if top:
            asyncio.create_task(self._update_access_times([m.id for _, m in top]))

        return [m.content for _, m in top]

    async def add_memory(
        self,
        content: str,
        personality_id: int,
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
            loop = asyncio.get_event_loop()
            vec = await loop.run_in_executor(None, self._embed, content)
            embedding_bytes = vec.astype(np.float32).tobytes()

        async with AsyncSessionLocal() as session:
            mem = Memory(
                content=content,
                personality_id=personality_id,
                embedding=embedding_bytes,
                source=source,
                importance=importance,
            )
            session.add(mem)
            await session.commit()
            await session.refresh(mem)
            logger.info(f"Memory {mem.id} added for personality {personality_id}")
            return mem.id

    # ── Internals ─────────────────────────────────────────────────────────────

    def _embed(self, text: str) -> np.ndarray:
        return self._embedder.encode(text, normalize_embeddings=True)

    async def _update_access_times(self, memory_ids: list[int]) -> None:
        async with AsyncSessionLocal() as session:
            for mid in memory_ids:
                mem = await session.get(Memory, mid)
                if mem:
                    mem.last_accessed = datetime.utcnow()
            await session.commit()
