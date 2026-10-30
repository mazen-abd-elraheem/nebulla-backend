"""
Unit tests for the Nebula Central Multithreading Subsystem.
"""

import asyncio
import threading
import time
import pytest

from app.core.threading import (
    ThreadPoolManager,
    init_thread_pools,
    shutdown_thread_pools,
    run_in_vision_thread,
    run_in_audio_thread,
    run_in_rag_thread,
    run_in_io_thread,
    get_thread_stats,
)


@pytest.fixture(autouse=True)
def ensure_thread_pools():
    init_thread_pools(vision_workers=4, audio_workers=4, rag_workers=2, io_workers=4)
    yield


@pytest.mark.asyncio
async def test_thread_pool_initialization():
    stats = get_thread_stats()
    assert "pools" in stats
    assert stats["pools"]["vision"]["max_workers"] >= 2
    assert stats["pools"]["audio"]["max_workers"] >= 2
    assert stats["pools"]["rag"]["max_workers"] >= 1
    assert stats["pools"]["io"]["max_workers"] >= 2


@pytest.mark.asyncio
async def test_run_in_vision_thread():
    def compute(x: int, y: int) -> int:
        return x * y

    result = await run_in_vision_thread(compute, 6, 7)
    assert result == 42


@pytest.mark.asyncio
async def test_run_in_audio_thread():
    def audio_task(text: str) -> str:
        return f"synthesized:{text}"

    result = await run_in_audio_thread(audio_task, "مرحبا")
    assert result == "synthesized:مرحبا"


@pytest.mark.asyncio
async def test_run_in_rag_thread():
    def rag_task(data: list) -> int:
        return sum(data)

    result = await run_in_rag_thread(rag_task, [10, 20, 30])
    assert result == 60


@pytest.mark.asyncio
async def test_run_in_io_thread():
    def io_task(filename: str) -> str:
        return f"saved_{filename}"

    result = await run_in_io_thread(io_task, "audio.wav")
    assert result == "saved_audio.wav"


@pytest.mark.asyncio
async def test_parallel_execution_across_threads():
    """Verify multiple concurrent calls execute on distinct threads in parallel."""
    def worker(delay: float) -> int:
        time.sleep(delay)
        return threading.get_ident()

    t0 = time.perf_counter()
    tasks = [run_in_vision_thread(worker, 0.1) for _ in range(4)]
    thread_ids = await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - t0

    # 4 tasks with 0.1s delay each in a 4-worker pool should complete in ~0.15s, not 0.4s
    assert elapsed < 0.35, f"Execution took {elapsed:.2f}s, expected parallel execution < 0.35s"
    # Should have executed across multiple distinct threads
    assert len(set(thread_ids)) > 1
