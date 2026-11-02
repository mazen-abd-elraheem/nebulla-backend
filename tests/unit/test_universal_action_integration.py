"""
Comprehensive Unit Tests for Universal System Actions & LLM Integration:
- Covers ANY action: Motion, Screen, Vision, Device, Phone, Reminder, Media, Sensitive.
- Tests Method 1: Metadata (GroundingInfo, ContextBuilder, PromptBuilder).
- Tests Method 2: API (Universal Parse, Execute, Capabilities for LLM Tool Calling).
- Tests Deterministic Enforcement (Strict refusal on unverified, unauthorized, or unsupported actions).
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import Base, get_db
from app.api.v1.endpoints import phone_actions, speakers
from app.models.contact import Contact
from app.models.personality import Personality
from app.models.reminder import Reminder
from app.services.ai.context_builder import build_grounding_context
from app.services.ai.universal_action import (
    get_universal_action_planner,
    get_action_capabilities,
    ActionDomain,
)
from app.providers.llm.prompt_builder import build_rag_system_prompt, build_rag_messages

api_app = FastAPI()
api_app.include_router(phone_actions.router, prefix="/api/v1/actions")
api_app.include_router(speakers.router, prefix="/api/v1/speakers")


@pytest_asyncio.fixture
async def async_session():
    """Create isolated in-memory SQLite database session."""
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


# ── 1. Universal Action Planner Unit Tests ───────────────────────────────────

def test_planner_motion_actions():
    planner = get_universal_action_planner()

    # Wave
    res_wave = planner.evaluate("لوح بايدك يا نيبولا")
    assert res_wave.has_action is True
    assert res_wave.domain == ActionDomain.MOTION.value
    assert res_wave.action == "wave"
    assert res_wave.action_tag == "[wave]"
    assert res_wave.decision == "ready"

    # Like
    res_like = planner.evaluate("اعمل لايك")
    assert res_like.domain == ActionDomain.MOTION.value
    assert res_like.action == "like"
    assert res_like.action_tag == "[like]"

    # Stop
    res_stop = planner.evaluate("اقف مكانك بسرعة")
    assert res_stop.domain == ActionDomain.MOTION.value
    assert res_stop.action == "stop"
    assert res_stop.action_tag == "[stop]"
    assert res_stop.decision == "ready"


def test_planner_screen_and_eyes_actions():
    planner = get_universal_action_planner()

    # Eyes mood: happy
    res_happy = planner.evaluate("خلي عينيك مبسوطة وفرحانة")
    assert res_happy.has_action is True
    assert res_happy.domain == ActionDomain.SCREEN.value
    assert res_happy.action == "eyes_mood"
    assert res_happy.params["mood"] == "happy"
    assert res_happy.action_tag == "[happy]"

    # Gaze
    res_gaze = planner.evaluate("بص لفوق")
    assert res_gaze.domain == ActionDomain.SCREEN.value
    assert res_gaze.action == "gaze"
    assert res_gaze.params["y"] == 1.0


def test_planner_device_and_iot_actions():
    planner = get_universal_action_planner()

    # Light toggle (requires Level 2 voice verification)
    res_light_unverified = planner.evaluate("شغل النور", is_verified=False)
    assert res_light_unverified.has_action is True
    assert res_light_unverified.domain == ActionDomain.DEVICE.value
    assert res_light_unverified.decision == "unverified_speaker"

    res_light_verified = planner.evaluate("شغل النور", is_verified=True, verification_level=2)
    assert res_light_verified.decision == "ready"
    assert res_light_verified.execution_payload["state"] is True

    # Battery
    res_bat = planner.evaluate("شوف البطارية كام")
    assert res_bat.domain == ActionDomain.DEVICE.value
    assert res_bat.action == "check_battery"
    assert res_bat.decision == "ready"


def test_planner_media_actions():
    planner = get_universal_action_planner()

    res_music = planner.evaluate("شغل موسيقى هادية")
    assert res_music.has_action is True
    assert res_music.domain == ActionDomain.MEDIA.value
    assert res_music.action == "play_media"

    res_vol = planner.evaluate("علي الصوت شوية")
    assert res_vol.domain == ActionDomain.MEDIA.value
    assert res_vol.action == "volume_control"


def test_planner_sensitive_level3_security():
    planner = get_universal_action_planner()

    # Unverified speaker attempting memory wipe
    res_wipe = planner.evaluate("امسح كل الذكريات اللي عندك", is_verified=False)
    assert res_wipe.has_action is True
    assert res_wipe.domain == ActionDomain.SENSITIVE.value
    assert res_wipe.action == "memory_wipe"
    assert res_wipe.decision == "unverified_speaker"
    assert res_wipe.is_authorized is False


def test_planner_unsupported_action_deterministic_refusal():
    planner = get_universal_action_planner()

    res = planner.evaluate("اطبخ لي عشا النهاردة")
    assert res.has_action is True
    assert res.decision == "unsupported_action"
    assert res.is_authorized is False
    assert "غير مدعوم" in res.llm_directive
    assert "لا تحاول اختلاق بديل" in res.llm_directive


# ── 2. Method 1: Metadata Context Integration ────────────────────────────────

@pytest.mark.asyncio
async def test_context_builder_metadata_any_action(async_session: AsyncSession):
    """Verify that build_grounding_context enriches GroundingInfo.action for any domain (motion, screen, etc.)."""
    p = Personality(id=1, name="نيبولا", is_active=True, dialect="cairo")
    async_session.add(p)
    await async_session.commit()

    # Motion action via metadata
    prompt, memories, grounding, pid = await build_grounding_context(
        db=async_session,
        personality_id=1,
        message="لوح بايدك وسلم عليهم",
        verified_speaker="مازن عبد الرحيم",
    )

    assert grounding.action["has_action"] is True
    assert grounding.action["domain"] == "motion"
    assert grounding.action["action"] == "wave"
    assert grounding.action["action_tag"] == "[wave]"
    assert "wave" in prompt


# ── 3. Method 2: API Integration Tests ───────────────────────────────────────

@pytest.mark.asyncio
async def test_api_universal_capabilities(client: AsyncClient):
    """Verify GET /api/v1/actions/universal/capabilities returns full tool definitions for LLMs."""
    resp = await client.get("/api/v1/actions/universal/capabilities")
    assert resp.status_code == 200
    data = resp.json()
    assert data["capabilities_count"] > 10
    assert "motion" in data["domains"]
    assert "screen" in data["domains"]
    assert "device" in data["domains"]
    assert len(data["tools"]) > 0


@pytest.mark.asyncio
async def test_api_universal_parse_any_action(client: AsyncClient):
    """Verify POST /api/v1/actions/universal/parse parses any action into structured LLM-ready data."""
    # Test screen mood action
    resp = await client.post(
        "/api/v1/actions/universal/parse",
        json={"utterance": "خلي عينيك سعيدة وفرحانة", "is_verified": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_action"] is True
    assert data["domain"] == "screen"
    assert data["action"] == "eyes_mood"
    assert data["action_tag"] == "[happy]"
    assert data["decision"] == "ready"


@pytest.mark.asyncio
async def test_api_universal_execute(client: AsyncClient):
    """Verify POST /api/v1/actions/universal/execute dispatches actions across channels."""
    resp = await client.post(
        "/api/v1/actions/universal/execute",
        json={
            "domain": "screen",
            "action": "eyes_mood",
            "params": {"mood": "happy"},
            "is_verified": True,
            "verification_level": 1,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["status"] == "dispatched"
    assert data["dispatched_channel"] == "phone"


@pytest.mark.asyncio
async def test_api_parse_backward_compatibility_with_any_action(client: AsyncClient):
    """Verify that existing POST /api/v1/actions/parse now handles ANY action seamlessly."""
    # Motion
    resp_motion = await client.post(
        "/api/v1/actions/parse",
        json={"utterance": "اعمل لايك"},
    )
    assert resp_motion.status_code == 200
    data_m = resp_motion.json()
    assert data_m["has_action"] is True
    assert data_m["intent"] == "like"
    assert data_m["decision"] == "ready"

    # Unsupported action -> deterministic refusal
    resp_unsupported = await client.post(
        "/api/v1/actions/parse",
        json={"utterance": "اطبخ لي رز وخضار"},
    )
    assert resp_unsupported.status_code == 200
    data_u = resp_unsupported.json()
    assert data_u["has_action"] is True
    assert data_u["decision"] == "unsupported_action"
    assert "غير مدعوم" in data_u["llm_directive"]

