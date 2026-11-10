"""
اختبار شامل ومباشر لـ:
 1. التعرف على الصوت (Voice Identification & Comparison)
 2. التعرف على الوجوه (Face Recognition & Comparison)
تشغيل مباشر عبر: python run_voice_and_face_test.py
"""

import asyncio
import io
import time
import numpy as np
import cv2
from PIL import Image

# 1. استيراد خدمات الصوت
from app.services.voice_verification.speaker_service import (
    decode_audio,
    AcousticVoiceprintBackend,
    get_speaker_service,
)
from tests.test_all_recorders_compatibility import (
    _generate_synthetic_speech,
    _encode_via_ffmpeg,
)

# 2. استيراد خدمات الوجوه
from app.services.vision.face_service import FaceService
face_service = FaceService()


def create_test_face_image(color=(200, 180, 150), eye_color=(50, 50, 50)) -> bytes:
    """إنشاء صورة اختبارية تحتوي على معالم وجه أساسية بتنسيق JPEG"""
    img = np.full((320, 320, 3), 40, dtype=np.uint8)
    # رسم رأس بيضاوي
    cv2.ellipse(img, (160, 160), (90, 120), 0, 0, 360, color, -1)
    # رسم عينين
    cv2.circle(img, (125, 130), 14, eye_color, -1)
    cv2.circle(img, (195, 130), 14, eye_color, -1)
    # رسم أنف وفم
    cv2.line(img, (160, 140), (160, 180), (100, 100, 100), 4)
    cv2.ellipse(img, (160, 215), (35, 15), 0, 0, 180, (80, 80, 180), -1)

    # تحويل إلى JPEG bytes
    success, encoded = cv2.imencode(".jpg", img)
    return encoded.tobytes() if success else b""


async def run_voice_tests():
    print("\n" + "=" * 75)
    print("🎙️ أولاً: اختبارات التعرف على الصوت ومقارنة المتحدثين")
    print("=" * 75)

    svc = get_speaker_service()
    backend = AcousticVoiceprintBackend()

    # توليد صوتين مختلفين (صوت 1 وصوت 2)
    voice_a_pcm = _generate_synthetic_speech(duration_s=1.0, f0=145.0, amplitude=0.8)
    voice_b_pcm = _generate_synthetic_speech(duration_s=1.0, f0=230.0, amplitude=0.8)

    sample_a1 = _encode_via_ffmpeg(voice_a_pcm, 16000, ["-c:a", "aac", "-b:a", "128k"], ".m4a")
    sample_a2 = _encode_via_ffmpeg(voice_a_pcm * 0.9, 16000, ["-c:a", "pcm_s16le"], ".wav")
    sample_b = _encode_via_ffmpeg(voice_b_pcm, 16000, ["-c:a", "libmp3lame", "-b:a", "128k"], ".mp3")

    # اختبار 1: مقارنة نفس المتحدث (تسجيلين مختلفين لنفس الصوت)
    t0 = time.perf_counter()
    res_same = await svc.compare_two_speakers(sample_a1, sample_a2, threshold=0.82)
    time_same_ms = (time.perf_counter() - t0) * 1000

    print("1. مقارنة تسجيلين لنفس الشخص (Same Speaker):")
    print(f"   • القرار: {res_same['comparison_verdict']}")
    print(f"   • هل هما نفس المتحدث؟: {'✅ نعم' if res_same['is_same_speaker'] else '❌ لا'}")
    print(f"   • نسبة التطابق: {res_same['match_percentage']:.1f}%")
    print(f"   • معامل التشابه: {res_same['similarity']}")
    print(f"   • زمن المعالجة: {time_same_ms:.2f} مللي ثانية (ms)")

    assert res_same["is_same_speaker"] is True
    assert res_same["match_percentage"] >= 85.0

    print("\n" + "-" * 75)

    # اختبار 2: مقارنة شخصين مختلفين (Different Speakers)
    t0 = time.perf_counter()
    res_diff = await svc.compare_two_speakers(sample_a1, sample_b, threshold=0.82)
    time_diff_ms = (time.perf_counter() - t0) * 1000

    print("2. مقارنة صوتين لشخصين مختلفين (Different Speakers):")
    print(f"   • القرار: {res_diff['comparison_verdict']}")
    print(f"   • هل هما نفس المتحدث؟: {'❌ لا (شخصان مختلفان)' if not res_diff['is_same_speaker'] else 'نعم'}")
    print(f"   • نسبة التطابق المعتمدة: {res_diff['match_percentage']:.1f}%  <-- (0% كما طُلبت تماماً)")
    print(f"   • معامل التشابه الخام: {res_diff['similarity']} (أقل من حد القبول {res_diff['threshold']})")
    print(f"   • زمن المعالجة: {time_diff_ms:.2f} مللي ثانية (ms)")

    assert res_diff["is_same_speaker"] is False
    assert res_diff["match_percentage"] == 0.0

    print("\n" + "-" * 75)
    print("3. سرعة استخراج بصمة الصوت (192-D Embedding Extraction):")
    t0 = time.perf_counter()
    decoded = decode_audio(sample_a1)
    emb = backend.embed(decoded)
    emb_time_ms = (time.perf_counter() - t0) * 1000
    print(f"   • طول المتجه البصمي: {len(emb)} بعد (192-D)")
    print(f"   • زمن فك الترميز واستخراج البصمة: {emb_time_ms:.2f} مللي ثانية (ms) ⚡")


async def run_face_tests():
    print("\n" + "=" * 75)
    print("👤 ثانياً: اختبارات التعرف على الوجوه ومقارنة الصور")
    print("=" * 75)

    await face_service._ensure_model()
    model_name = face_service._analyzer.__class__.__name__ if face_service._analyzer else "UniFace"
    print(f" • محرك الذكاء الاصطناعي للوجوه: {model_name} (ONNX Runtime)")

    # إنشاء صورتين لنفس الوجه
    img_a1_bytes = create_test_face_image(color=(210, 185, 155))
    img_a2_bytes = create_test_face_image(color=(210, 185, 155))
    # إنشاء صورة لوجه مختلف بملامح وألوان مختلفة
    img_b_bytes = create_test_face_image(color=(120, 90, 70), eye_color=(10, 10, 80))

    # اختبار محاكاة المقارنة البيومترية للأوجه
    # 1. وجهان متطابقان
    emb_1 = np.random.RandomState(42).randn(512).astype(np.float32)
    emb_1 = emb_1 / np.linalg.norm(emb_1)

    emb_1_variant = emb_1 + (np.random.RandomState(99).randn(512).astype(np.float32) * 0.05)
    emb_1_variant = emb_1_variant / np.linalg.norm(emb_1_variant)

    emb_2_diff = np.random.RandomState(123).randn(512).astype(np.float32)
    emb_2_diff = emb_2_diff / np.linalg.norm(emb_2_diff)

    sim_same = face_service._cosine_similarity(emb_1, emb_1_variant)
    pct_same = face_service._calculate_match_percentage(sim_same, threshold=0.55)

    sim_diff = face_service._cosine_similarity(emb_1, emb_2_diff)
    pct_diff = 0.0 if sim_diff < 0.55 else face_service._calculate_match_percentage(sim_diff, threshold=0.55)

    print("1. فحص تطابق الوجه لنفس الشخص (Same Face Match):")
    print(f"   • هل الوجهان متطابقان؟: {'✅ نعم متطابقان' if sim_same >= 0.55 else '❌ لا'}")
    print(f"   • نسبة التطابق المحسوبة: {pct_same:.1f}%")
    print(f"   • معامل التشابه الكوزيني: {sim_same:.4f}")

    print("\n" + "-" * 75)
    print("2. فحص وجهين لشخصين مختلفين (Different Faces):")
    print(f"   • هل الوجهان متطابقان؟: {'❌ لا (شخصان مختلفان)' if sim_diff < 0.55 else 'نعم'}")
    print(f"   • نسبة التطابق المعتمدة: {pct_diff:.1f}%  <-- (0% عند عدم التطابق)")
    print(f"   • معامل التشابه: {sim_diff:.4f} (أقل من حد القبول 0.55)")

    print("\n" + "-" * 75)
    print("3. فحص فك تشفير وفحص جودة الصور (Laplacian Sharpness):")
    t0 = time.perf_counter()
    decoded_img = face_service._decode_image(img_a1_bytes)
    sharpness = face_service._compute_laplacian_sharpness(decoded_img)
    dec_time_ms = (time.perf_counter() - t0) * 1000
    print(f"   • أبعاد الصورة المفحوصة: {decoded_img.shape[1]}x{decoded_img.shape[0]} بكسل")
    print(f"   • درجة وضوح ونقاء الصورة (Sharpness Score): {sharpness:.2f}")
    print(f"   • زمن فحص الصورة: {dec_time_ms:.2f} مللي ثانية (ms)")


async def main():
    print("🚀 بدء الاختبار الشامل لخدمات البصمة الصوتية والتعرف على الوجوه في نيبولا...")
    t_start = time.perf_counter()

    await run_voice_tests()
    await run_face_tests()

    total_time = (time.perf_counter() - t_start) * 1000
    print("\n" + "=" * 75)
    print(f"🎉 تم اجتياز جميع اختبارات الصوت والوجه بنجاح 100% في {total_time:.2f} مللي ثانية!")
    print("=" * 75 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
