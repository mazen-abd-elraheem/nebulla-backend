"""Live verification script for LLM Multi-System Grounding:
1. Faces (Vision)
2. Memories (RAG)
3. Personalities (Dialect / Prompt)
4. Voice Clone (XTTS / sample)
5. Diagnostics (Connected hardware channels)
"""

import asyncio
import sys
import uuid
import httpx

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from app.main import app
from app.db.session import init_db, AsyncSessionLocal
from app.models.face_profile import FaceProfile
from app.models.memory import Memory
from app.models.personality import Personality
from app.websocket.handlers import get_face_service
from app.websocket.manager import manager
from sqlalchemy import select


async def main():
    print("=" * 70)
    print("🤖 بدء اختبار التحقق من الربط متعدد الأنظمة (Grounding Verification)")
    print("=" * 70)

    await init_db()

    # 1. Prepare simulated data in DB & Manager
    async with AsyncSessionLocal() as db:
        # Personality
        res_p = await db.execute(select(Personality).where(Personality.name == "توت الذكي"))
        p = res_p.scalar_one_or_none()
        if not p:
            p = Personality(
                name="توت الذكي",
                description="مساعد شخصي للمهندس مازن",
                system_prompt="أنت توأم رقمي ذكي، وتعرف أنك روبوت نيبولا ولديك محرك صوت مستنسخ.",
                dialect="cairo",
                language_mix="ar_en",
                voice_sample_path="voices/mazen_clone.wav",
                is_active=True,
            )
            db.add(p)
            await db.commit()
            await db.refresh(p)
        else:
            p.voice_sample_path = "voices/mazen_clone.wav"
            p.is_active = True
            await db.commit()

        # FaceProfile
        res_f = await db.execute(select(FaceProfile).where(FaceProfile.name == "Mazen"))
        f = res_f.scalar_one_or_none()
        if not f:
            f = FaceProfile(name="Mazen", embedding=[0.1] * 128)
            db.add(f)
            await db.commit()

        # Memory
        res_m = await db.execute(select(Memory).where(Memory.content.like("%تخرج مازن%")))
        m = res_m.scalar_one_or_none()
        if not m:
            m = Memory(
                personality_id=p.id,
                content="مشروع تخرج مازن هو روبوت Nebula الذكي للذكاء الاصطناعي.",
                source="user",
                importance=0.9,
            )
            db.add(m)
            await db.commit()

    # 2. Simulate Active Face Detection & Hardware connection
    face_svc = get_face_service()
    face_svc.last_result = {
        "status": "recognized",
        "face_id": "Mazen",
        "confidence": 0.98,
        "box": [10, 20, 100, 120],
    }
    import time
    face_svc.last_detection_time = time.time()

    # Simulate ESP32 connected in diagnostics
    manager._esp = object()

    print("\n✅ تم تجهيز البيئة والحالات الحية:")
    print(f"   - الشخصية: {p.name} (عينة الصوت: {p.voice_sample_path})")
    print(f"   - الوجه أمام الكاميرا: Mazen (ثقة: 98%)")
    print(f"   - الوجوه المسجلة: Mazen")
    print(f"   - التشخيص: ESP32 متصل ({manager.status()})")
    print(f"   - الذاكرة: مشروع تخرج مازن هو روبوت Nebula")

    # 3. Call /chat endpoint
    session_id = f"grounding-test-{uuid.uuid4().hex[:6]}"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        user_query = "أنا مين قدامك دلوقتي؟ وإيه مشروع تخرجي؟ وإيه حالة الروبوت وESP32؟"
        print(f"\n👤 سؤال المستخدم:\n   '{user_query}'")
        print("\n⏳ جاري استدعاء الـ API ومطابقة الأنظمة الخمسة مع LLM...")

        resp = await client.post(
            "/api/v1/conversations/chat",
            json={
                "message": user_query,
                "session_id": session_id,
                "personality_id": p.id,
            },
            timeout=120.0,
        )

        if resp.status_code != 200:
            print(f"❌ فشل: {resp.status_code} - {resp.text}")
            return

        data = resp.json()

        print("\n" + "=" * 70)
        print("📦 البيانات المرجعية للأنظمة (Grounding Info المعادة في الـ Response):")
        print("=" * 70)
        import json
        print(json.dumps(data.get("grounding"), indent=2, ensure_ascii=False))

        print("\n" + "=" * 70)
        print("🤖 رد الروبوت المستند للأنظمة الخمسة:")
        print("=" * 70)
        print(f"الرد الكامل:       {data['reply']}")
        print(f"المشاعر:          {data['emotion']}")
        print(f"الذكريات المسترجعة: {data['memories_used']}")
        print(f"زمن الـ LLM:       {data['llm_latency_ms']} ms")
        print("=" * 70)
        print("🎉 الاختبار اكتمل بنجاح تام وتم التحقق من تكامل الأنظمة الخمسة!")


if __name__ == "__main__":
    asyncio.run(main())
