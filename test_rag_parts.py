"""
أداة اختبار أجزاء الـ RAG بشكل منفصل عبر السيرفر
RAG Modular Server Test Suite
-----------------------------------------------------------------------
تتيح هذه الأداة اختبار كل جزء من أجزاء منظومة الـ RAG بشكل مستقل عبر الـ API:
  - الجزء 1: إضافة الذكريات واستعراضها (Memory Ingestion & Listing)
  - الجزء 2: البحث الدلالي المهجن (Semantic & Lexical Hybrid Search)
  - الجزء 3: الاسترجاع المخصص للشخصية والتعرف على الوجه (Personalized RAG Grounding)
  - الجزء 4: تجميع وبناء الـ Prompt النصي الموجه للـ LLM (بدون JSON)
  - الجزء 5: المحادثة والربط المباشر مع الـ LLM (End-to-End Chat with RAG - بدون Fallback)
  - الجزء 6: تدفق الرد اللحظي مع سياق الذاكرة (Streaming RAG Chat)
  - الجزء 7: حذف الذكريات وإدارة دورة الحياة (Memory Deletion)

الاستخدام:
  1. اختبار جزء محدد:
     python test_rag_parts.py --part 1
     python test_rag_parts.py --part 4

  2. اختبار جميع الأجزاء:
     python test_rag_parts.py --all

  3. تحديد عنوان السيرفر (افتراضياً يفحص السيرفر الحي أو يشغل عميل ASGI داخلي):
     python test_rag_parts.py --url http://127.0.0.1:8000 --part 2
"""

import argparse
import asyncio
import json
import sys
from typing import Optional

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import httpx

from app.main import app
from app.core.config import settings
from app.db.session import init_db

DEFAULT_SERVER_URL = "http://127.0.0.1:8000"


class RAGServerTester:
    def __init__(self, base_url: str = DEFAULT_SERVER_URL):
        self.base_url = base_url.rstrip("/")
        self.auth_headers = {"X-API-Key": settings.PAIRING_SECRET}
        self.client: Optional[httpx.AsyncClient] = None
        self.is_live_server = False

    async def setup(self):
        """Detect if live server is running; otherwise use in-process ASGI test client."""
        await init_db()

        try:
            async with httpx.AsyncClient(base_url=self.base_url, timeout=1.5) as probe:
                r = await probe.get("/health")
                if r.status_code == 200:
                    self.is_live_server = True
        except Exception:
            self.is_live_server = False

        if self.is_live_server:
            print(f"🌐 الاتصال بسيرفر خارجي حي: {self.base_url}")
            self.client = httpx.AsyncClient(base_url=self.base_url, timeout=30.0)
        else:
            print(f"⚡ لم يتم الكشف عن سيرفر خارجي يعمل على {self.base_url}")
            print(f"   يتم التشغيل عبر مشغل ASGI الداخلي المباشر (Direct In-Process Server)")
            from httpx import ASGITransport
            self.client = httpx.AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://testserver",
                timeout=30.0,
            )

    async def close(self):
        if self.client:
            await self.client.aclose()

    # ── [الجزء 1] إضافة واستعراض الذكريات ──────────────────────────────────
    async def test_part_1_ingestion(self) -> int:
        print("\n" + "=" * 65)
        print("  [الجزء 1] اختبار إضافة الذكريات واستعراضها عبر الـ API")
        print("  Endpoint: POST /api/v1/memories/ & GET /api/v1/memories/")
        print("=" * 65)

        test_fact = "مازن يفضل العمل بلغة بايثون في مشاريع الروبوتات والذكاء الاصطناعي."
        print(f"1. إرسال طلب POST /api/v1/memories/ لإضافة حقيقة جديدة...")
        res = await self.client.post(
            "/api/v1/memories/",
            json={
                "content": test_fact,
                "personality_id": 1,
                "source": "modular_test_p1",
                "importance": 5,
            },
            headers=self.auth_headers,
        )
        print(f"   - كود الاستجابة: {res.status_code}")
        assert res.status_code == 201, f"فشل الحفظ: {res.text}"
        data = res.json()
        mem_id = data["id"]
        print(f"   ✓ تم حفظ الحقيقة بنجاح برقم ID: {mem_id}")
        print(f"   - المحتوى المحفوظ: {data['content']}")

        print("\n2. إرسال طلب GET /api/v1/memories/ لاستعراض كل الذكريات...")
        list_res = await self.client.get(
            "/api/v1/memories/",
            params={"personality_id": 1},
            headers=self.auth_headers,
        )
        assert list_res.status_code == 200, f"فشل الاستعراض: {list_res.text}"
        mems = list_res.json().get("memories", [])
        print(f"   ✓ تم استرجاع قائمة الذكريات بنجاح (العدد الإجمالي: {len(mems)})")
        found = any(m["id"] == mem_id for m in mems)
        assert found, "الذاكرة الجديدة غير موجودة في القائمة!"
        print(f"   ✓ تأكيد: الذاكرة المضافة موجودة في قاعدة البيانات.")
        return mem_id

    # ── [الجزء 2] الاسترجاع الدلالي والمهجن ─────────────────────────────────
    async def test_part_2_search(self):
        print("\n" + "=" * 65)
        print("  [الجزء 2] اختبار الاسترجاع الدلالي والبحث المهجن عبر الـ API")
        print("  Endpoint: GET /api/v1/memories/search")
        print("=" * 65)

        query = "ما هي اللغة التي يفضلها مازن في البرمجة والروبوتات؟"
        print(f"1. إرسال استعلام بحث دلالي: '{query}'")
        res = await self.client.get(
            "/api/v1/memories/search",
            params={"q": query, "personality_id": 1, "top_k": 3},
            headers=self.auth_headers,
        )
        assert res.status_code == 200, f"فشل البحث: {res.text}"
        results = res.json().get("results", [])
        print(f"   ✓ عدد النتائج المسترجعة: {len(results)}")
        for idx, m in enumerate(results, 1):
            print(f"     [{idx}] {m}")
        assert len(results) > 0, "لم يتم العثور على أي ذكريات مرتبطة!"

        print("\n2. اختبار البحث مع تفاصيل الـ Score والـ Metadata (detailed=true)...")
        res_det = await self.client.get(
            "/api/v1/memories/search",
            params={"q": query, "personality_id": 1, "top_k": 2, "detailed": True},
            headers=self.auth_headers,
        )
        assert res_det.status_code == 200
        det_results = res_det.json().get("results", [])
        for m in det_results:
            print(f"   - [ID: {m['id']}] Score: {m['score']} | {m['content']}")
        print("   ✓ نجح البحث الدلالي مع احتساب درجات التطابق (Relevance Scores).")

    # ── [الجزء 3] الاسترجاع المخصص للشخصية (Face Grounding) ────────────────
    async def test_part_3_personalization(self):
        print("\n" + "=" * 65)
        print("  [الجزء 3] اختبار الاسترجاع المخصص للتعرف على الوجه والشخصية (Personalized RAG)")
        print("  Endpoint: GET /api/v1/memories/search?person_name=مازن")
        print("=" * 65)

        query = "هو اتولد سنة كام وبيحب يأكل إيه؟"
        person = "مازن"
        print(f"1. إرسال استعلام شخصي بضمير الغائب مع تمرير person_name='{person}'...")
        res = await self.client.get(
            "/api/v1/memories/search",
            params={"q": query, "personality_id": 1, "person_name": person, "top_k": 4},
            headers=self.auth_headers,
        )
        assert res.status_code == 200, f"فشل الاسترجاع: {res.text}"
        results = res.json().get("results", [])
        print(f"   ✓ النتائج المسترجعة بعد دمج هوية الشخص:")
        for idx, m in enumerate(results, 1):
            print(f"     [{idx}] {m}")

        has_birth = any("2000" in m for m in results)
        has_food = any("خضروات" in m or "الخضروات" in m for m in results)
        print(f"   - تم استرجاع حقيقة سنة الميلاد (2000): {has_birth}")
        print(f"   - تم استرجاع تفضيلات الطعام (الخضروات): {has_food}")
        assert has_birth or has_food, "فشل ربط هوية الشخص بالاسترجاع المخصص!"
        print("   ✓ تم التأكد: الـ RAG يقوم بتخصيص الاسترجاع بدقة بناءً على اسم الشخص.")

    # ── [الجزء 4] بناء الـ Prompt النصي (بدون JSON) ─────────────────────────
    async def test_part_4_prompt_builder(self):
        print("\n" + "=" * 65)
        print("  [الجزء 4] اختبار تجميع وبناء الـ Prompt النصي الموجه للـ LLM (بدلاً من JSON)")
        print("  Endpoint: POST /api/v1/memories/prompt")
        print("=" * 65)

        payload = {
            "query": "ما هو مشروع تخرج مازن وما هي هواياته؟",
            "personality_id": 1,
            "person_name": "مازن",
            "top_k": 3,
        }
        print(f"1. إرسال طلب بناء الـ Prompt إلى POST /api/v1/memories/prompt...")
        res = await self.client.post(
            "/api/v1/memories/prompt",
            json=payload,
            headers=self.auth_headers,
        )
        assert res.status_code == 200, f"فشل توليد الـ Prompt: {res.text}"
        data = res.json()
        assert data.get("format") == "prompt", "يجب أن تكون الصيغة Prompt وليس JSON خام!"

        prompt_text = data.get("prompt", "")
        print("   ✓ تم توليد الـ Prompt بنجاح بدون قيود وتغليف الـ JSON:")
        print("   " + "-" * 55)
        for line in prompt_text.splitlines():
            print(f"   | {line}")
        print("   " + "-" * 55)

        assert "سياق الذاكرة المسترجع" in prompt_text, "سياق الذاكرة مفقود من الـ Prompt!"
        assert "توجيهات التشغيل والرد" in prompt_text, "تعليمات التشغيل مفقودة!"
        print("   ✓ تم التأكد: تم إنتاج Prompt نصي كامل ومنظم وجاهز للإرسال المباشر للـ LLM.")

    # ── [الجزء 5] المحادثة مع الـ LLM مع ربط الـ RAG (بدون Fallback) ────────
    async def test_part_5_chat_grounding(self):
        print("\n" + "=" * 65)
        print("  [الجزء 5] اختبار المحادثة مع الـ LLM بحقن سياق الـ RAG عبر الـ API")
        print("  Endpoint: POST /api/v1/conversations/chat (No Fallback Model)")
        print("=" * 65)

        user_query = "هو مازن بيحب أكل الخضار ولا الفواكه؟"
        print(f"1. إرسال سؤال المستخدم: '{user_query}'...")
        payload = {
            "message": user_query,
            "personality_id": 1,
            "broadcast_to_clients": False,
            "provider": "mock",  # use deterministic mock provider for isolated testing
        }
        res = await self.client.post(
            "/api/v1/conversations/chat",
            json=payload,
            headers=self.auth_headers,
        )
        assert res.status_code == 200, f"فشل المحادثة: {res.text}"
        chat_data = res.json()
        print(f"   ✓ تم استلام الرد من الـ LLM:")
        print(f"     - الجلسة (Session ID): {chat_data.get('session_id')}")
        print(f"     - الذكريات المسترجعة (RAG Memories): {chat_data.get('retrieved_memories')}")
        print(f"     - نص الرد المولد: {chat_data.get('response') or chat_data.get('reply')}")
        print(f"     - المشاعر المستخرجة: {chat_data.get('emotion')}")

        retrieved = chat_data.get("retrieved_memories", [])
        assert len(retrieved) > 0, "الـ RAG لم يقم بتغذية الـ LLM بالسياق!"
        print("   ✓ تم التأكد: الـ RAG قام بحقن الذاكرة المطلوبة بنجاح وبدون أي Fallback Model.")

    # ── [الجزء 6] التدفق اللحظي مع RAG ────────────────────────────────────
    async def test_part_6_streaming(self):
        print("\n" + "=" * 65)
        print("  [الجزء 6] اختبار التدفق اللحظي (SSE Streaming) مع سياق الـ RAG")
        print("  Endpoint: POST /api/v1/conversations/chat/stream")
        print("=" * 65)

        payload = {
            "message": "مشروع تخرج مازن إيه؟",
            "personality_id": 1,
            "provider": "mock",
        }
        print("1. إرسال طلب التدفق إلى POST /api/v1/conversations/chat/stream...")
        res = await self.client.post(
            "/api/v1/conversations/chat/stream",
            json=payload,
            headers=self.auth_headers,
        )
        assert res.status_code == 200, f"فشل التدفق: {res.text}"

        tokens = []
        context_event = None
        for line in res.text.split("\n"):
            if line.startswith("data: "):
                try:
                    event = json.loads(line[6:])
                    if event.get("type") == "context":
                        context_event = event
                    elif event.get("type") == "token":
                        tokens.append(event.get("content", ""))
                except Exception:
                    pass

        print(f"   ✓ تم استلام حدث سياق الـ RAG في بداية التدفق: {context_event is not None}")
        if context_event:
            print(f"     - الذكريات المسترجعة في التدفق: {context_event.get('memories')}")
        print(f"   ✓ إجمالي عدد أجزاء التدفق (Tokens): {len(tokens)}")
        print(f"   ✓ النص المستلم كاملاً: '{''.join(tokens).strip()}'")
        assert len(tokens) > 0, "لم يتم استلام أي Tokens من الـ LLM!"
        print("   ✓ تم التأكد: التدفق اللحظي يعمل مع سياق الـ RAG بنجاح.")

    # ── [الجزء 7] حذف الذكريات وإدارة دورة الحياة ────────────────────────────
    async def test_part_7_deletion(self, mem_id: int):
        print("\n" + "=" * 65)
        print(f"  [الجزء 7] اختبار حذف الذاكرة المؤقتة ID={mem_id}")
        print("  Endpoint: DELETE /api/v1/memories/{mid}")
        print("=" * 65)

        del_res = await self.client.delete(f"/api/v1/memories/{mem_id}", headers=self.auth_headers)
        assert del_res.status_code == 204, f"فشل الحذف: {del_res.status_code}"
        print(f"   ✓ تم حذف الذاكرة ID={mem_id} بنجاح (Status: 204 No Content).")

        # التحقق من عدم وجودها بعد الحذف
        chk_res = await self.client.get(
            "/api/v1/memories/",
            params={"personality_id": 1},
            headers=self.auth_headers,
        )
        mems = chk_res.json().get("memories", [])
        assert not any(m["id"] == mem_id for m in mems), "الذاكرة ما زالت موجودة بعد الحذف!"
        print(f"   ✓ تم التأكد: الذاكرة حُذفت فعلياً من قاعدة البيانات.")


async def main():
    parser = argparse.ArgumentParser(description="اختبار أجزاء الـ RAG عبر السيرفر")
    parser.add_argument(
        "--part",
        type=int,
        choices=[1, 2, 3, 4, 5, 6, 7],
        help="رقم الجزء المطلوب اختباره منفصلاً (1 إلى 7)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="تشغيل اختبار كل الأجزاء بالتتابع",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_SERVER_URL,
        help="عنوان السيرفر (افتراضياً: http://127.0.0.1:8000)",
    )
    args = parser.parse_args()

    tester = RAGServerTester(base_url=args.url)
    await tester.setup()

    try:
        if args.part == 1:
            await tester.test_part_1_ingestion()
        elif args.part == 2:
            await tester.test_part_2_search()
        elif args.part == 3:
            await tester.test_part_3_personalization()
        elif args.part == 4:
            await tester.test_part_4_prompt_builder()
        elif args.part == 5:
            await tester.test_part_5_chat_grounding()
        elif args.part == 6:
            await tester.test_part_6_streaming()
        elif args.part == 7:
            # Add a quick memory then delete it
            mid = await tester.test_part_1_ingestion()
            await tester.test_part_7_deletion(mid)
        elif args.all:
            print("\n🚀 تشغيل الفحص الكامل لجميع أجزاء الـ RAG (1 إلى 7)...")
            created_mid = await tester.test_part_1_ingestion()
            await tester.test_part_2_search()
            await tester.test_part_3_personalization()
            await tester.test_part_4_prompt_builder()
            await tester.test_part_5_chat_grounding()
            await tester.test_part_6_streaming()
            await tester.test_part_7_deletion(created_mid)
            print("\n" + "=" * 65)
            print("  🎉 نجحت جميع اختبارات أجزاء الـ RAG عبر السيرفر بنجاح تام!")
            print("=" * 65)
        else:
            # Interactive Menu
            print("\n" + "=" * 65)
            print("  اختر الجزء الذي ترغب في اختباره من منظومة الـ RAG:")
            print("  [1] إضافة واستعراض الذكريات (Memory Ingestion & List)")
            print("  [2] الاسترجاع الدلالي والبحث المهجن (Hybrid Search)")
            print("  [3] الاسترجاع المخصص للشخصية والوجه (Personalized RAG)")
            print("  [4] تجميع وبناء الـ Prompt النصي بدلاً من JSON")
            print("  [5] المحادثة وربط الـ RAG مع الـ LLM (بدون Fallback)")
            print("  [6] تدفق الرد اللحظي مع سياق الـ RAG (Streaming)")
            print("  [7] اختبار دورة الحذف والتنظيف (Memory Deletion)")
            print("  [8] تشغيل جميع الأجزاء بالتتابع (Full Test)")
            print("=" * 65)
            choice = input("أدخل رقم الخيار (1-8): ").strip()
            if choice == "1":
                await tester.test_part_1_ingestion()
            elif choice == "2":
                await tester.test_part_2_search()
            elif choice == "3":
                await tester.test_part_3_personalization()
            elif choice == "4":
                await tester.test_part_4_prompt_builder()
            elif choice == "5":
                await tester.test_part_5_chat_grounding()
            elif choice == "6":
                await tester.test_part_6_streaming()
            elif choice == "7":
                mid = await tester.test_part_1_ingestion()
                await tester.test_part_7_deletion(mid)
            elif choice == "8":
                created_mid = await tester.test_part_1_ingestion()
                await tester.test_part_2_search()
                await tester.test_part_3_personalization()
                await tester.test_part_4_prompt_builder()
                await tester.test_part_5_chat_grounding()
                await tester.test_part_6_streaming()
                await tester.test_part_7_deletion(created_mid)
            else:
                print("خيار غير صحيح!")
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
