import asyncio
import sys
import uuid
import httpx

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from app.main import app
from app.db.session import init_db

questions = [
    "من هو نيبولا؟",
    "إيه هو مشروع تخرج مازن؟",
    "أنا بحب أشرب إيه؟",
    "حسبي الله ونعم الوكيل",
]

async def run_test():
    await init_db()
    session_id = f"test-eval-{uuid.uuid4().hex[:6]}"
    
    print("=" * 65)
    print(f"🚀 اختبار المحادثة عبر REST API (Session: {session_id}):")
    print("=" * 65)
    
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost:8000") as client:
        for q in questions:
            print(f"\n👤 المستخدم: {q}")
            resp = await client.post(
                "/api/v1/conversations/chat",
                json={"message": q, "session_id": session_id},
                timeout=45.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                print(f"🤖 نيبولا:    {data['reply']}")
                print(f"   الذاكرة:   {data.get('memories_used')}")
                print(f"   الشعور:    {data.get('emotion')}")
            else:
                print(f"❌ خطأ: {resp.status_code} - {resp.text}")
    print("=" * 65)

asyncio.run(run_test())
