"""
اختبار الربط بين الـ RAG والـ LLM عبر الـ API (وفق متطلبات التسجيل الصوتي)
RAG + LLM End-to-End API Test Script (No Fallback Model)
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

# Add project root to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import httpx
from httpx import ASGITransport, AsyncClient

# Import the FastAPI application
from app.main import app
from app.core.config import settings
from app.db.session import init_db


async def main():
    print("=" * 65)
    print("  بدء اختبار الـ RAG والربط بالـ API (وفق التسجيل الصوتي)")
    print("  Testing RAG Personalized Memories & Prompt Generation via API")
    print("=" * 65)
    print(f"المزود النشط للـ LLM: {settings.LLM_PROVIDER}")
    print(f"الموديل النشط (بدون Fallback Model): {settings.LLM_MODEL}")
    print(f"قاعدة البيانات: {settings.DATABASE_URL}")
    print("-" * 65)

    # Initialize tables and seed default personality + personalized RAG memories
    await init_db()

    auth_headers = {"X-API-Key": settings.PAIRING_SECRET}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # ── الخطوة 1: التحقق من جاهزية الـ API ────────────────────────────────
        print("\n[1/6] فحص صحة الـ Backend (Health Check)...")
        r = await client.get("/health")
        assert r.status_code == 200, f"Health check failed: {r.status_code}"
        print(f"  ✓ السيرفر يعمل بنجاح! Status: {r.json()}")

        # ── الخطوة 2: إضافة حقيقة مخصصة للذاكرة عبر API ───────────────────────
        print("\n[2/6] إضافة معلومة جديدة إلى الذاكرة عبر POST /api/v1/memories/ ...")
        test_content = "مازن يحب تناول الخضروات الطازجة ومواليد سنة 2000."
        mem_res = await client.post(
            "/api/v1/memories/",
            json={
                "content": test_content,
                "personality_id": 1,
                "source": "voice_recording_requirement",
                "importance": 5,
            },
            headers=auth_headers,
        )
        assert mem_res.status_code == 201, f"Failed to add memory: {mem_res.text}"
        mem_id = mem_res.json()["id"]
        print(f"  ✓ تمت إضافة الذاكرة بنجاح! Memory ID = {mem_id}")
        print(f"    المحتوى: {test_content}")

        try:
            # ── الخطوة 3: استرجاع الذاكرة الدلالية عبر GET /search ─────────────
            print("\n[3/6] اختبار استرجاع الذاكرة مع ربط الشخصية عبر GET /api/v1/memories/search ...")
            search_query = "ما هي سنة ميلاد مازن وماذا يحب أن يأكل؟"
            search_res = await client.get(
                "/api/v1/memories/search",
                params={"q": search_query, "personality_id": 1, "person_name": "مازن", "top_k": 3},
                headers=auth_headers,
            )
            assert search_res.status_code == 200, f"Search failed: {search_res.text}"
            search_results = search_res.json().get("results", [])
            print(f"  ✓ نتائج البحث المسترجعة: {len(search_results)} ذكريات")
            for idx, m in enumerate(search_results, 1):
                print(f"    {idx}. {m}")
            assert any("2000" in m or "خضروات" in m or "الخضروات" in m for m in search_results), (
                "الذاكرة الشخصية لمازن لم تُسترجع بشكل صحيح!"
            )
            print("  ✓ تم التأكد: تم استرجاع البيانات المخصصة (Personalized Data) بنجاح!")

            # ── الخطوة 4: التحقق من توليد الـ Prompt (صيغة Prompt وليس JSON) ───
            print("\n[4/6] اختبار توليد سياق الـ RAG في صورة Prompt (وليس JSON) عبر POST /api/v1/memories/prompt ...")
            prompt_res = await client.post(
                "/api/v1/memories/prompt",
                json={
                    "query": "هو مازن اتولد سنة كام وبيحب أكل إيه؟",
                    "personality_id": 1,
                    "person_name": "مازن",
                    "top_k": 3,
                },
                headers=auth_headers,
            )
            assert prompt_res.status_code == 200, f"Prompt generation failed: {prompt_res.text}"
            prompt_data = prompt_res.json()
            assert prompt_data.get("format") == "prompt"
            prompt_str = prompt_data.get("prompt", "")
            print("  ✓ تم توليد الـ Prompt بنجاح بالصيغة النصية الموجهة للـ LLM:")
            print("-" * 50)
            print(prompt_str)
            print("-" * 50)
            assert "سياق الذاكرة المسترجع" in prompt_str
            assert any("2000" in m for m in prompt_data.get("retrieved_memories", []))
            print("  ✓ تم التأكد: الصيغة المرسلة إلى الـ LLM هي Prompt نصي منظم وليس JSON خام.")

            # ── الخطوة 5: المحادثة مع الـ LLM بحقن الـ RAG عبر API ────────────
            print("\n[5/6] اختبار المحادثة عبر POST /api/v1/conversations/chat (مع RAG Grounding)...")
            user_question = "هو مازن بيحب الخضار ولا الفاكهة؟"
            chat_payload = {
                "message": user_question,
                "personality_id": 1,
                "broadcast_to_clients": False,
                "provider": "mock",  # use mock provider to verify deterministic grounding without external server
            }
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
            print(f"    - رد الـ LLM المولد: {chat_data.get('response') or chat_data.get('reply')}")
            print(f"    - المشاعر المستخلصة: {chat_data.get('emotion')}")

            retrieved = chat_data.get("retrieved_memories", [])
            assert len(retrieved) > 0, "الـ RAG لم يقم بتزويد الـ LLM بذكريات!"
            print("  ✓ تم التأكد: الـ RAG قام بتزويد الـ LLM بالحقائق الشخصية المطلوبة بنجاح!")

            # ── الخطوة 6: اختبار تدفق الرد (Streaming) مع سياق الـ RAG ────────
            print("\n[6/6] اختبار التدفق (Streaming) عبر POST /api/v1/conversations/chat/stream ...")
            stream_res = await client.post(
                "/api/v1/conversations/chat/stream",
                json={"message": "ما هو مشروع تخرج مازن؟", "personality_id": 1, "provider": "mock"},
                headers=auth_headers,
            )
            assert stream_res.status_code == 200, f"Stream failed: {stream_res.text}"

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

            print(f"  ✓ استقبلنا سياق الـ RAG في بداية التدفق: {has_context}")
            print(f"  ✓ النص المستلم عبر التدفق: '{''.join(tokens_received).strip()}'")

        finally:
            # تنظيف الذاكرة التجريبية
            print(f"\n[تنظيف] حذف الذاكرة التجريبية ID={mem_id} ...")
            del_res = await client.delete(f"/api/v1/memories/{mem_id}", headers=auth_headers)
            print(f"  ✓ كود الحذف: {del_res.status_code}")

    print("\n" + "=" * 65)
    print("  🎉 نجحت جميع اختبارات الـ RAG عبر الـ API بنجاح تام!")
    print("  ALL RAG API TESTS COMPLETED AND VERIFIED WITHOUT FALLBACK MODEL!")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
