"""Test voice synthesis with user's cloned voice."""

import asyncio
import io
import math
import struct
import sys
import time
import wave
import httpx

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")

from app.main import app


async def main():
    test_phrase = "أهلاً بيكم، تم استنساخ صوتي بنجاح، والسيستم بيقبل واف وإم بي فور كمان!"
    print("=" * 65)
    print("🎙️ بدء اختبار استنساخ صوت المستخدم الحي...")
    print(f"النص المطلوب نطقه: \"{test_phrase}\"")
    print("=" * 65)

    t0 = time.time()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        res = await client.post(
            "/api/v1/voice-clone/synthesize",
            json={"text": test_phrase, "personality_id": 1},
        )
        t1 = time.time()
        elapsed = t1 - t0

        print(f"\n✅ الحالة: {res.status_code}")
        print(f"⚡ الوقت المستغرق: {elapsed:.2f} ثانية")
        print(f"📊 حجم ملف الصوت: {len(res.content):,} بايت")

        if res.status_code == 200:
            out_file = "user_voice_clone_test.wav"
            with open(out_file, "wb") as f:
                f.write(res.content)
            print(f"💾 تم حفظ الملف الصوتي بنجاح: {out_file}")

            with wave.open(io.BytesIO(res.content)) as wf:
                dur = wf.getnframes() / wf.getframerate()
                frames = wf.readframes(wf.getnframes())
                samples = struct.unpack(f"<{len(frames)//2}h", frames)
                rms = math.sqrt(sum(s**2 for s in samples) / len(samples))
                peak = max(abs(s) for s in samples)

            print(f"🔊 مدة الصوت الناتج: {dur:.2f} ثانية")
            print(f"📈 أقصى سعة للصوت: {peak}")
            print(f"📉 متوسط طاقة الصوت (RMS): {rms:.1f}")
            try:
                import os
                os.startfile(out_file)
            except Exception:
                pass
        else:
            print("❌ خطأ:", res.text)


if __name__ == "__main__":
    asyncio.run(main())
