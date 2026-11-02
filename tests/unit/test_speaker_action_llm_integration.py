"""
Comprehensive Unit Tests for Speaker, Action & Voice Verification Integration:
1. Method 1: Metadata Injection (GroundingInfo, ContextBuilder, PromptBuilder).
2. Method 2: API Endpoints (Action Parse, Action LLM Context, LLM Bundle, Speaker Context).
3. Deterministic refusal on unverified or unknown entities.
"""

import pytest
import pytest_asyncio
import numpy as np
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import Base, get_db
from app.api.v1.endpoints import phone_actions, speakers
from app.models.contact import Contact
from app.models.reminder import Reminder
from app.models.voiceprint import Voiceprint
from app.models.user import User
from app.models.personality import Personality
from app.services.ai.context_builder import build_grounding_context, GroundingInfo
from app.providers.llm.prompt_builder import build_rag_system_prompt, build_rag_messages

api_app = FastAPI()
api_app.include_router(phone_actions.router, prefix="/api/v1/actions")
api_app.include_router(speakers.router, prefix="/api/v1/speakers")


@pytest_asyncio.fixture
async def async_session():
    """Create an isolated in-memory SQLite database session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def client(async_session: AsyncSession):
    """Async HTTP test client with database dependency override."""
    async def override_get_db():
        yield async_session

    api_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    api_app.dependency_overrides.pop(get_db, None)


# ── 1. Method 1: Metadata Injection Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_grounding_context_metadata_injection_verified_speaker(async_session: AsyncSession):
    """Verify that speaker and voice verification metadata are populated in GroundingInfo and Prompt."""
    verif_data = {
        "speaker_name": "مازن عبد الرحيم",
        "is_verified": True,
        "confidence": 0.95,
        "security_level": 2,
        "status": "verified",
    }

    prompt, memories, grounding, pid = await build_grounding_context(
        db=async_session,
        personality_id=None,
        message="أهلاً يا نيبولا",
        verified_speaker="مازن عبد الرحيم",
        speaker_verification=verif_data,
    )

    # 1. Verify GroundingInfo metadata
    assert grounding.speaker["name"] == "مازن عبد الرحيم"
    assert grounding.speaker["is_verified"] is True
    assert grounding.speaker["status"] == "verified"
    assert grounding.speaker["security_level"] == 2
    assert grounding.voice_verification["is_verified"] is True

    # 2. Verify System Prompt contains speaker directives for the LLM
    assert "مازن عبد الرحيم" in prompt
    assert "المتحدث" in prompt


@pytest.mark.asyncio
async def test_grounding_context_action_metadata_allowlisted_contact(async_session: AsyncSession):
    """Verify that calling an allowlisted contact sets action metadata and prompt directives."""
    mama_contact = Contact(
        id=1,
        name="ماما",
        slug="mama",
        phone_number="01000000000",
        is_allowlisted=True,
        requires_confirmation=True,
        required_level=1,
    )
    async_session.add(mama_contact)
    await async_session.commit()

    prompt, memories, grounding, pid = await build_grounding_context(
        db=async_session,
        personality_id=None,
        message="كلم ماما",
    )

    # Action metadata verification
    assert grounding.action["has_action"] is True
    assert grounding.action["kind"] == "call"
    assert grounding.action["target"] == "ماما"
    assert grounding.action["is_allowlisted"] is True
    assert grounding.action["requires_confirmation"] is True
    assert grounding.action["status"] == "needs_confirmation"

    # Directive for LLM
    assert "ماما" in prompt
    assert "الإجراء المطلوب" in prompt
    assert "تأكيد" in prompt


@pytest.mark.asyncio
async def test_grounding_context_action_metadata_unknown_contact_rejection(async_session: AsyncSession):
    """Verify that calling an unknown contact strictly rejects deterministically."""
    prompt, memories, grounding, pid = await build_grounding_context(
        db=async_session,
        personality_id=None,
        message="اتصل برامي حالا",
    )

    assert grounding.action["has_action"] is True
    assert grounding.action["kind"] == "call"
    assert grounding.action["is_allowlisted"] is False
    assert grounding.action["status"] == "unknown_contact"
    assert "مش لاقي الاسم ده" in grounding.action["directive"]

    # Prompt directs LLM to refuse strictly
    assert "مش لاقي الاسم ده" in prompt


def test_prompt_builder_speaker_action_formatting():
    """Verify build_rag_system_prompt and build_rag_messages format speaker & action blocks."""
    spk_info = {
        "name": "منه محمد",
        "status": "verified",
        "security_level": 2,
        "directive": "المتحدث الحالي موثق بالبصمة الصوتية: 'منه محمد'.",
    }
    act_info = {
        "has_action": True,
        "kind": "call",
        "target": "ماما",
        "status": "needs_confirmation",
        "directive": "اسأل لتأكيد الاتصال بـ ماما.",
    }

    sys_prompt = build_rag_system_prompt(
        context=["نيبولا روبوت مصري"],
        system_prompt="أنت نيبولا.",
        speaker_info=spk_info,
        action_info=act_info,
    )

    assert "Speaker & Action Context" in sys_prompt
    assert "منه محمد" in sys_prompt
    assert "call -> ماما" in sys_prompt
    assert "اسأل لتأكيد الاتصال بـ ماما" in sys_prompt

    messages = build_rag_messages(
        prompt="كلم ماما",
        context=["نيبولا روبوت مصري"],
        speaker_info=spk_info,
        action_info=act_info,
    )
    assert len(messages) == 2
    assert "منه محمد" in messages[0]["content"]
    assert "call -> ماما" in messages[0]["content"]


# ── 2. Method 2: API Endpoints Tests (Data via API for LLM) ──────────────────

@pytest.mark.asyncio
async def test_api_action_parse_allowlisted_contact(client: AsyncClient, async_session: AsyncSession):
    """Test POST /api/v1/actions/parse for calling an allowlisted contact."""
    c = Contact(
        name="ماما",
        slug="mama",
        phone_number="01012345678",
        is_allowlisted=True,
        requires_confirmation=True,
        required_level=1,
    )
    async_session.add(c)
    await async_session.commit()

    resp = await client.post(
        "/api/v1/actions/parse",
        json={
            "utterance": "كلم ماما",
            "speaker_name": "مازن",
            "is_verified": True,
            "verification_level": 2,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_action"] is True
    assert data["intent"] == "call"
    assert data["target"] == "ماما"
    assert data["is_allowlisted"] is True
    assert data["decision"] == "needs_confirm"
    assert "llm_directive" in data
    assert "suggested_speech" in data


@pytest.mark.asyncio
async def test_api_action_parse_app_open(client: AsyncClient):
    """Test POST /api/v1/actions/parse for opening an app."""
    resp = await client.post(
        "/api/v1/actions/parse",
        json={
            "utterance": "افتح الواتساب",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_action"] is True
    assert data["intent"] == "app_open"
    assert data["decision"] == "ready"
    assert "واتساب" in data["suggested_speech"] or "whatsapp" in data["metadata"].get("app_id", "")


@pytest.mark.asyncio
async def test_api_actions_llm_context(client: AsyncClient, async_session: AsyncSession):
    """Test GET /api/v1/actions/llm-context returns contacts and capabilities for LLM."""
    c = Contact(name="أحمد", slug="ahmed", phone_number="01099999999", is_allowlisted=True)
    async_session.add(c)
    await async_session.commit()

    resp = await client.get("/api/v1/actions/llm-context")
    assert resp.status_code == 200
    data = resp.json()
    assert data["contacts_count"] >= 1
    assert any(item["name"] == "أحمد" for item in data["allowlisted_contacts"])
    assert "supported_apps" in data
    assert "capabilities" in data
    assert "call" in data["capabilities"]


@pytest.mark.asyncio
async def test_api_actions_llm_bundle(client: AsyncClient, async_session: AsyncSession):
    """Test POST /api/v1/actions/llm-bundle returns complete unified package for LLM."""
    c = Contact(name="ماما", slug="mama", phone_number="01011111111", is_allowlisted=True)
    async_session.add(c)
    await async_session.commit()

    resp = await client.post(
        "/api/v1/actions/llm-bundle",
        json={
            "message": "كلم ماما دلوقتي",
            "verified_speaker": "مازن عبد الرحيم",
            "speaker_verification": {
                "speaker_name": "مازن عبد الرحيم",
                "is_verified": True,
                "confidence": 0.98,
                "security_level": 2,
                "status": "verified",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "system_prompt" in data
    assert "messages" in data
    assert "speaker" in data
    assert "action" in data
    assert data["speaker"]["name"] == "مازن عبد الرحيم"
    assert data["action"]["has_action"] is True
    assert len(data["messages"]) >= 2


@pytest.mark.asyncio
async def test_api_speaker_llm_context(client: AsyncClient, async_session: AsyncSession):
    """Test POST /api/v1/speakers/context returns LLM-formatted speaker metadata."""
    u = User(id=1, email="mazen@nebulla.ai", full_name="مازن عبد الرحيم", hashed_password="hash", is_active=True)
    async_session.add(u)
    await async_session.flush()

    vp = Voiceprint(
        user_id=1,
        speaker_name="مازن عبد الرحيم",
        embedding=b"\x00" * (192 * 4),
        embedding_dim=192,
        samples_count=5,
        max_level=2,
    )
    async_session.add(vp)
    await async_session.commit()

    # 1. Registered speaker
    resp1 = await client.post(
        "/api/v1/speakers/context",
        json={"speaker_name": "مازن عبد الرحيم"},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["is_verified"] is True
    assert data1["status"] == "verified"
    assert data1["security_level"] == 2
    assert "مازن عبد الرحيم" in data1["llm_directive"]

    # 2. Unregistered speaker (Deterministic rejection)
    resp2 = await client.post(
        "/api/v1/speakers/context",
        json={"speaker_name": "شخص_غريب_تماماً"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_verified"] is False
    assert data2["status"] == "unverified"
    assert "غير مسجل" in data2["llm_directive"]
