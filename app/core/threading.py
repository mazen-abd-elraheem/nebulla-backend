"""
Nebula Backend — Central Multithreading & Thread Pool Management.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Provides isolated, dedicated ThreadPoolExecutors for each workload domain:
  1. Vision Pool   — Computer Vision (UniFace, OpenCV, face detection, video frames)
  2. Audio Pool    — Speech & Audio (STT inference, TTS synthesis, voice cloning)
  3. RAG Pool      — Semantic embeddings (SentenceTransformers, vector math)
  4. I/O Pool      — File conversions, FFmpeg subprocesses, disk writes

Isolating thread pools prevents heavy tasks (like video frame extraction or TTS)
from starving real-time tasks (like camera gaze tracking or WebSocket communication).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import functools
import os
import threading
from typing import Any, Callable, Dict, Optional, TypeVar

from app.core.logger import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class ThreadPoolManager:
    """
    Singleton manager for domain-isolated ThreadPoolExecutors.
    """

    _instance: Optional["ThreadPoolManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        # Determine CPU capacity
        cpu_count = os.cpu_count() or 4

        # Configure worker counts per domain
        # Minimum 2 threads to prevent head-of-line blocking
        self.vision_workers = max(2, min(cpu_count, 8))
        self.audio_workers = max(2, min(cpu_count, 6))
        self.rag_workers = max(1, min(cpu_count // 2 or 1, 4))
        self.io_workers = max(2, min(cpu_count, 8))

        self.vision_pool: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self.audio_pool: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self.rag_pool: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self.io_pool: Optional[concurrent.futures.ThreadPoolExecutor] = None

        self._initialized = False

    @classmethod
    def get_instance(cls) -> "ThreadPoolManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def initialize(
        self,
        vision_workers: Optional[int] = None,
        audio_workers: Optional[int] = None,
        rag_workers: Optional[int] = None,
        io_workers: Optional[int] = None,
    ) -> None:
        """Initialize all thread pools with configured worker counts."""
        if self._initialized:
            return

        if vision_workers:
            self.vision_workers = vision_workers
        if audio_workers:
            self.audio_workers = audio_workers
        if rag_workers:
            self.rag_workers = rag_workers
        if io_workers:
            self.io_workers = io_workers

        self.vision_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.vision_workers,
            thread_name_prefix="nebula-vision",
        )
        self.audio_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.audio_workers,
            thread_name_prefix="nebula-audio",
        )
        self.rag_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.rag_workers,
            thread_name_prefix="nebula-rag",
        )
        self.io_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.io_workers,
            thread_name_prefix="nebula-io",
        )

        self._initialized = True
        logger.info(
            f"🚀 ThreadPoolManager initialized with isolated pools: "
            f"Vision={self.vision_workers}, Audio={self.audio_workers}, "
            f"RAG={self.rag_workers}, I/O={self.io_workers} (Total Workers: "
            f"{self.vision_workers + self.audio_workers + self.rag_workers + self.io_workers})"
        )

    def shutdown(self, wait: bool = True) -> None:
        """Gracefully shut down all thread pools."""
        pools = [
            ("Vision", self.vision_pool),
            ("Audio", self.audio_pool),
            ("RAG", self.rag_pool),
            ("I/O", self.io_pool),
        ]
        for name, pool in pools:
            if pool is not None:
                try:
                    pool.shutdown(wait=wait, cancel_futures=True)
                    logger.info(f"ThreadPool [{name}] shut down.")
                except Exception as e:
                    logger.warning(f"Error shutting down ThreadPool [{name}]: {e}")

        self.vision_pool = None
        self.audio_pool = None
        self.rag_pool = None
        self.io_pool = None
        self._initialized = False

    def get_stats(self) -> Dict[str, Any]:
        """Return diagnostic metrics about all thread pools."""
        def _pool_info(pool: Optional[concurrent.futures.ThreadPoolExecutor], configured: int) -> Dict[str, Any]:
            if pool is None:
                return {"status": "inactive", "max_workers": configured}
            return {
                "status": "active",
                "max_workers": pool._max_workers,
                "active_threads": len(getattr(pool, "_threads", set())),
            }

        return {
            "total_process_threads": threading.active_count(),
            "cpu_cores": os.cpu_count(),
            "pools": {
                "vision": _pool_info(self.vision_pool, self.vision_workers),
                "audio": _pool_info(self.audio_pool, self.audio_workers),
                "rag": _pool_info(self.rag_pool, self.rag_workers),
                "io": _pool_info(self.io_pool, self.io_workers),
            },
        }


# Global thread manager instance
manager = ThreadPoolManager.get_instance()


def init_thread_pools(
    vision_workers: Optional[int] = None,
    audio_workers: Optional[int] = None,
    rag_workers: Optional[int] = None,
    io_workers: Optional[int] = None,
) -> None:
    """Initialize thread pools (called during FastAPI startup)."""
    manager.initialize(
        vision_workers=vision_workers,
        audio_workers=audio_workers,
        rag_workers=rag_workers,
        io_workers=io_workers,
    )


def shutdown_thread_pools(wait: bool = True) -> None:
    """Shut down thread pools (called during FastAPI shutdown)."""
    manager.shutdown(wait=wait)


# ─────────────────────────────────────────────────────────────────────────────
# Async Helper Wrappers for offloading work to dedicated thread pools
# ─────────────────────────────────────────────────────────────────────────────

async def run_in_vision_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute CPU-bound or GPU-bound Vision tasks on the dedicated vision thread pool."""
    if not manager._initialized or manager.vision_pool is None:
        manager.initialize()
    loop = asyncio.get_running_loop()
    if kwargs:
        call = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(manager.vision_pool, call)
    return await loop.run_in_executor(manager.vision_pool, func, *args)


async def run_in_audio_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute heavy STT/TTS audio synthesis tasks on the dedicated audio thread pool."""
    if not manager._initialized or manager.audio_pool is None:
        manager.initialize()
    loop = asyncio.get_running_loop()
    if kwargs:
        call = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(manager.audio_pool, call)
    return await loop.run_in_executor(manager.audio_pool, func, *args)


async def run_in_rag_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute embedding and semantic search computations on the dedicated RAG thread pool."""
    if not manager._initialized or manager.rag_pool is None:
        manager.initialize()
    loop = asyncio.get_running_loop()
    if kwargs:
        call = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(manager.rag_pool, call)
    return await loop.run_in_executor(manager.rag_pool, func, *args)


async def run_in_io_thread(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Execute blocking I/O, FFmpeg conversions, or disk operations on the dedicated I/O thread pool."""
    if not manager._initialized or manager.io_pool is None:
        manager.initialize()
    loop = asyncio.get_running_loop()
    if kwargs:
        call = functools.partial(func, *args, **kwargs)
        return await loop.run_in_executor(manager.io_pool, call)
    return await loop.run_in_executor(manager.io_pool, func, *args)


def get_thread_stats() -> Dict[str, Any]:
    """Retrieve current thread pool and system threading statistics."""
    return manager.get_stats()

