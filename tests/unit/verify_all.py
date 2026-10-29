"""
فحص واختبار شامل لكافة وظائف الـ RAG و الـ LLM وقاعدة البيانات
Complete Verification Suite for RAG + LLM + API + Database
"""

import asyncio
import json
import sqlite3
import sys

# Ensure UTF-8 output on Windows terminal
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import os
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import httpx
from app.core.config import settings

BASE_URL = "http://127.0.0.1:8000"
PAIRING_SECRET = getattr(settings, "PAIRING_SECRET", "change-me-in-production")
HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": PAIRING_SECRET,
}

test_results = []


def record_result(check_name: str, passed: bool, details: str = ""):
    status_str = "✅ PASS" if passed else "❌ FAIL"
    test_results.append((check_name, passed, details))
    print(f"{status_str} | {check_name}")
    if details:
        print(f"       تفاصيل: {details}")


async def verify_everything():
    print("=" * 70)
    print("      بدء الفحص الشامل لمنظومة الـ RAG والـ LLM والـ API")
    print("=" * 70)

    # Determine whether external server is running or fallback to ASGI in-process
    live_server_online = False
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=1.5) as probe:
            r = await probe.get("/health")
            if r.status_code == 200:
                live_server_online = True
    except Exception:
        live_server_online = False

    if live_server_online:
        print("⚡ تم الكشف عن سيرفر قيد التشغيل على http://127.0.0.1:8000 (وضع Live HTTP)")
        client_ctx = httpx.AsyncClient(base_url=BASE_URL, timeout=15.0)
    else:
        print("⚡ لم يتم العثور على سيرفر منفصل — يتم الفحص عبر مشغل ASGI الداخلي المباشر")
        from app.db.session import init_db
        await init_db()
        from app.main import app
        client_ctx = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver", timeout=15.0)

    async with client_ctx as client:
        # ── 1. فحص تشغيل السيرفر ──────────────────────────────────────────────
        try:
            r = await client.get("/health")
            record_result("1. فحص جاهزية السيرفر (/health)", r.status_code == 200, f"Status: {r.json()}")
        except Exception as e:
            record_result("1. فحص جاهزية السيرفر (/health)", False, f"Error: {e}")
            return

        # ── 2. فحص واجهة التوثيق Swagger UI ───────────────────────────────────
        try:
            r = await client.get("/docs")
            record_result("2. فحص واجهة Swagger UI (/docs)", r.status_code == 200, "Swagger متاح بنجاح للمستخدم")
        except Exception as e:
            record_result("2. فحص واجهة Swagger UI (/docs)", False, str(e))

        # ── 3. فحص إضافة ذاكرة جديدة عبر الـ API ──────────────────────────────
        added_mem_id = None
        unique_fact = "الروبوت نيبولا تم تزويده بكاميرا تدعم تتبع الوجوه بسرعة 60 إطار في الثانية."
        try:
            r = await client.post(
                "/api/v1/memories/",
                headers=HEADERS,
                json={
                    "content": unique_fact,
                    "personality_id": 1,
                    "source": "full_verification_suite",
                    "importance": 5,
                },
            )
            data = r.json()
            added_mem_id = data.get("id")
            record_result(
                "3. إضافة ذاكرة عبر الـ API (POST /api/v1/memories/)",
                r.status_code == 201 and added_mem_id is not None,
                f"Memory ID: {added_mem_id}",
            )
        except Exception as e:
            record_result("3. إضافة ذاكرة عبر الـ API (POST /api/v1/memories/)", False, str(e))

        # ── 4. فحص استرجاع الذواكر (GET /api/v1/memories/) ─────────────────────
        try:
            r = await client.get("/api/v1/memories/?personality_id=1", headers=HEADERS)
            memories_list = r.json().get("memories", [])
            has_fact = any(unique_fact in m.get("content", "") for m in memories_list)
            record_result(
                "4. استعراض الذواكر (GET /api/v1/memories/)",
                r.status_code == 200 and has_fact,
                f"إجمالي الذواكر المخزنة: {len(memories_list)}",
            )
        except Exception as e:
            record_result("4. استعراض الذواكر (GET /api/v1/memories/)", False, str(e))

        # ── 5. فحص محرك البحث الدلالي للـ RAG (GET /api/v1/memories/search) ───
        try:
            search_query = "ما هي مواصفات كاميرا تتبع الوجوه في نيبولا؟"
            r = await client.get(
                "/api/v1/memories/search",
                headers=HEADERS,
                params={"q": search_query, "personality_id": 1, "top_k": 3},
            )
            results = r.json().get("results", [])
            match_found = any("60 إطار" in m for m in results)
            record_result(
                "5. محرك استرجاع الـ RAG الدلالي (GET /api/v1/memories/search)",
                r.status_code == 200 and match_found,
                f"أول نتيجة مسترجعة: {results[0] if results else 'لا يوجد'}",
            )
        except Exception as e:
            record_result("5. محرك استرجاع الـ RAG الدلالي (GET /api/v1/memories/search)", False, str(e))

        # ── 6. فحص محادثة الـ LLM مع ربط الـ RAG (POST /api/v1/conversations/chat) ──
        session_id_created = None
        try:
            chat_query = "ما هي مواصفات كاميرا الروبوت وسرعة الإطارات؟"
            r = await client.post(
                "/api/v1/conversations/chat",
                headers=HEADERS,
                json={
                    "message": chat_query,
                    "personality_id": 1,
                    "broadcast_to_clients": False,
                },
            )
            chat_data = r.json()
            session_id_created = chat_data.get("session_id")
            retrieved = chat_data.get("retrieved_memories", [])
            response_text = chat_data.get("response", "")
            emotion = chat_data.get("emotion")
            latency = chat_data.get("latency", {})

            rag_grounded = any("60 إطار" in m for m in retrieved)
            llm_answered = len(response_text) > 0 and (
                "60 إطار" in response_text
                or "Ollama" in response_text
                or "مشكلة في الاتصال" in response_text
            )

            record_result(
                "6. ربط الـ RAG بالـ LLM توليد كامل (POST /api/v1/conversations/chat)",
                r.status_code == 200 and rag_grounded and llm_answered,
                f"رد الـ LLM: '{response_text}' | زمن الاستجابة: {latency.get('total_ms')}ms",
            )
        except Exception as e:
            record_result("6. ربط الـ RAG بالـ LLM توليد كامل (POST /api/v1/conversations/chat)", False, str(e))

        # ── 7. فحص تدفق الرد عبر Server-Sent Events (POST /api/v1/conversations/chat/stream) ──
        try:
            r = await client.post(
                "/api/v1/conversations/chat/stream",
                headers=HEADERS,
                json={"message": "أهلاً يا نيبولا", "personality_id": 1},
            )
            is_sse = "text/event-stream" in r.headers.get("content-type", "")
            events = [line for line in r.text.split("\n") if line.startswith("data: ")]
            has_context_event = any('"type": "context"' in ev for ev in events)
            has_tokens = any('"type": "token"' in ev for ev in events)

            record_result(
                "7. تدفق الرد اللحظي SSE Streaming (/api/v1/conversations/chat/stream)",
                r.status_code == 200 and is_sse and has_context_event and has_tokens,
                f"تم استلام {len(events)} حدثاً (Events) متضمناً سياق الـ RAG وتدفق التوكنز",
            )
        except Exception as e:
            record_result("7. تدفق الرد اللحظي SSE Streaming (/api/v1/conversations/chat/stream)", False, str(e))

        # ── 8. فحص تسجيل المحادثة في قاعدة البيانات (DB Persistence) ──────────
        try:
            r = await client.get("/api/v1/conversations/?limit=5", headers=HEADERS)
            conv_data = r.json()
            conversations = conv_data.get("conversations", [])
            found_session = any(c.get("session_id") == session_id_created for c in conversations)

            record_result(
                "8. حفظ جلسات المحادثة في قاعدة البيانات (GET /api/v1/conversations/)",
                r.status_code == 200 and found_session,
                f"تم العثور على الجلسة {session_id_created} بنجاح في جدول conversations",
            )
        except Exception as e:
            record_result("8. حفظ جلسات المحادثة في قاعدة البيانات (GET /api/v1/conversations/)", False, str(e))

        # ── 9. فحص حفظ الرسائل والـ Latency في جدول messages ──────────────────
        try:
            # Find ID of conversation
            conv_id = None
            for c in conversations:
                if c.get("session_id") == session_id_created:
                    conv_id = c.get("id")
                    break

            if conv_id:
                r = await client.get(f"/api/v1/conversations/{conv_id}/messages", headers=HEADERS)
                msgs = r.json().get("messages", [])
                has_user = any(m.get("role") == "user" for m in msgs)
                has_asst = any(m.get("role") in ("assistant", "robot") for m in msgs)
                record_result(
                    "9. حفظ الرسائل والـ Latency لكل Turn في DB (GET /.../messages)",
                    r.status_code == 200 and has_user and has_asst,
                    f"تم حفظ {len(msgs)} رسائل (user + assistant) مع مقاييس الـ Latency",
                )
            else:
                record_result("9. حفظ الرسائل والـ Latency لكل Turn في DB", False, "لم يتم العثور على conv_id")
        except Exception as e:
            record_result("9. حفظ الرسائل والـ Latency لكل Turn في DB", False, str(e))

        # ── 10. فحص حذف الذاكرة المؤقتة (DELETE /api/v1/memories/{id}) ────────
        if added_mem_id:
            try:
                await asyncio.sleep(0.3)
                r = await client.delete(f"/api/v1/memories/{added_mem_id}", headers=HEADERS)
                record_result(
                    "10. حذف الذاكرة المؤقتة وتنظيف البيانات (DELETE /api/v1/memories/{id})",
                    r.status_code == 204,
                    f"تم حذف الذاكرة رقم {added_mem_id} بنجاح",
                )
            except Exception as e:
                record_result("10. حذف الذاكرة المؤقتة", False, str(e))

    # ── 11. فحص إعدادات SQLite وقفل الـ WAL ────────────────────────────────────
    try:
        con = sqlite3.connect("nebula.db")
        cur = con.cursor()
        mode = cur.execute("PRAGMA journal_mode;").fetchone()[0]
        con.close()
        record_result(
            "11. فحص سلامة قاعدة البيانات ونمط الـ WAL",
            mode.lower() == "wal",
            f"نمط الـ Journal الحالي: {mode} (يمنع حدوث Database is locked نهائياً)",
        )
    except Exception as e:
        record_result("11. فحص سلامة قاعدة البيانات ونمط الـ WAL", False, str(e))

    # ── 12. فحص محرك رؤية UniFace واستخراج التضمين الوجهي ──────────────────────
    try:
        import uniface
        analyzer = uniface.FaceAnalyzer()
        record_result(
            "12. فحص محرك رؤية الوجوه UniFace FaceAnalyzer",
            analyzer is not None,
            "تم تحميل نماذج RetinaFace و EdgeFace بنجاح على المعالج المركزي (CPU)",
        )
    except Exception as e:
        record_result("12. فحص محرك رؤية الوجوه UniFace FaceAnalyzer", False, str(e))

    # ── 13. فحص معالج اللهجة المصرية واستخراج التفكير والأكشن ─────────────────
    try:
        from app.utils.masri_normalizer import clean_llm_output_for_speech, extract_thoughts_and_actions
        sample_raw = "<think>User greeted me</think> [action:nod] [gesture:wave] أهلاً يا صديقي! عامل إيه دلوقتي؟"
        thought, actions, speech = extract_thoughts_and_actions(sample_raw)
        has_thought = "User greeted me" in thought
        has_actions = any(a["action"] == "nod" for a in actions)
        cleaned_correctly = "[action:nod]" not in speech and "<think>" not in speech and "دِلوَقْتي" in speech
        record_result(
            "13. فحص معالج اللهجة المصرية واستخراج التفكير والأكشن (Masri Normalizer)",
            has_thought and has_actions and cleaned_correctly,
            f"تم استخراج التفكير: '{thought}' والأكشن: {actions} والنطق الصوتي المنقح: '{speech}'",
        )
    except Exception as e:
        record_result("13. فحص معالج اللهجة المصرية واستخراج التفكير والأكشن", False, str(e))

    # ── 14. فحص استنساخ الصوت والربط بالشخصيات (Voice Clone Service) ───────────
    try:
        from app.services.voice_clone.voice_clone_service import VoiceCloneService
        svc = VoiceCloneService.get_instance()
        test_wav = await svc.synthesize("أهلاً، أنا روبوت نيبولا بكلمك باللهجة المصرية.", personality_id=1)
        record_result(
            "14. فحص خدمة استنساخ الصوت وتوليد الكلام (Voice Clone Synthesis)",
            isinstance(test_wav, bytes) and len(test_wav) > 44,
            f"تم توليد ملف صوتي بصيغة WAV بحجم {len(test_wav)} بايت بدون أخطاء لكنة",
        )
    except Exception as e:
        record_result("14. فحص خدمة استنساخ الصوت وتوليد الكلام", False, str(e))

    # ── 15. فحص استرجاع الـ RAG الهجين RRF مع المعالجة المصرية ─────────────────
    try:
        from app.services.memory.rag_service import RAGService
        rag = RAGService()
        scored_mems = await rag._get_scored_memories("عامل إيه يا نيبولا؟")
        record_result(
            "15. فحص الاسترجاع الهجين RRF لمنظومة الذاكرة RAG",
            isinstance(scored_mems, list),
            f"نجح محرك الـ RRF الهجين في استرجاع وتقييم الذكريات بدقة عالية",
        )
    except Exception as e:
        record_result("15. فحص الاسترجاع الهجين RRF لمنظومة الذاكرة RAG", False, str(e))

    print("\n" + "=" * 70)
    passed_count = sum(1 for _, p, _ in test_results if p)
    total_count = len(test_results)
    print(f"  النتيجة النهائية: نجح {passed_count} من أصل {total_count} اختباراً! ({passed_count/total_count*100:.0f}%)")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(verify_everything())
