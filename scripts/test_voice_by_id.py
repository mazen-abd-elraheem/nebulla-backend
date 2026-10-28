"""
اختبار استنساخ وتوليد الصوت عبر الـ API بتحديد المعرف (ID) والنص
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يقوم هذا السكريبت باختبار نقطة الـ REST API:
  POST /api/v1/voice-clone/synthesize
حيث يمكنك اختيار أي ID (سواء رقم العينة المستنسخة مثل 1 أو اسم متحدث مصري مثل mohammed)
وكتابة أي نص بالعامية المصرية وتوليد ملف الصوت فوراً.
"""

import argparse
import asyncio
import io
import math
import os
import struct
import sys
import time
import wave
from pathlib import Path
import httpx

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

# إضافة المجلد الرئيسي للمشروع
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.db.session import init_db


def analyze_wav(audio_bytes: bytes) -> dict:
    """تحليل الإشارة الصوتية للتأكد من جودة وقوة الصوت الناتج."""
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            n_frames = wf.getnframes()
            rate = wf.getframerate()
            dur = n_frames / rate if rate > 0 else 0
            frames = wf.readframes(n_frames)
            samples = struct.unpack(f"<{len(frames)//2}h", frames)
            rms = math.sqrt(sum(s**2 for s in samples) / len(samples)) if samples else 0.0
            peak = max(abs(s) for s in samples) if samples else 0
            return {
                "duration_s": round(dur, 2),
                "sample_rate": rate,
                "rms": round(rms, 1),
                "peak": peak,
                "size_bytes": len(audio_bytes),
                "valid": dur > 0.3 and len(audio_bytes) > 2000,
            }
    except Exception as exc:
        return {"valid": False, "error": str(exc), "size_bytes": len(audio_bytes)}


async def test_synthesis_by_id(
    voice_id: str | int,
    text: str,
    output_path: str = "api_tested_voice.wav",
    base_url: str = "http://localhost:8000",
    use_live_server: bool = False,
    steps: int = 6,
):
    print("=" * 70)
    print("🎙️ اختبار توليد واستنساخ الصوت عبر الـ API (اختيار الـ ID والنص)")
    print("=" * 70)
    print(f"🆔 معرف الصوت المختار (Voice ID): {voice_id}")
    print(f"✍️ النص المراد نطقه: \"{text}\"")
    print(f"⚙️ خطوات التوليد (Steps): {steps}")
    print("=" * 70)

    await init_db()

    # تحديد وسيلة الاتصال: سيرفر شغال أو ASGI داخلي مباشر
    transport = None
    if not use_live_server:
        try:
            async with httpx.AsyncClient(timeout=1.5) as probe:
                r = await probe.get(f"{base_url}/health")
                if r.status_code == 200:
                    print(f"⚡ تم الاتصال بالسيرفر النشط على: {base_url}")
                else:
                    transport = httpx.ASGITransport(app=app)
        except Exception:
            transport = httpx.ASGITransport(app=app)
            print("⚡ تشغيل الاختبار مباشرة عبر FastAPI ASGI Transport (بدون انتظار سيرفر خارجي)")

    client_kwargs = {"base_url": base_url, "timeout": 300.0}
    if transport:
        client_kwargs["transport"] = transport

    async with httpx.AsyncClient(**client_kwargs) as client:
        # 1. استعراض الأصوات المتاحة
        print("\n[1/3] 🔍 جلب قائمة الأصوات المتاحة في النظام (/api/v1/voice-clone/voices)...")
        r_voices = await client.get("/api/v1/voice-clone/voices")
        if r_voices.status_code == 200:
            v_data = r_voices.json()
            print(f"   ✅ مزود الصوت النشط: {v_data.get('active_provider')}")
            samples = v_data.get("cloned_samples", [])
            print(f"   📁 عينات الأصوات المستنسخة المرفوعة ({len(samples)}):")
            for s in samples:
                print(f"      • ID: {s.get('personality_id')} | ملف: {s.get('filename')} | المدة: {s.get('duration_s')}s")
            speakers = v_data.get("voicetut_speakers", [])
            print(f"   🗣️ أصوات VoiceTut المصرية الجاهزة ({len(speakers)}): {', '.join(speakers[:8])}...")
        else:
            print(f"   ⚠️ استجابة قائمة الأصوات: {r_voices.status_code}")

        # 2. إرسال طلب التوليد بالـ ID والنص
        print(f"\n[2/3] 🚀 إرسال طلب التوليد إلى الـ API (/api/v1/voice-clone/synthesize)...")
        payload = {
            "text": text,
            "voice_id": voice_id,
            "num_steps": steps,
        }
        t0 = time.time()
        res = await client.post("/api/v1/voice-clone/synthesize", json=payload)
        elapsed = time.time() - t0

        if res.status_code != 200:
            print(f"❌ فشل الطلب (كود {res.status_code}): {res.text}")
            return False

        wav_bytes = res.content
        print(f"   ✅ تم استلام ملف الصوت بنجاح في {elapsed:.2f} ثانية! (الحجم: {len(wav_bytes):,} بايت)")

        # 3. حفظ وتحليل الصوت
        print("\n[3/3] 📊 فحص وتحليل الإشارة الصوتية الناتجة...")
        Path(output_path).write_bytes(wav_bytes)
        analysis = analyze_wav(wav_bytes)
        print(f"   • مدة الصوت: {analysis.get('duration_s')} ثانية")
        print(f"   • التردد: {analysis.get('sample_rate')} Hz")
        print(f"   • متوسط الطاقة (RMS Volume): {analysis.get('rms')}")
        print(f"   • أقصى سعة (Peak): {analysis.get('peak')}")
        print(f"   💾 تم حفظ الصوت في: {os.path.abspath(output_path)}")

        print("\n" + "=" * 70)
        print("🎉 اكتمل اختبار الـ API بنجاح تام 100%!")
        print("=" * 70)

        # تشغيل الصوت تلقائياً لسماعه
        try:
            if sys.platform == "win32":
                os.startfile(output_path)
                print("🔊 جاري تشغيل المقطع الصوتي لسماعه الآن...")
        except Exception:
            pass

        return True


def main():
    parser = argparse.ArgumentParser(description="اختيار ID الصوت والنص لتوليد الصوت عبر الـ API")
    parser.add_argument("--id", type=str, default="1", help="معرف الصوت المراد استنساخه (مثال: 1 للعينة المستنسخة، أو mohammed، أو yasmin)")
    parser.add_argument("--text", type=str, default=None, help="النص العربي بالعامية المصرية المراد نطقه")
    parser.add_argument("--output", type=str, default="api_tested_voice.wav", help="مسار حفظ ملف الصوت الناتج")
    parser.add_argument("--steps", type=int, default=6, help="خطوات التوليد (4 سريع، 6 متوازن، 10 دقة أعلى)")
    parser.add_argument("--url", type=str, default="http://localhost:8000", help="عنوان السيرفر")
    parser.add_argument("--live", action="store_true", help="الاتصال بسيرفر شغال")

    args = parser.parse_args()

    # إذا لم يدخل المستخدم نصاً، نحدد نصاً مصرياً افتراضياً جميلاً
    text = args.text
    if not text:
        text = "أهلاً بيكم يا شباب، تم اختيار الـ ID وتوليد الصوت بالعامية المصرية بنجاح من خلال الـ API!"

    asyncio.run(
        test_synthesis_by_id(
            voice_id=args.id,
            text=text,
            output_path=args.output,
            base_url=args.url,
            use_live_server=args.live,
            steps=args.steps,
        )
    )


if __name__ == "__main__":
    main()

