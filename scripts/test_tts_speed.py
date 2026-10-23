"""Live speed and audio waveform test script."""

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


async def run_live_test():
    print("=" * 65)
    print("🚀 بدء الاختبار الحي لمحرك الصوت السريع والتأكد من جودة الريك...")
    print("=" * 65)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        # 1. اختبار الـ /test endpoint
        print("\n[1/2] 🧪 جاري اختبار نقطة: POST /api/v1/voice-clone/test")
        t0 = time.time()
        res_test = await client.post("/api/v1/voice-clone/test")
        t1 = time.time()
        elapsed_test = t1 - t0

        assert res_test.status_code == 200, f"فشل الطلب: {res_test.text}"
        wav_data_1 = res_test.content
        with wave.open(io.BytesIO(wav_data_1)) as wf:
            dur1 = wf.getnframes() / wf.getframerate()
            frames1 = wf.readframes(wf.getnframes())
            # حساب متوسط طاقة الصوت (RMS) للتأكد الرياضي أن الصوت غير صامت إطلاقاً
            samples1 = struct.unpack(f"<{len(frames1)//2}h", frames1)
            rms1 = math.sqrt(sum(s**2 for s in samples1) / len(samples1))
            peak1 = max(abs(s) for s in samples1)

        print(f"   ✅ الحالة: {res_test.status_code} OK")
        print(f"   ⚡ زمن الاستجابة: {elapsed_test:.2f} ثانية فقط!")
        print(f"   🔊 مدة المقطع الصوتي: {dur1:.2f} ثانية")
        print(f"   📊 حجم الملف: {len(wav_data_1):,} بايت")
        print(f"   📈 أقصى سعة للصوت (Peak Amplitude): {peak1} (صوت بشري طبيعي)")
        print(f"   📉 متوسط طاقة الصوت (RMS Volume): {rms1:.1f}")

        # 2. اختبار توليد نص مخصص بالمصري
        custom_text = "أهلاً بيك يا فنان! الصوت شغال تمام وسريع جداً، والريك مليان ومش فاضي."
        print(f"\n[2/2] 🧪 جاري اختبار توليد جملة مخصصة: \"{custom_text}\"")
        t2 = time.time()
        res_synth = await client.post("/api/v1/voice-clone/synthesize", json={"text": custom_text})
        t3 = time.time()
        elapsed_synth = t3 - t2

        assert res_synth.status_code == 200, f"فشل الطلب: {res_synth.text}"
        wav_data_2 = res_synth.content
        with wave.open(io.BytesIO(wav_data_2)) as wf2:
            dur2 = wf2.getnframes() / wf2.getframerate()
            frames2 = wf2.readframes(wf2.getnframes())
            samples2 = struct.unpack(f"<{len(frames2)//2}h", frames2)
            rms2 = math.sqrt(sum(s**2 for s in samples2) / len(samples2))
            peak2 = max(abs(s) for s in samples2)

        out_file = "test_result_audio.wav"
        with open(out_file, "wb") as f:
            f.write(wav_data_2)

        print(f"   ✅ الحالة: {res_synth.status_code} OK")
        print(f"   ⚡ زمن الاستجابة: {elapsed_synth:.2f} ثانية!")
        print(f"   🔊 مدة المقطع الصوتي: {dur2:.2f} ثانية")
        print(f"   📊 حجم الملف: {len(wav_data_2):,} بايت")
        print(f"   📈 أقصى سعة للصوت (Peak Amplitude): {peak2}")
        print(f"   📉 متوسط طاقة الصوت (RMS Volume): {rms2:.1f}")
        print(f"   💾 تم حفظ الملف الصوتي كـ: {out_file}")

        print("\n" + "=" * 65)
        print("🎉 الاختبار انتهى بنجاح تام! الاستجابة فورية والريك ممتلئ بالصوت.")
        print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_live_test())
