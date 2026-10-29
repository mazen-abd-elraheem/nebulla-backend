"""
Live End-to-End Test for the UniFace Face Recognition, Comparison,
Storage, and Video Extraction REST API.
"""

import asyncio
import os
import sys
import tempfile
import cv2
import httpx
import numpy as np

# Ensure UTF-8 console output on Windows
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from app.main import app
from app.db.session import init_db


def make_test_video(face_bgr: np.ndarray, duration_sec: float = 2.0, fps: float = 10.0) -> bytes:
    """Create a test MP4 video placing a face inside moving frames."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_vid:
        temp_path = temp_vid.name

    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(temp_path, fourcc, fps, (640, 480))
        num_frames = int(duration_sec * fps)

        h, w = face_bgr.shape[:2]
        # Resize face to fit nicely
        face_resized = cv2.resize(face_bgr, (200, 200))

        for i in range(num_frames):
            frame = np.ones((480, 640, 3), dtype=np.uint8) * 230
            # Position moving slightly
            x_offset = 100 + int(i * 10)
            y_offset = 120
            frame[y_offset:y_offset + 200, x_offset:x_offset + 200] = face_resized
            out.write(frame)

        out.release()
        with open(temp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


async def main():
    print("=" * 70)
    print("🚀 بدء اختبار الـ Face API الحي الشامل (UniFace Live API Test)")
    print("=" * 70)

    # 1. Initialize DB
    await init_db()

    # 2. Prepare sample real face
    print("\n📥 1. جلب صورة وجه حقيقية للاختبار...")
    async with httpx.AsyncClient() as dl_client:
        img_resp = await dl_client.get("https://raw.githubusercontent.com/opencv/opencv/master/samples/data/lena.jpg")
        if img_resp.status_code != 200:
            print("❌ فشل تحميل صورة الاختبار.")
            return
        lena_bytes = img_resp.content
        print(f"✅ تم تحميل صورة الوجه بنجاح ({len(lena_bytes):,} بايت).")

    # Decode for video generator
    nparr = np.frombuffer(lena_bytes, np.uint8)
    face_bgr = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    # Prepare video
    print("\n🎬 2. إنشاء فيديو تجريبي يحتوي على الوجه...")
    video_bytes = make_test_video(face_bgr, duration_sec=1.5, fps=10.0)
    print(f"✅ تم إنشاء الفيديو التجريبي ({len(video_bytes):,} بايت).")

    # Connect to FastAPI app via ASGITransport
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost:8000") as client:

        # ── Test 1: Register Face from Image ──────────────────────────────────
        print("\n" + "─" * 50)
        print("👤 3. اختبار تسجيل شخص بصورة (POST /api/v1/faces/register)")
        files = {"file": ("lena.jpg", lena_bytes, "image/jpeg")}
        data = {"name": "Lena Soderberg"}

        res_reg = await client.post("/api/v1/faces/register", data=data, files=files)
        print(f"الحالة: {res_reg.status_code}")
        print(f"الرد: {res_reg.json()}")
        assert res_reg.status_code in (201, 200)

        # ── Test 2: List Registered Faces ─────────────────────────────────────
        print("\n" + "─" * 50)
        print("📋 4. اختبار عرض قائمة الأشخاص المسجلين (GET /api/v1/faces/)")
        res_list = await client.get("/api/v1/faces/")
        print(f"الحالة: {res_list.status_code}")
        profiles_data = res_list.json()
        print(f"عدد المسجلين: {profiles_data['count']}")
        for p in profiles_data["profiles"]:
            print(f"  • {p['name']} | رابط الصورة: {p['photo_url']}")

        # ── Test 3: Face Recognition (1:N) ────────────────────────────────────
        print("\n" + "─" * 50)
        print("🔍 5. اختبار التعرف على الشخص في الصورة (POST /api/v1/faces/recognize)")
        files_rec = {"file": ("query.jpg", lena_bytes, "image/jpeg")}
        res_rec = await client.post("/api/v1/faces/recognize?threshold=0.45", files=files_rec)
        print(f"الحالة: {res_rec.status_code}")
        rec_data = res_rec.json()
        print(f"عدد الوجوه المكتشفة: {rec_data['detected_count']}")
        for f in rec_data["faces"]:
            print(f"  • الاسم: {f['name']}")
            print(f"  • هل هو معروف؟ {f['is_known']}")
            print(f"  • نسبة التشابه (Similarity): {f['similarity']}")
            print(f"  • دقة الاكتشاف (Confidence): {f['confidence']}")
            print(f"  • موقع الوجه (BBox): {f['bbox']}")

        assert rec_data["detected_count"] >= 1
        assert rec_data["faces"][0]["is_known"] is True
        assert rec_data["faces"][0]["name"] == "Lena Soderberg"

        # ── Test 4: Face Comparison (1:1 Verification) ────────────────────────
        print("\n" + "─" * 50)
        print("⚖️ 6. اختبار المقارنة بين صورتين (POST /api/v1/faces/compare)")
        # Download two distinct faces from UniFace verification dataset
        async with httpx.AsyncClient() as dl:
            curie_bytes = (await dl.get("https://raw.githubusercontent.com/yakhyo/uniface/main/assets/source/verify_curie.jpg")).content
            einstein_bytes = (await dl.get("https://raw.githubusercontent.com/yakhyo/uniface/main/assets/source/verify_einstein_1921.jpg")).content

        # Case A: Two DIFFERENT people (Curie vs Einstein)
        print("  [أ] مقارنة شخصين مختلفين (Marie Curie vs Albert Einstein):")
        res_diff = await client.post(
            "/api/v1/faces/compare?threshold=0.45",
            files={
                "image1": ("curie.jpg", curie_bytes, "image/jpeg"),
                "image2": ("einstein.jpg", einstein_bytes, "image/jpeg"),
            },
        )
        cmp_diff = res_diff.json()
        print(f"      • هل هما متطابقان؟ {cmp_diff['is_match']}")
        print(f"      • نسبة التشابه (Similarity): {cmp_diff['similarity']}")
        print(f"      • نسبة التطابق المئوية: {cmp_diff['match_percentage']}%")
        assert cmp_diff["is_match"] is False

        # Case B: The SAME person (Lena vs Lena)
        print("  [ب] مقارنة نفس الشخص (Same Person Verification):")
        res_same = await client.post(
            "/api/v1/faces/compare?threshold=0.45",
            files={
                "image1": ("lena1.jpg", lena_bytes, "image/jpeg"),
                "image2": ("lena2.jpg", lena_bytes, "image/jpeg"),
            },
        )
        cmp_same = res_same.json()
        print(f"      • هل هما متطابقان؟ {cmp_same['is_match']}")
        print(f"      • نسبة التشابه (Similarity): {cmp_same['similarity']}")
        print(f"      • نسبة التطابق المئوية: {cmp_same['match_percentage']}%")
        assert cmp_same["is_match"] is True


        # ── Test 5: Video Face Extraction ─────────────────────────────────────
        print("\n" + "─" * 50)
        print("🎥 7. اختبار استخراج أوضح الوجوه من الفيديو (POST /api/v1/faces/extract-from-video)")
        files_vid = {"file": ("test_vid.mp4", video_bytes, "video/mp4")}
        res_vid = await client.post(
            "/api/v1/faces/extract-from-video?sample_interval_sec=0.5&max_faces=3",
            files=files_vid,
        )
        print(f"الحالة: {res_vid.status_code}")
        vid_data = res_vid.json()
        print(f"عدد الوجوه المستخرجة: {vid_data['extracted_count']}")
        for idx, shot in enumerate(vid_data["faces"]):
            print(f"  [{idx+1}] التوقيت: {shot['formatted_time']} ({shot['timestamp_sec']}s)")
            print(f"      درجة النقاء (Sharpness): {shot['sharpness']}")
            print(f"      درجة الجودة المركبة: {shot['quality_score']}")
            print(f"      حجم BBox: {shot['bbox']}")
            print(f"      كود الصورة: {shot['crop_base64'][:40]}...")

        assert vid_data["extracted_count"] >= 1

        # ── Test 6: Register Face from Video ──────────────────────────────────
        print("\n" + "─" * 50)
        print("📹 8. اختبار التسجيل المباشر من الفيديو (POST /api/v1/faces/register-from-video)")
        files_reg_vid = {"file": ("test_vid.mp4", video_bytes, "video/mp4")}
        data_reg_vid = {"name": "Video Person", "sample_interval_sec": "0.5"}
        res_reg_vid = await client.post("/api/v1/faces/register-from-video", data=data_reg_vid, files=files_reg_vid)
        print(f"الحالة: {res_reg_vid.status_code}")
        print(f"الرد: {res_reg_vid.json()}")
        assert res_reg_vid.status_code in (201, 200)

        # ── Test 7: Cleanup ───────────────────────────────────────────────────
        print("\n" + "─" * 50)
        print("🧹 9. اختبار حذف الحسابات التجريبية (DELETE /api/v1/faces/{name})")
        res_del1 = await client.delete("/api/v1/faces/Lena Soderberg")
        print(f"حذف Lena: {res_del1.status_code} - {res_del1.json()}")
        res_del2 = await client.delete("/api/v1/faces/Video Person")
        print(f"حذف Video Person: {res_del2.status_code} - {res_del2.json()}")

    print("\n" + "=" * 70)
    print("🎉 جميع اختبارات الـ API الحية تمت بنجاح وبدقة 100%!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
