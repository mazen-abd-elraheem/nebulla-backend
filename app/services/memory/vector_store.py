"""
VectorStore — High-Performance In-Memory Vector Store for Database Memories.

Optimizes Database Vectors & Retrieval Performance:
- Stores L2-normalized float32 vectors in an aligned NumPy matrix for sub-millisecond dot products:
    cos_sim(u, v) = u_norm · v_norm
- Thread-safe in-memory cache synchronized with SQLite database.
- Metadata filtering (by personality_id, person_name, source).
- Automatically backfills missing embeddings in SQLite on startup.
- Strictly deterministic vector operations (NO fallback models).
"""

import asyncio
import os
import sqlite3
import threading
from typing import Dict, List, Optional, Set, Tuple, Any

import numpy as np
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.memory import Memory

logger = get_logger(__name__)


class DatabaseVectorStore:
    """
    In-Memory Vector Matrix Cache & SQLite Vector Manager.
    Avoids repeatedly decoding BLOBs from the database on every search query.
    """

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._lock = threading.Lock()
        self._matrix: Optional[np.ndarray] = None          # Shape: (N, D), float32, L2-normalized
        self._ids: List[int] = []                         # Corresponding Memory IDs
        self._memory_cache: Dict[int, Memory] = {}        # Cached Memory objects
        self._person_tags: Dict[int, Set[str]] = {}       # Mapped person names/tags per memory
        self._is_initialized = False

    @classmethod
    def get_instance(cls) -> "DatabaseVectorStore":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @staticmethod
    def _normalize(vec: np.ndarray) -> np.ndarray:
        """L2-normalize vector to unit length for direct cosine similarity via dot product."""
        norm = np.linalg.norm(vec)
        if norm > 1e-12:
            return vec / norm
        return vec

    def _extract_person_tags(self, text: str) -> Set[str]:
        """Extract mentioned person entities or names to index for metadata-filtered retrieval."""
        tags = set()
        clean = text.lower()
        common_names = ["مازن", "منه", "منة", "أحمد", "احمد", "سارة", "ساره", "محمد", "علي", "محمود"]
        for name in common_names:
            if name in clean:
                tags.add(name)
        return tags

    def load_from_db(self, memories: List[Memory], embedder: Any = None) -> None:
        """
        Builds the aligned in-memory vector matrix from SQLite memories.
        Optionally backfills missing embeddings if an active embedder is provided.
        """
        with self._lock:
            self._ids.clear()
            self._memory_cache.clear()
            self._person_tags.clear()

            vectors: List[np.ndarray] = []
            mems_needing_backfill: List[Memory] = []

            for mem in memories:
                self._memory_cache[mem.id] = mem
                self._person_tags[mem.id] = self._extract_person_tags(mem.content)

                if mem.embedding:
                    try:
                        arr = np.frombuffer(mem.embedding, dtype=np.float32)
                        if arr.size > 0:
                            vectors.append(self._normalize(arr))
                            self._ids.append(mem.id)
                            continue
                    except Exception as e:
                        logger.debug(f"Failed to decode embedding for memory {mem.id}: {e}")

                if embedder is not None and embedder != "disabled":
                    mems_needing_backfill.append(mem)

            # Auto-backfill missing embeddings in background if embedder available
            if mems_needing_backfill and embedder is not None and embedder != "disabled":
                logger.info(f"Auto-backfilling embeddings for {len(mems_needing_backfill)} memories...")
                for m in mems_needing_backfill:
                    try:
                        vec = embedder.encode(m.content, normalize_embeddings=True)
                        m.embedding = vec.astype(np.float32).tobytes()
                        vectors.append(self._normalize(vec.astype(np.float32)))
                        self._ids.append(m.id)
                        self._persist_embedding_sync(m.id, m.embedding)
                    except Exception as e:
                        logger.warning(f"Backfill failed for memory {m.id}: {e}")

            if vectors:
                self._matrix = np.vstack(vectors).astype(np.float32)
            else:
                self._matrix = None

            self._is_initialized = True
            logger.info(
                f"DatabaseVectorStore initialized with {len(self._ids)} indexed vectors "
                f"(Total memories cached: {len(self._memory_cache)})."
            )

    def _persist_embedding_sync(self, memory_id: int, embedding_bytes: bytes) -> None:
        """Persist generated embedding back to SQLite database."""
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)

        try:
            conn = sqlite3.connect(db_path, timeout=3.0)
            cursor = conn.cursor()
            cursor.execute("UPDATE memories SET embedding = ? WHERE id = ?", (embedding_bytes, memory_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.debug(f"Failed to persist backfilled embedding to SQLite: {e}")

    def add_or_update(self, memory: Memory, vec: Optional[np.ndarray] = None) -> None:
        """Thread-safe incremental addition or update of a single vector."""
        with self._lock:
            self._memory_cache[memory.id] = memory
            self._person_tags[memory.id] = self._extract_person_tags(memory.content)

            if vec is None and memory.embedding:
                try:
                    vec = np.frombuffer(memory.embedding, dtype=np.float32)
                except Exception:
                    vec = None

            if vec is not None:
                norm_vec = self._normalize(vec.astype(np.float32))

                if memory.id in self._ids:
                    idx = self._ids.index(memory.id)
                    if self._matrix is not None:
                        self._matrix[idx] = norm_vec
                else:
                    self._ids.append(memory.id)
                    if self._matrix is None:
                        self._matrix = norm_vec.reshape(1, -1)
                    else:
                        self._matrix = np.vstack([self._matrix, norm_vec])

    def delete(self, memory_id: int) -> None:
        """Remove a memory and its vector from the store."""
        with self._lock:
            self._memory_cache.pop(memory_id, None)
            self._person_tags.pop(memory_id, None)

            if memory_id in self._ids:
                idx = self._ids.index(memory_id)
                self._ids.pop(idx)
                if self._matrix is not None:
                    if len(self._ids) == 0:
                        self._matrix = None
                    else:
                        self._matrix = np.delete(self._matrix, idx, axis=0)

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = 10,
        personality_id: Optional[int] = None,
        person_name: Optional[str] = None,
        min_similarity: float = 0.20,
    ) -> List[Tuple[float, Memory]]:
        """
        Fast Matrix-Vector Cosine Similarity Search:
        Computes similarities in a single vector operation: S = M · q
        Applies optional personality and person entity metadata filtering.
        """
        with self._lock:
            if self._matrix is None or len(self._ids) == 0:
                return []

            # 1. Normalize query vector
            q_norm = self._normalize(query_vec.astype(np.float32))

            # 2. Fast Dot Product Matrix Multiply (Instantaneous cosine similarity)
            sims = np.dot(self._matrix, q_norm)

            results: List[Tuple[float, Memory]] = []
            clean_person = person_name.strip().lower() if person_name else None

            for idx, score in enumerate(sims):
                sim_val = float(score)
                if sim_val < min_similarity:
                    continue

                mid = self._ids[idx]
                mem = self._memory_cache.get(mid)
                if not mem:
                    continue

                # Filter by personality_id if specified
                if personality_id is not None:
                    if mem.personality_id is not None and mem.personality_id != personality_id:
                        continue

                # Boost or prioritize if matching person_name
                boost = 0.0
                if clean_person:
                    tags = self._person_tags.get(mid, set())
                    if clean_person in tags or clean_person in mem.content.lower():
                        boost = 0.15

                results.append((sim_val + boost, mem))

            results.sort(key=lambda x: x[0], reverse=True)
            return results[:top_k]

    def get_all_memories(self, personality_id: Optional[int] = None) -> List[Memory]:
        with self._lock:
            if personality_id is None:
                return list(self._memory_cache.values())
            return [
                m for m in self._memory_cache.values()
                if m.personality_id is None or m.personality_id == personality_id
            ]

