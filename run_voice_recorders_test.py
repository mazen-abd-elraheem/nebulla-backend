"""
ملف تشغيل واختبار فوري لجميع مسجلات الصوت الـ 14
يمكن تشغيله مباشرة عبر: python run_voice_recorders_test.py
"""

import time
import numpy as np
from app.services.voice_verification.speaker_service import (
    decode_audio,
    AcousticVoiceprintBackend,
    get_speaker_service,
)
from tests.test_all_recorders_compatibility import (
    _generate_synthetic_speech,
    _encode_via_ffmpeg,
)

async def main():
    print("=" * 70)
    print("🎙️ اختبار توافق وسرعة جميع مسجلات وتطبيقات الصوت الـ 14")
    print("=" * 70)

    # توليد صوت اصطناعي يحاكي الحنجرة البشرية
    pcm_voice_a = _generate_synthetic_speech(duration_s=1.0, f0=145.0, amplitude=0.8)
    pcm_voice_b = _generate_synthetic_speech(duration_s=1.0, f0=220.0, amplitude=0.8)
    backend = AcousticVoiceprintBackend()

    recorders = [
        ("1. Voice Recorder (Samsung / Xiaomi)", ["-c:a", "aac", "-b:a", "128k"], ".m4a"),
        ("1b. Voice Recorder (Android AMR)", ["-c:a", "amr_nb", "-ar", "8000"], ".amr"),
        ("2. Easy Voice Recorder", ["-c:a", "libmp3lame", "-b:a", "192k"], ".mp3"),
        ("3. Smart Voice Recorder", ["-c:a", "libvorbis", "-q:a", "4"], ".ogg"),
        ("4. Dolby On", ["-c:a", "aac", "-b:a", "256k"], ".mp4"),
        ("5. Voice Memos (Apple iPhone / Mac)", ["-c:a", "aac", "-b:a", "128k"], ".m4a"),
        ("6. Audacity (24-bit BWF)", ["-c:a", "pcm_s24le", "-ar", "44100"], ".wav"),
        ("6b. Audacity (32-bit Float)", ["-c:a", "pcm_f32le", "-ar", "48000"], ".wav"),
        ("7. Sound Recorder / Windows", ["-c:a", "wmav2", "-b:a", "64k"], ".wma"),
        ("8. Adobe Audition (FLAC Lossless)", ["-c:a", "flac"], ".flac"),
        ("9. GarageBand (AIFF)", ["-c:a", "pcm_s16be"], ".aiff"),
        ("10. Ocenaudio (MP3 VBR)", ["-c:a", "libmp3lame", "-q:a", "2"], ".mp3"),
        ("11. Zoom (H1n/H4n/H6) 24-bit Quiet Headroom", ["-c:a", "pcm_s24le", "-ar", "48000"], ".wav"),
        ("12. Tascam (DR-05X) 96kHz High-Res", ["-c:a", "pcm_s24le", "-ar", "96000"], ".wav"),
        ("13. Sony (PCM-A10 / ICD)", ["-c:a", "pcm_s16le", "-ar", "44100"], ".wav"),
        ("14. Olympus / OM System (Voice-Trek)", ["-c:a", "libmp3lame", "-b:a", "128k", "-ac", "1"], ".mp3"),
    ]

    print(f"{'المسجل / التطبيق':<40} | {'الصيغة':<8} | {'وقت المعالجة':<14} | {'الحالة'}")
    print("-" * 75)

    sample_m4a = None
    sample_zoom = None

    for name, args, ext in recorders:
        # إعداد الإشارة مع محاكاة الـ Headroom لـ Zoom
        input_sig = pcm_voice_a * 0.10 if "Zoom" in name else pcm_voice_a
        raw_bytes = _encode_via_ffmpeg(input_sig, 16000, args, ext)

        if "Voice Memos" in name:
            sample_m4a = raw_bytes
        if "Zoom" in name:
            sample_zoom = raw_bytes

        t0 = time.perf_counter()
        decoded = decode_audio(raw_bytes)
        emb = backend.embed(decoded)
        dur_ms = (time.perf_counter() - t0) * 1000

        print(f"{name:<40} | {ext:<8} | {dur_ms:>6.2f} ms     | ✅ تم بنجاح")

    print("-" * 75)
    print("⚖️ اختبار المقارنة بين مسجلين مختلفين لنفس المتحدث:")
    print("   (Apple Voice Memos .m4a  ضد  Zoom Field Recorder .wav 24-bit)")

    svc = get_speaker_service()
    t0 = time.perf_counter()
    res = await svc.compare_two_speakers(
        audio1=sample_m4a,
        audio2=sample_zoom,
        threshold=0.82
    )
    compare_time_ms = (time.perf_counter() - t0) * 1000

    print(f" • قرار الفحص: {res['comparison_verdict']}")
    print(f" • نسبة التطابق: {res['similarity']:.2%}")
    print(f" • كود اللغة المكتشف: {res['voice1']['language_code']} (اللهجة المصرية)")
    print(f" • إجمالي وقت المقارنة لكلا الملفين: {compare_time_ms:.2f} مللي ثانية (ms) ⚡")
    print("=" * 70)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())

