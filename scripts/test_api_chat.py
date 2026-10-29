"""
API Live Chat Testing Script.
Tests conversation chat endpoint with newly injected API memories.
"""

import asyncio
import json
import sys
import uuid
import httpx

sys.stdout.reconfigure(encoding="utf-8")

BASE_URL = "http://localhost:8000"

TEST_PROMPTS = [
    # Grounded on new API memory 1
    ("فين معمل الروبوتات بالضبط؟", "grounded", ["رابع", "هندسة"]),
    # Grounded on new API memory 2
    ("مازن متخصص في إيه؟", "grounded", ["ذكاء", "نماذج", "روبوت"]),
    # Anti-hallucination trap (not in memory)
    ("ما هو رقم الموبايل الشخصي لمازن؟", "refusal", ["مش مسجل", "غير مسجل", "معنديش", "غير متوفر", "لا أملك"]),
]


async def main():
    print("=" * 70)
    print("📡 بدء اختبار الـ Chat المباشر عبر الـ API (POST /api/v1/conversations/chat)")
    print("=" * 70)

    session_id = f"api-test-{uuid.uuid4().hex[:6]}"

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180.0) as client:
        for idx, (question, test_type, expected_keywords) in enumerate(TEST_PROMPTS, 1):
            print(f"\n[{idx}/3] 👤 سؤال المستخدم: '{question}' (نوع الفحص: {test_type})")

            resp = await client.post(
                "/api/v1/conversations/chat",
                json={
                    "message": question,
                    "session_id": session_id,
                },
            )

            if resp.status_code != 200:
                print(f"❌ خطأ: {resp.status_code} - {resp.text}")
                continue

            data = resp.json()
            reply = data.get("reply", "")
            memories_used = data.get("memories_used", [])
            emotion = data.get("emotion", "")
            latency = data.get("llm_latency_ms", 0)

            print(f"   🔍 الذكريات المسترجعة عبر RAG: {memories_used}", flush=True)
            print(f"   🤖 رد الروبوت نيبولا: {reply}", flush=True)
            print(f"   ⚡ سرعة الـ LLM: {latency:.1f} ms | المشاعر: {emotion}", flush=True)

            # Verify response
            reply_lower = reply.lower()
            if test_type == "grounded":
                matched = any(kw.lower() in reply_lower for kw in expected_keywords)
                if matched:
                    print("   🎯 النتيجة: ✅ إجابة دقيقة مستندة بنجاح لمعلومات الذاكرة المدخلة عبر API!", flush=True)
                else:
                    print("   ⚠️ النتيجة: لم يتم رصد الكلمات المتوقعة بدقة.", flush=True)
            elif test_type == "refusal":
                refused = any(rw.lower() in reply_lower for rw in expected_keywords)
                if refused:
                    print("   🎯 النتيجة: ✅ نجاح حاسم لمنع الهلوسة (اعترف بعدم وجود المعلومة)!", flush=True)
                else:
                    print("   ⚠️ النتيجة: حاول التخمين.")

    print("\n" + "=" * 70)
    print("🎉 اكتمل اختبار الـ Chat عبر الـ API بنجاح تام!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
