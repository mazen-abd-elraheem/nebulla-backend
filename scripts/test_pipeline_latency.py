"""
Verification test for low-latency multithreaded AIPipeline and Egyptian Arabic Fast-Path.
"""

import asyncio
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.ai.pipeline import AIPipeline, EgyptianFastPathCache

async def test_fast_path():
    print("=== Testing Egyptian Fast-Path Cache ===")
    queries = [
        "صباح الخير",
        "مساء الفل",
        "أهلاً وسهلاً",
        "إزيك عامل إيه",
        "إنت مين",
        "مين صممك وطورك",
        "شكراً جزيلاً",
    ]

    for q in queries:
        t0 = time.perf_counter()
        match = EgyptianFastPathCache.match(q, personality_id=1)
        dur_ms = (time.perf_counter() - t0) * 1000
        print(f"Query: '{q}'")
        print(f"Latency: {dur_ms:.3f} ms")
        if match:
            resp, emotion = match
            print(f"Response ({emotion}): {resp}")
        else:
            print("NO MATCH")
        print("-" * 50)

async def test_pipeline_process_text():
    print("\n=== Testing AIPipeline process_text ===")
    pipe = AIPipeline()
    
    # 1. Fast-path greeting
    t0 = time.perf_counter()
    res1 = await pipe.process_text("صباح الخير يا نيبولا", broadcast_to_clients=False)
    dur1 = (time.perf_counter() - t0) * 1000
    print(f"Fast-path turn latency: {dur1:.2f} ms")
    print(f"Result 1: {res1.get('response')}\n")

    # 2. Fast-path identity
    t0 = time.perf_counter()
    res2 = await pipe.process_text("إنت مين بالظبط؟", broadcast_to_clients=False)
    dur2 = (time.perf_counter() - t0) * 1000
    print(f"Fast-path turn latency: {dur2:.2f} ms")
    print(f"Result 2: {res2.get('response')}\n")

if __name__ == "__main__":
    asyncio.run(test_fast_path())
    asyncio.run(test_pipeline_process_text())
