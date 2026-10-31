import asyncio
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")

from app.providers.stt.factory import get_stt_provider

async def main():
    print("=" * 60)
    print("Testing STT Provider: whisper")
    print("=" * 60)

    stt = get_stt_provider("whisper")

    with open("data/voice_samples/personality_1_test_seg.wav", "rb") as f:
        audio_data = f.read()

    print(f"Read audio sample: {len(audio_data):,} bytes")
    t0 = time.time()
    text = await stt.transcribe(audio_data)
    elapsed = time.time() - t0

    print(f"\nTranscription Result ({elapsed:.2f}s):")
    print(f"'{text}'")
    print("=" * 60)

    # Second pass test to verify warm singleton caching speed
    print("\nSecond pass (warm cache):")
    t1 = time.time()
    text2 = await stt.transcribe(audio_data)
    elapsed2 = time.time() - t1
    print(f"Second pass time: {elapsed2:.2f}s")
    print(f"'{text2}'")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
