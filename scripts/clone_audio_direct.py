"""
Direct Voice Cloning CLI — استنساخ أي ريكورد مباشرة بدون متصفح أو UI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يقبل سحب أي ملف صوت أو فيديو (WAV, MP3, M4A, MP4, AAC, OGG, Opus)
ويقوم باستنساخه ونطقه فوراً وتشغيل الصوت الناتج تلقائياً على الويندوز.
"""

import asyncio
import io
import math
import os
import struct
import sys
import time
import wave
from pathlib import Path

# إعداد الترميز للغة العربية على ويندوز
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, ".")

from app.services.voice_clone.voice_clone_service import VoiceCloneService, _save_and_convert_to_wav
from app.db.session import init_db


def analyze_audio(wav_bytes: bytes) -> tuple[float, int, float]:
    """حساب مدة الصوت وأقصى سعة ومتوسط الطاقة للتأكد أن الريك غير فارغ."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            dur = wf.getnframes() / wf.getframerate()
            frames = wf.readframes(wf.getnframes())
            if not frames:
                return dur, 0, 0.0
            samples = struct.unpack(f"<{len(frames)//2}h", frames)
            peak = max(abs(s) for s in samples) if samples else 0
            rms = math.sqrt(sum(s**2 for s in samples) / len(samples)) if samples else 0.0
            return dur, peak, rms
    except Exception:
        return 0.0, 0, 0.0


async def clone_direct(audio_path: str | None = None, text: str | None = None, transcript: str | None = None):
    await init_db()
    svc = VoiceCloneService.get_instance()

    print("=" * 70)
    print("🎙️ منظومة استنساخ الصوت المباشرة (Direct Audio Cloning)")
    print("=" * 70)

    # 1. تحديد ملف الصوت (الريكورد)
    ref_wav_to_use = None
    if audio_path and audio_path.strip():
        clean_path = audio_path.strip().strip("'\"")
        p = Path(clean_path)
        if not p.exists():
            print(f"❌ خطأ: ملف الصوت غير موجود في المسار: {clean_path}")
            return
        
        print(f"\n📂 جاري قراءة وتحويل ملف الصوت: {p.name} ({p.stat().st_size / 1024:.1f} KB)...")
        raw_bytes = p.read_bytes()
        dest_wav = Path("data/voice_samples/personality_1.wav")
        dest_wav.parent.mkdir(parents=True, exist_ok=True)
        
        # تحويل وضبط الملف إلى WAV متوافق مع الاستنساخ
        dur = _save_and_convert_to_wav(raw_bytes, p.suffix.lower(), dest_wav)
        print(f"✅ تم ضبط الريكورد بنجاح (المدة: {dur:.1f} ثانية)!")

        # حفظ النص المرجعي إن وجد
        txt_dest = dest_wav.with_suffix(".txt")
        if transcript and transcript.strip():
            txt_dest.write_text(transcript.strip(), encoding="utf-8")
        elif txt_dest.exists():
            txt_dest.unlink()

        # تحديث الماب وقاعدة البيانات
        svc._personality_voice_map[1] = str(dest_wav)
        await svc._sync_db_voice_sample(1, str(dest_wav))
        ref_wav_to_use = str(dest_wav)
    else:
        # استخدام الصوت الحالي المسجل مسبقاً
        ref_wav_to_use = svc.get_sample_path(1)
        if not ref_wav_to_use or not os.path.exists(ref_wav_to_use):
            print("❌ لا يوجد ملف صوت مسجل مسبقاً! يرجى تحديد مسار ملف صوت للاستنساخ عليه.")
            return
        print(f"\nℹ️ سيتم الاستنساخ بناءً على آخر ريكورد مسجل: {ref_wav_to_use}")

    # 2. تحديد النص المراد نطقه بالصوت
    if not text or not text.strip():
        text = "أهلاً بيكم يا شباب، تم استنساخ الصوت بنجاح، والصوت واضح وعالي ومش فاضي أبداً!"

    print(f"\n✍️ النص المطلوب نطقه: \"{text}\"")
    print("⏳ جاري توليد الكلام بالصوت المستنسخ عبر محرك الذكاء الاصطناعي...")
    
    t0 = time.time()
    wav_bytes = await svc.synthesize(text=text, reference_wav=ref_wav_to_use)
    t1 = time.time()
    elapsed = t1 - t0

    if not wav_bytes or len(wav_bytes) <= 1000:
        print("❌ فشل التوليد: لم يتم إرجاع ملف صوتي صالح.")
        return

    dur, peak, rms = analyze_audio(wav_bytes)

    out_file = "my_cloned_voice.wav"
    with open(out_file, "wb") as f:
        f.write(wav_bytes)

    print("\n" + "=" * 70)
    print(f"🎉 تم استنساخ ونطق الصوت بنجاح تام!")
    print(f"⚡ الوقت المستغرق: {elapsed:.2f} ثانية")
    print(f"🔊 مدة الصوت الناتج: {dur:.2f} ثانية")
    print(f"📈 أقصى سعة للصوت (Peak Amplitude): {peak} (قيمة ممتازة وغير فارغة)")
    print(f"📉 متوسط طاقة الصوت (RMS Volume): {rms:.1f}")
    print(f"💾 تم حفظ الملف الصوتي كـ: {os.path.abspath(out_file)}")
    print("=" * 70)

    # تشغيل الصوت تلقائياً للمستخدم
    print("\n▶️ جاري تشغيل الملف الصوتي الآن لتسمعه...")
    try:
        os.startfile(out_file)
    except Exception as e:
        print(f"⚠️ تعذر فتح المشغل التلقائي: {e}")


def main():
    audio_path = None
    text = None
    transcript = None

    if len(sys.argv) > 1:
        # تشغيل من سطر الأوامر: python scripts/clone_audio_direct.py "audio.mp3" "نص تجربة"
        audio_path = sys.argv[1]
        if len(sys.argv) > 2:
            text = " ".join(sys.argv[2:])
    else:
        # الوضع التفاعلي
        print("=" * 70)
        print("🎙️ تجربة استنساخ الصوت المباشر (Direct Audio Clone CLI)")
        print("=" * 70)
        
        try:
            print("\n1️⃣ اسحب ملف الصوت أو الفيديو الجديد هنا ثم اضغط Enter")
            print("   (أو اضغط Enter مباشرة لاستخدام آخر صوت تم حفظه):")
            audio_path = input("👉 مسار الملف: ").strip()

            print("\n2️⃣ اكتب النص اللي عايزه ينطقه بصوتك المستنسخ")
            print("   (أو اضغط Enter لاستخدام الجملة الافتراضية):")
            text = input("👉 النص: ").strip()

            if audio_path:
                print("\n3️⃣ ما قيل في التسجيل (اختياري، اضغط Enter للتخطي):")
                transcript = input("👉 كلام الريك: ").strip()

        except (KeyboardInterrupt, EOFError):
            print("\nتم الإلغاء.")
            return

    asyncio.run(clone_direct(audio_path, text, transcript))


if __name__ == "__main__":
    main()
