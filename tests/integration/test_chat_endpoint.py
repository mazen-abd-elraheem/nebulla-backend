import time
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.main import app
from app.db.session import init_db, AsyncSessionLocal
from app.models.personality import Personality
from app.models.face_profile import FaceProfile
from app.models.memory import Memory
from app.websocket.manager import manager
from app.services.vision.face_service import FaceResult
from app.websocket.handlers import get_face_service


@pytest.mark.asyncio
async def test_chat_endpoint_success():
    await init_db()

    mock_reply = "أهلاً يا باشا! منور الدنيا [happy] [wave]"

    with patch("app.providers.llm.local_ollama.LocalOllamaProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = mock_reply

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            payload = {
                "message": "صباح الفل يا روبوت",
                "session_id": "test-chat-session-001",
            }
            resp = await client.post("/api/v1/conversations/chat", json=payload)

            assert resp.status_code == 200
            data = resp.json()
            assert data["reply"] == mock_reply
            assert data["cleaned_reply"] == "أهلاً يا باشا! منور الدنيا"
            assert data["emotion"] == "happy"
            assert data["session_id"] == "test-chat-session-001"
            assert data["conversation_id"] > 0
            assert data["llm_latency_ms"] >= 0
            assert "grounding" in data
            assert "faces" in data["grounding"]
            assert "memories" in data["grounding"]
            assert "personality" in data["grounding"]
            assert "voice_clone" in data["grounding"]
            assert "diagnostics" in data["grounding"]


@pytest.mark.asyncio
async def test_chat_multi_turn_history():
    await init_db()

    with patch("app.providers.llm.local_ollama.LocalOllamaProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "تمام جداً [like]"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            session_id = "test-chat-multi-turn-002"

            # Turn 1
            r1 = await client.post("/api/v1/conversations/chat", json={"message": "أنا أحمد", "session_id": session_id})
            assert r1.status_code == 200
            cid = r1.json()["conversation_id"]

            # Turn 2 with same session_id
            r2 = await client.post("/api/v1/conversations/chat", json={"message": "فاكر اسمي؟", "session_id": session_id})
            assert r2.status_code == 200
            assert r2.json()["conversation_id"] == cid

            # Verify history passed to LLM on turn 2
            call_kwargs = mock_gen.call_args[1]
            history = call_kwargs.get("history", [])
            assert len(history) >= 2
            assert history[0]["content"] == "أنا أحمد"


@pytest.mark.asyncio
async def test_chat_full_grounding_context():
    await init_db()

    # Seed personality, face profile, and mock face detection
    async with AsyncSessionLocal() as session:
        # Personality with voice sample
        p = Personality(
            name=f"شخصية تجريبية-{time.time()}",
            system_prompt="أنت مساعد ذكي للمكتب.",
            dialect="alex",
            language_mix="ar_en",
            voice_sample_path="samples/voice1.wav",
            is_active=True,
        )
        session.add(p)
        await session.flush()

        # Registered face profile
        res_face = await session.execute(select(FaceProfile).where(FaceProfile.name == "مازن عبد الرحيم"))
        existing_face = res_face.scalar_one_or_none()
        if not existing_face:
            face_profile = FaceProfile(
                name="مازن عبد الرحيم",
                embedding=[0.1] * 128,
            )
            session.add(face_profile)

        # Stored memory
        mem = Memory(
            personality_id=p.id,
            content="المستخدم يفضل القهوة بدون سكر",
            source="manual",
        )
        session.add(mem)
        await session.commit()

    # Mock active face detection
    face_svc = get_face_service()
    face_svc.last_result = FaceResult(detected=True, x=0.0, y=0.0, confidence=0.98, face_id="مازن عبد الرحيم")
    face_svc.last_detection_time = time.time()

    with patch("app.providers.llm.local_ollama.LocalOllamaProvider.generate", new_callable=AsyncMock) as mock_gen:
        mock_gen.return_value = "أهلاً يا مازن! شايفك قدامي [happy]"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/v1/conversations/chat",
                json={"message": "شايف مين قدامك وعارف قهوتي إيه؟", "personality_id": p.id},
            )

            assert resp.status_code == 200
            data = resp.json()
            grounding = data["grounding"]

            # 1. Verify Personality
            assert grounding["personality"]["dialect"] == "alex"
            assert "أنت مساعد ذكي" in grounding["personality"]["system_prompt"]

            # 2. Verify Faces
            assert "مازن عبد الرحيم" in grounding["faces"]["registered_profiles"]
            assert "مازن عبد الرحيم" in grounding["faces"]["current_person"]
            assert grounding["faces"]["currently_detected"] is True

            # 3. Verify Voice Clone
            assert "samples/voice1.wav" in grounding["voice_clone"]["voice_sample_path"]
            assert grounding["voice_clone"]["has_sample"] is True

            # 4. Verify Diagnostics
            assert "phone_connected" in grounding["diagnostics"]
            assert "desktop_connected" in grounding["diagnostics"]
            assert "esp_connected" in grounding["diagnostics"]

            # 5. Verify system prompt passed to LLM contains all grounding elements
            call_kwargs = mock_gen.call_args[1]
            sys_prompt = call_kwargs.get("system_prompt", "")
            assert "مازن عبد الرحيم" in sys_prompt
            assert "alex" in sys_prompt
            assert "samples/voice1.wav" in sys_prompt
            assert "الشخصية النشطة" in sys_prompt
            assert "التشخيص وحالة الأجهزة" in sys_prompt


@pytest.mark.asyncio
async def test_chat_empty_message_validation():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/v1/conversations/chat", json={"message": "   "})
        assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_playground_ui():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/chat")
        assert resp.status_code == 200
        assert "شات روبوت Nebula" in resp.text
        assert "messagesArea" in resp.text

        resp_p = await client.get("/api/v1/conversations/playground")
        assert resp_p.status_code == 200
        assert "شات روبوت Nebula" in resp_p.text


@pytest.mark.asyncio
async def test_chat_streaming_concurrency_and_persistence():
    await init_db()

    async def mock_stream_tokens(*args, **kwargs):
        for token in ["أهلاً ", "بك ", "يا ", "سيدي! ", "[happy]"]:
            yield token

    with patch("app.providers.llm.local_ollama.LocalOllamaProvider.generate_stream", side_effect=mock_stream_tokens):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            session_id = f"test-stream-session-{time.time()}"

            # Stream Turn 1
            r1 = await client.post("/api/v1/conversations/chat", json={
                "message": "مرحبا 1",
                "session_id": session_id,
                "stream": True,
            })
            assert r1.status_code == 200
            content1 = r1.text
            assert "أهلاً بك يا سيدي!" in content1

            # Stream Turn 2 in quick succession (tests SQLite concurrency & WAL mode)
            r2 = await client.post("/api/v1/conversations/chat", json={
                "message": "مرحبا 2",
                "session_id": session_id,
                "stream": True,
            })
            assert r2.status_code == 200
            content2 = r2.text
            assert "أهلاً بك يا سيدي!" in content2

    # Verify messages in DB
    from app.models.conversation import Conversation, Message
    async with AsyncSessionLocal() as session:
        conv_res = await session.execute(
            select(Conversation).where(Conversation.session_id == session_id)
        )
        conv = conv_res.scalar_one_or_none()
        assert conv is not None

        msgs_res = await session.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
        )
        msgs = msgs_res.scalars().all()
        # Turn 1 (user + robot) + Turn 2 (user + robot) = 4 messages
        assert len(msgs) == 4
        assert msgs[0].role == "user"
        assert msgs[0].content == "مرحبا 1"
        assert msgs[1].role == "robot"
        assert "أهلاً بك يا سيدي!" in msgs[1].content
        assert msgs[2].role == "user"
        assert msgs[2].content == "مرحبا 2"
        assert msgs[3].role == "robot"
        assert "أهلاً بك يا سيدي!" in msgs[3].content

