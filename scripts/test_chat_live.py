"""Live test script for the /api/v1/conversations/chat endpoint with local LLM."""

import asyncio
import sys
import uuid
import httpx

# Ensure proper utf-8 encoding on Windows console
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from app.main import app
from app.db.session import init_db


async def main():
    print("=" * 60)
    print("🚀 بدء اختبار الـ Chat Endpoint الحي مع الموديل المحلي Qwen2.5...")
    print("=" * 60)

    await init_db()

    session_id = f"live-chat-{uuid.uuid4().hex[:8]}"

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        # ── Turn 1 ────────────────────────────────────────────────────────────
        user_msg_1 = "أهلاً يا صديقي! أنا مازن، عرف نفسك باختصار بالمصري."
        print(f"\n👤 المستخدم: {user_msg_1}")
        print("⏳ جاري إرسال الطلب إلى POST /api/v1/conversations/chat ...")

        resp1 = await client.post(
            "/api/v1/conversations/chat",
            json={"message": user_msg_1, "session_id": session_id},
            timeout=30.0,
        )

        if resp1.status_code != 200:
            print(f"❌ خطأ: {resp1.status_code} - {resp1.text}")
            return

        data1 = resp1.json()
        print(f"🤖 رد الروبوت (Raw):     {data1['reply']}")
        print(f"🔊 رد الروبوت المُنظف:   {data1['cleaned_reply']}")
        print(f"😊 المشاعر المستخرجة:    {data1['emotion']}")
        print(f"⚡ زمن الاستجابة (LLM):  {data1['llm_latency_ms']} ms")
        print(f"🆔 Conversation ID:     {data1['conversation_id']}")

        # ── Turn 2 (Testing multi-turn history) ────────────────────────────────
        user_msg_2 = "فاكر اسمي إيه؟"
        print(f"\n👤 المستخدم: {user_msg_2}")
        print("⏳ جاري إرسال الطلب إلى نفس الجلسة للتأكد من الذاكرة الحوارية...")

        resp2 = await client.post(
            "/api/v1/conversations/chat",
            json={"message": user_msg_2, "session_id": session_id},
            timeout=30.0,
        )

        data2 = resp2.json()
        print(f"🤖 رد الروبوت (Raw):     {data2['reply']}")
        print(f"🔊 رد الروبوت المُنظف:   {data2['cleaned_reply']}")
        print(f"⚡ زمن الاستجابة (LLM):  {data2['llm_latency_ms']} ms")

        # ── Streaming Test ───────────────────────────────────────────────────
        user_msg_3 = "قولي نصيحة سريعة في البرمجة"
        print(f"\n👤 المستخدم (Streaming): {user_msg_3}")
        print("🤖 رد الروبوت المباشر (Tokens Stream): ", end="", flush=True)

        async with client.stream(
            "POST",
            "/api/v1/conversations/chat",
            json={"message": user_msg_3, "session_id": session_id, "stream": True},
            timeout=30.0,
        ) as stream_resp:
            async for chunk in stream_resp.aiter_text():
                print(chunk, end="", flush=True)
        print("\n\n✅ تم الانتهاء من الاختبار بنجاح تام!")


if __name__ == "__main__":
    asyncio.run(main())
