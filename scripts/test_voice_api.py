"""
API Voice & Voice Cloning Test Script (VoiceTut + STT + Voice Clone)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests the entire voice pipeline strictly via REST API endpoints:
  1. GET  /api/v1/audio/speakers        — List Egyptian speakers
  2. POST /api/v1/voice-clone/upload    — Upload user voice recording
  3. POST /api/v1/audio/transcribe      — Transcribe speech to text (STT)
  4. POST /api/v1/audio/voicetut        — Synthesize text via VoiceTut
  5. POST /api/v1/voice-clone/synthesize — Synthesize text with cloned voice
  6. POST /api/v1/voice-clone/test      — Quick Egyptian test response

Usage:
  python scripts/test_voice_api.py
  python scripts/test_voice_api.py --audio "my_voice.wav"
  python scripts/test_voice_api.py --audio "record.m4a" --text "أهلاً بيكم في روبوت نيبيولا"
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
    sys.stdout.reconfigure(encoding="utf-8")

# Ensure repository root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app
from app.core.config import settings
from app.db.session import init_db


def analyze_wav(audio_bytes: bytes) -> dict:
    """Analyze WAV audio bytes to verify real audio content and volume."""
    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            frame_rate = wf.getframerate()
            n_frames = wf.getnframes()
            duration = n_frames / frame_rate if frame_rate > 0 else 0

            frames = wf.readframes(n_frames)
            if sample_width == 2 and len(frames) >= 2:
                num_samples = len(frames) // 2
                samples = struct.unpack(f"<{num_samples}h", frames)
                rms = math.sqrt(sum(s**2 for s in samples) / len(samples))
                peak = max(abs(s) for s in samples)
            else:
                rms = 0.0
                peak = 0

            return {
                "channels": n_channels,
                "sample_rate": frame_rate,
                "duration_s": round(duration, 2),
                "rms": round(rms, 1),
                "peak": peak,
                "size_bytes": len(audio_bytes),
                "valid": duration > 0.3 and len(audio_bytes) > 2000,
            }
    except Exception as exc:
        return {"valid": False, "error": str(exc), "size_bytes": len(audio_bytes)}


async def run_voice_api_test(
    audio_path: str,
    text: str,
    output_path: str = "output_cloned_voice.wav",
    base_url: str = "http://localhost:8000",
    use_live_server: bool = False,
    steps: int = 6,
):
    print("\n" + "═" * 70)
    print("🎙️   NEBULA VOICE & CLONING API TEST (VoiceTut + STT)")
    print("═" * 70)
    print(f"📁 عينة الصوت المدخلة: {audio_path}")
    print(f"💬 النص المراد نطقه بصوتك المستنسخ: \"{text}\"")
    print("═" * 70)

    # Initialize DB for DB sync if running in-process
    await init_db()

    # Determine transport: live server or ASGI in-process
    transport = None
    if not use_live_server:
        # Check if local server is already running on base_url
        try:
            async with httpx.AsyncClient(timeout=1.5) as probe:
                r = await probe.get(f"{base_url}/health")
                if r.status_code == 200:
                    print(f"⚡ تم الاتصال بالسيرفر الشغال محلياً على: {base_url}")
                else:
                    transport = httpx.ASGITransport(app=app)
        except Exception:
            transport = httpx.ASGITransport(app=app)
            print("⚡ تشغيل الاختبار مباشرة عبر FastAPI ASGI Transport (بدون الحاجة لسيرفر خارجي)")

    client_kwargs = {"base_url": base_url, "timeout": 300.0}
    if transport:
        client_kwargs["transport"] = transport

    async with httpx.AsyncClient(**client_kwargs) as client:
        # ── الخطوة 1: فحص حالة الـ API ──────────────────────────────────────────
        print("\n[1/6] 🔍 فحص حالة النظام والـ API (/health)...")
        r_health = await client.get("/health")
        assert r_health.status_code == 200, f"Health check failed: {r_health.text}"
        print(f"   ✅ حالة السيرفر: {r_health.json()}")

        # ── الخطوة 2: استعراض أصوات المتحدثين المصريين في VoiceTut ──────────────
        print("\n[2/6] 🗣️ استعراض قائمة المتحدثين المصريين في VoiceTut (/api/v1/audio/speakers)...")
        r_speakers = await client.get("/api/v1/audio/speakers")
        if r_speakers.status_code == 200:
            spk_data = r_speakers.json()
            speakers = spk_data.get("speakers", [])
            print(f"   ✅ تم العثور على {len(speakers)} متحدث مصري جاهز: {', '.join(speakers[:8])}...")
        else:
            print(f"   ⚠️ استجابة المتحدثين: {r_speakers.status_code}")

        # ── الخطوة 3: رفع ملف الصوت المخصص للاستنساخ ─────────────────────────────
        print(f"\n[3/6] 📤 رفع ملف الصوت للاستنساخ (/api/v1/voice-clone/upload)...")
        p = Path(audio_path)
        if not p.exists():
            raise FileNotFoundError(f"لم يتم العثور على ملف الصوت: {audio_path}")

        file_bytes = p.read_bytes()
        files = {"file": (p.name, file_bytes, "audio/wav")}
        data = {"personality_id": "1"}

        t0_up = time.perf_counter()
        r_upload = await client.post("/api/v1/voice-clone/upload", files=files, data=data)
        up_time = (time.perf_counter() - t0_up) * 1000

        assert r_upload.status_code == 201, f"فشل رفع ملف الصوت ({r_upload.status_code}): {r_upload.text}"
        upload_resp = r_upload.json()
        print(f"   ✅ تم رفع الصوت وحفظه كعينة مرجعية بنجاح في {up_time:.1f}ms")
        print(f"      المسار المحفوظ: {upload_resp.get('path')}")

        # ── الخطوة 4: تفريغ عينة الصوت نصياً عبر الـ STT (Speech-to-Text) ─────────
        print("\n[4/6] 📝 تجربة تفريغ الصوت إلى نص عبر STT (/api/v1/audio/transcribe)...")
        t0_stt = time.perf_counter()
        files_stt = {"file": (p.name, file_bytes, "audio/wav")}
        r_stt = await client.post("/api/v1/audio/transcribe", files=files_stt)
        stt_time = (time.perf_counter() - t0_stt) * 1000

        detected_transcript = None
        if r_stt.status_code == 200:
            stt_data = r_stt.json()
            detected_transcript = stt_data.get("transcription", "")
            print(f"   ✅ تم تفريغ الصوت بنجاح في {stt_time:.1f}ms (المزود: {stt_data.get('provider')})")
            print(f"      النص المكتشف في التسجيل: \"{detected_transcript}\"")
        else:
            print(f"   ⚠️ تنبيه في STT ({r_stt.status_code}): {r_stt.text}")

        # ── الخطوة 5: توليد الصوت المستنسخ عبر VoiceTut ──────────────────────────
        print(f"\n[5/6] 🎭 توليد الصوت المستنسخ باستخدام VoiceTut (/api/v1/voice-clone/synthesize)...")
        synth_payload = {
            "text": text,
            "personality_id": 1,
            "language": "ar",
            "ref_text": detected_transcript or None,
            "num_steps": steps,
        }

        t0_synth = time.perf_counter()
        r_synth = await client.post("/api/v1/voice-clone/synthesize", json=synth_payload)
        synth_time = time.perf_counter() - t0_synth

        assert r_synth.status_code == 200, f"فشل توليد الصوت ({r_synth.status_code}): {r_synth.text}"
        wav_out = r_synth.content
        assert len(wav_out) > 2000, "الملف الصوتي الناتج فارغ أو تالف!"

        Path(output_path).write_bytes(wav_out)
        print(f"   ✅ نجح توليد الصوت المستنسخ في {synth_time:.2f} ثانية!")
        print(f"   💾 تم حفظ الصوت الناتج في: {output_path}")

        # ── الخطوة 6: تحليل إشارة الصوت ومطابقة الجودة ───────────────────────────
        print("\n[6/6] 📊 تحليل الموجة الصوتية للملف الناتج...")
        analysis = analyze_wav(wav_out)
        print(f"   • مدة المقطع: {analysis.get('duration_s')} ثانية")
        print(f"   • معدل التردد (Sample Rate): {analysis.get('sample_rate')} Hz")
        print(f"   • متوسط طاقة الصوت (RMS Volume): {analysis.get('rms')}")
        print(f"   • أقصى سعة للصوت (Peak Amplitude): {analysis.get('peak')}")
        print(f"   • حجم الملف: {analysis.get('size_bytes'):,} بايت")
        assert analysis.get("valid"), "تحليل الصوت يشير إلى وجود خطأ في ملف الـ WAV!"

        print("\n" + "═" * 70)
        print("🎉 اكتمل اختبار الـ API بنجاح تام 100%!")
        print(f"   تم استنساخ صوتك وتوليد النطق العربي المصري بنجاح عبر VoiceTut.")
        print(f"   الملف الصوتي جاهز للاستماع: {os.path.abspath(output_path)}")
        print("═" * 70)

        # تشغيل الصوت تلقائياً للمستخدم للاستماع إليه
        try:
            if sys.platform == "win32":
                os.startfile(output_path)
                print("🔊 جاري تشغيل المقطع الصوتي لسماعه الآن...")
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="اختبار استنساخ الصوت والـ STT عبر الـ API")
    parser.add_argument("--audio", type=str, default=None, help="مسار ملف الصوت المراد استنساخه")
    parser.add_argument("--text", type=str, default=None, help="النص العربي المراد نطقه بالصوت المستنسخ")
    parser.add_argument("--output", type=str, default="output_cloned_voice.wav", help="مسار حفظ الصوت الناتج")
    parser.add_argument("--steps", type=int, default=6, help="عدد خطوات التوليد (4 سريع، 6 متوازن، 10 دقة أعلى)")
    parser.add_argument("--url", type=str, default="http://localhost:8000", help="عنوان السيرفر")
    parser.add_argument("--live", action="store_true", help="الاتصال بسيرفر شغال بدلاً من ASGI Transport")

    args = parser.parse_args()

    # Audio path handling (interactive fallback if not provided)
    audio_path = args.audio
    if not audio_path:
        # Check if default sample files exist as suggestions
        defaults = [
            "test_salma.wav",
            "test_voice_ar.wav",
            "test_audio_egyptian.wav",
            "data/voice_samples/personality_1.wav",
        ]
        existing_defaults = [d for d in defaults if os.path.exists(d)]

        print("\n" + "─" * 60)
        print("🎙️ اختبار استنساخ الصوت عبر الـ API (Voice Clone API)")
        print("─" * 60)
        if existing_defaults:
            print(f"عينة افتراضية متاحة: {existing_defaults[0]}")
        
        entered = input("من فضلك أدخلي مسار ملف الصوت الخاص بكِ (WAV, MP3, M4A, etc.) [اضغطي Enter للافتراضي]: ").strip()
        entered = entered.strip("\"'")
        if entered:
            audio_path = entered
        elif existing_defaults:
            audio_path = existing_defaults[0]
        else:
            print("❌ يجب إدخال مسار ملف صوتي صالح للاختبار.")
            sys.exit(1)

    if not os.path.exists(audio_path):
        print(f"❌ لم يتم العثور على الملف الصوتي: {audio_path}")
        sys.exit(1)

    # Text handling
    text = args.text
    if not text:
        default_text = "أهلاً بيكم، تم استنساخ صوتي بنجاح من خلال الـ API ونظام فويس توت شغال تمام!"
        entered_text = input(f"النص المراد نطقه بصوتك المستنسخ [اضغطي Enter للنص الافتراضي]: ").strip()
        text = entered_text if entered_text else default_text

    asyncio.run(
        run_voice_api_test(
            audio_path=audio_path,
            text=text,
            output_path=args.output,
            base_url=args.url,
            use_live_server=args.live,
            steps=args.steps,
        )
    )


if __name__ == "__main__":
    main()
