import asyncio
import os
os.environ["SENTENCE_TRANSFORMERS_OFFLINE"] = "1"
from httpx import AsyncClient, ASGITransport
from app.main import app

async def test_endpoints():
    print("=" * 60)
    print("🌐 اختبار جميع Endpoints الـ API عبر FastAPI مباشرة...")
    print("=" * 60)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. فحص الشخصيات
        resp = await client.get("/api/v1/personalities/")
        assert resp.status_code == 200, f"Error {resp.status_code}: {resp.text}"
        data = resp.json()
        p_list = data["personalities"]
        print(f"  • عدد الشخصيات المتاحة: {len(p_list)}")
        p_ids = [p["id"] for p in p_list]
        assert 0 in p_ids and 1 in p_ids and 2 in p_ids, f"شخصيات ناقصة: {p_ids}"
        print("  ✅ GET /personalities/ يعرض الشخصيات 0 و 1 و 2 بنجاح.")

        # 2. فحص استرجاع النبرة
        resp_tone = await client.get("/api/v1/personalities/2/tone")
        assert resp_tone.status_code == 200
        tone_data = resp_tone.json()
        print(f"  • نبرة شخصية أحمد (2): {tone_data['tone']} | الأسلوب: {tone_data['speaking_style']}")
        assert "tone" in tone_data and tone_data["tone"] != ""
        print("  ✅ GET /personalities/2/tone يسترجع النبرة وطريقة الكلام بنجاح.")

        # 3. فحص عرض الصورة
        resp_disp = await client.post("/api/v1/personalities/2/display-image")
        assert resp_disp.status_code == 200
        print(f"  • استجابة عرض الصورة: {resp_disp.json()['message']}")
        print("  ✅ POST /personalities/2/display-image يرسل أمر عرض الصورة بنجاح.")

        # 4. فحص استرجاع الذاكرة وتأكيد ظهور personality_id
        resp_mems = await client.get("/api/v1/memories/?personality_id=2")
        assert resp_mems.status_code == 200
        mems = resp_mems.json()["memories"]
        for m in mems:
            assert "personality_id" in m, "personality_id مفقود من استجابة الـ GET!"
            assert m["personality_id"] == 2, f"خطأ في عزل الذاكرة: {m}"
        print("  ✅ GET /memories/?personality_id=2 يعيد الذكريات مع personality_id وبعزل كامل.")

        # 5. فحص إضافة ذاكرة (POST)
        post_resp = await client.post("/api/v1/memories/", json={
            "content": "أحمد اشترى نظارة جديدة",
            "personality_id": 2,
            "importance": 6,
        })
        assert post_resp.status_code == 201, f"POST failed: {post_resp.text}"
        new_mid = post_resp.json()["id"]
        print(f"  • أضفنا معلومة جديدة بنجاح (ID: {new_mid})")

        # 6. فحص تعديل ذاكرة (PUT)
        put_resp = await client.put(f"/api/v1/memories/{new_mid}", json={
            "content": "أحمد اشترى نظارة شمسية ماركة ريبان",
            "importance": 7,
        })
        assert put_resp.status_code == 200, f"PUT failed: {put_resp.text}"
        assert "ريبان" in put_resp.json()["content"]
        print(f"  ✅ PUT /memories/{new_mid} عدل المعلومة واستبدلها بنجاح.")

        # 7. فحص حذف ذاكرة (DELETE by ID)
        del_resp = await client.delete(f"/api/v1/memories/{new_mid}")
        assert del_resp.status_code == 200, f"DELETE failed: {del_resp.text}"
        del_json = del_resp.json()
        assert del_json["status"] == "success"
        print(f"  ✅ DELETE /memories/{new_mid} مسح المعلومة بنجاح وأرجع تأكيداً: {del_json['message']}")

        # 8. فحص الحذف بالكلمة المفتاحية (POST /forget)
        # نضيف معلومة سريعة ثم نحذفها بـ forget
        temp_add = await client.post("/api/v1/memories/", json={
            "content": "أحمد مسافر إسكندرية يوم الخميس",
            "personality_id": 2,
        })
        forget_resp = await client.post("/api/v1/memories/forget", json={
            "query": "إسكندرية",
            "personality_id": 2,
        })
        assert forget_resp.status_code == 200
        f_json = forget_resp.json()
        assert f_json["deleted_count"] >= 1
        print(f"  ✅ POST /memories/forget مسح المعلومة بالبحث اللفظي بنجاح: {f_json['message']}")

    print("\n" + "=" * 60)
    print("🎉 جميع اختبارات الـ API (Endpoints) نجحت 100% بدون أي أخطاء!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_endpoints())
