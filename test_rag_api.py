"""
اختبار الربط بين الـ RAG والـ LLM عبر الـ API
RAG + LLM End-to-End API Test Script
"""

import asyncio
import json
import os
import sys

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx
from httpx import ASGITransport, AsyncClient

# Import the FastAPI application
from app.main import app
from app.core.config import settings


async def main():
    print("=" * 60)
    print("  بدء اختبار الربط بين الـ RAG والـ LLM عبر الـ API")
    print("  Testing RAG + LLM Integration via FastAPI Endpoints")
    print("=" * 60)
    print(f"المزود الحالي للـ LLM: {settings.LLM_PROVIDER}")
    print(f"قاعدة البيانات: {settings.DATABASE_URL}")
    print("-" * 60)

    auth_headers = {"X-API-Key": settings.PAIRING_SECRET}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # ── الخطوة 1: التحقق من جاهزية السيرفر ─────────────────────────────────
        print("\n[1/5] فحص صحة الـ Backend (Health Check)...")
        r = await client.get("/health")
        assert r.status_code == 200, f"Health check failed: {r.status_code}"
        print(f"  ✓ السيرفر يعمل بنجاح! Status: {r.json()}")

        # ── الخطوة 2: إضافة معلومة جديدة للذاكرة (RAG Memory Insertion) ────────
        print("\n[2/5] إضافة حقيقة جديدة إلى الذاكرة عبر POST /api/v1/memories/ ...")
        test_content = "الروبوت نيبولا يمتلك 12 محرك سيرفو فائق الدقة ومتصل بنظام أمان متقدم."
        mem_res = await client.post(
            "/api/v1/memories/",
            json={
                "content": test_content,
                "personality_id": 1,
                "source": "api_verification_test",
                "importance": 5,
            },
            headers=auth_headers,
        )
        assert mem_res.status_code == 201, f"Failed to add memory: {mem_res.text}"
        mem_id = mem_res.json()["id"]
        print(f"  ✓ تمت إضافة الذاكرة بنجاح! Memory ID = {mem_id}")
        print(f"    المحتوى: {test_content}")

        try:
            # ── الخطوة 3: اختبار استرجاع الذاكرة عبر RAG Search API ────────────
            print("\n[3/5] اختبار البحث الدلالي في الذاكرة عبر GET /api/v1/memories/search ...")
            search_query = "كم عدد محركات السيرفو الموجودة في نيبولا؟"
            search_res = await client.get(
                "/api/v1/memories/search",
                params={"q": search_query, "personality_id": 1, "top_k": 3},
                headers=auth_headers,
            )
            assert search_res.status_code == 200, f"Search failed: {search_res.text}"
            search_results = search_res.json().get("results", [])
            print(f"  ✓ نتائج البحث المسترجعة: {len(search_results)} ذكريات")
            for idx, m in enumerate(search_results, 1):
                print(f"    {idx}. {m}")
            assert any("12 محرك" in m for m in search_results), "الذاكرة لم تُسترجع في البحث!"

            # ── الخطوة 4: المحادثة مع الـ LLM مع ربط الـ RAG Context ───────────
            print("\n[4/5] اختبار استدعاء الـ LLM مع الـ RAG عبر POST /api/v1/conversations/chat ...")
            user_question = "كم محرك سيرفو يمتلك الروبوت نيبولا؟"
            chat_payload = {
                "message": user_question,
                "personality_id": 1,
                "broadcast_to_clients": False,
            }
            print(f"  السؤال المرسل: '{user_question}'")
            chat_res = await client.post(
                "/api/v1/conversations/chat",
                json=chat_payload,
                headers=auth_headers,
            )
            assert chat_res.status_code == 200, f"Chat failed: {chat_res.text}"
            chat_data = chat_res.json()

            print("  ✓ استجابة الـ API:")
            print(f"    - الـ Session ID: {chat_data.get('session_id')}")
            print(f"    - الذكريات المسترجعة (RAG Memories): {chat_data.get('retrieved_memories')}")
            print(f"    - رد الـ LLM المولد: {chat_data.get('response')}")
            print(f"    - المشاعر المستخلصة (Emotion): {chat_data.get('emotion')}")
            print(f"    - زمن الاستجابة (Latency): {chat_data.get('latency')}")

            # التحقق من أن الـ RAG زود الـ LLM بالذاكرة الصحيحة
            retrieved = chat_data.get("retrieved_memories", [])
            assert any("12 محرك" in m for m in retrieved), "الـ RAG لم يقم بتزويد الـ LLM بالسياق المطلوب!"
            print("  ✓ تم التأكد: الـ RAG استرجع الذاكرة المناسبة وحقنها في سياق الـ LLM بنجاح!")

            # ── الخطوة 5: اختبار الـ Streaming (Server-Sent Events) ───────────
            print("\n[5/5] اختبار تدفق الرد اللحظي عبر POST /api/v1/conversations/chat/stream ...")
            stream_res = await client.post(
                "/api/v1/conversations/chat/stream",
                json={"message": "أهلاً يا نيبولا", "personality_id": 1},
                headers=auth_headers,
            )
            assert stream_res.status_code == 200, f"Stream failed: {stream_res.text}"
            assert "text/event-stream" in stream_res.headers.get("content-type", "")

            tokens_received = []
            has_context = False
            for line in stream_res.text.split("\n"):
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if data.get("type") == "context":
                            has_context = True
                        elif data.get("type") == "token":
                            tokens_received.append(data.get("content", ""))
                    except Exception:
                        pass

            print(f"  ✓ استقبلنا سياق الـ RAG في البداية: {has_context}")
            print(f"  ✓ إجمالي عدد أجزاء التدفق (Tokens): {len(tokens_received)}")
            print(f"  ✓ النص المستلم عبر التدفق: '{''.join(tokens_received).strip()}'")

        finally:
            # تنظيف الذاكرة التجريبية
            await asyncio.sleep(0.3)
            print(f"\n[تنظيف] حذف الذاكرة التجريبية ID={mem_id} ...")
            del_res = await client.delete(f"/api/v1/memories/{mem_id}", headers=auth_headers)
            print(f"  ✓ كود الحذف: {del_res.status_code}")

    print("\n" + "=" * 60)
    print("  🎉 نجحت جميع اختبارات الربط بين الـ RAG والـ LLM عبر الـ API!")
    print("  ALL RAG + LLM API INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
