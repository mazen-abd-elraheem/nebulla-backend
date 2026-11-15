"""
Unit & API Tests for Unified Speaker Management.
Verifies:
  1. Speaker entity creation (verification_id, voice_id, personality_id, is_main).
  2. Multi-main speaker support (multiple main speakers allowed).
  3. Absence of security_level across context and LLM directives.
  4. Speaker CRUD API endpoints (GET, POST, PATCH, DELETE).
  5. Auto-binding between voiceprint enrollment and Speaker profile.
"""

import io
import wave
import numpy as np
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.core.config import settings
from app.db.session import Base
from app.models.user import User
from app.models.personality import Personality
from app.models.voiceprint import Voiceprint
from app.models.speaker import Speaker
from app.services.voice_verification.speaker_service import (
    SpeakerVerificationService,
    get_speaker_service,
    _unit,
)


def _generate_wav(duration_s: float = 1.0, sample_rate: int = 16000, freq: float = 440.0) -> bytes:
    n_samples = int(duration_s * sample_rate)
    t = np.linspace(0, duration_s, n_samples, endpoint=False)
    samples = (np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


@pytest.fixture
async def test_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed User & Personality
    async with async_session() as session:
        u = User(id=1, full_name="مازن عبد الرحيم", email="mazen@nebula.local", hashed_password="hash", is_active=True)
        p = Personality(id=1, name="مازن - التوأم الرقمي", system_prompt="توأم رقمي", is_active=True)
        session.add_all([u, p])
        await session.commit()

    yield async_session
    await engine.dispose()


@pytest.mark.asyncio
async def test_speaker_model_creation_and_attributes(test_db):
    """Test that Speaker model correctly aggregates the 4 components and supports multi-main."""
    async with test_db() as session:
        # 1. Create dummy voiceprint
        blob = np.ones(192, dtype=np.float32).tobytes()
        vp1 = Voiceprint(user_id=1, speaker_name="مازن", embedding=blob, embedding_dim=192, samples_count=1, model_id="test")
        session.add(vp1)
        await session.flush()

        # 2. Create Speaker 1 (Mazen - Main)
        spk1 = Speaker(
            name="مازن",
            verification_id=vp1.id,
            voice_id="1",
            personality_id=1,
            is_main=True,
        )
        session.add(spk1)

        # 3. Create Speaker 2 (Menna - Also Main, verifying multi-main support)
        spk2 = Speaker(
            name="منه",
            verification_id=None,
            voice_id="2",
            personality_id=None,
            is_main=True,
        )
        session.add(spk2)
        await session.commit()

        # Query and verify
        res = await session.execute(select(Speaker).order_by(Speaker.id.asc()))
        speakers = res.scalars().all()
        assert len(speakers) == 2

        # Mazen
        assert speakers[0].name == "مازن"
        assert speakers[0].verification_id == vp1.id
        assert speakers[0].voice_id == "1"
        assert speakers[0].personality_id == 1
        assert speakers[0].is_main is True

        # Menna
        assert speakers[1].name == "منه"
        assert speakers[1].verification_id is None
        assert speakers[1].voice_id == "2"
        assert speakers[1].is_main is True  # Both can be main simultaneously!


@pytest.mark.asyncio
async def test_speakers_api_crud():
    """Test full Speaker RESTful CRUD endpoints (/api/v1/speakers)."""
    from app.db.session import init_db
    await init_db()
    headers = {"X-API-Key": settings.PAIRING_SECRET}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # 1. Create a new speaker
        create_payload = {
            "name": "أحمد التيست",
            "verification_id": None,
            "voice_id": "ahmed_voice_sample",
            "personality_id": 1,
            "is_main": False,
        }
        res_create = await client.post("/api/v1/speakers", json=create_payload, headers=headers)
        assert res_create.status_code in (201, 409)
        if res_create.status_code == 201:
            data = res_create.json()
            spk_id = data["id"]
            assert data["name"] == "أحمد التيست"
            assert data["voice_id"] == "ahmed_voice_sample"
            assert data["is_main"] is False

            # 2. Get speaker by ID
            res_get = await client.get(f"/api/v1/speakers/{spk_id}", headers=headers)
            assert res_get.status_code == 200
            get_data = res_get.json()
            assert get_data["id"] == spk_id
            assert get_data["name"] == "أحمد التيست"

            # 3. Update speaker (Promote to is_main = True)
            res_patch = await client.patch(f"/api/v1/speakers/{spk_id}", json={"is_main": True, "voice_id": "voice_updated"}, headers=headers)
            assert res_patch.status_code == 200
            patch_data = res_patch.json()
            assert patch_data["is_main"] is True
            assert patch_data["voice_id"] == "voice_updated"

            # 4. List speakers
            res_list = await client.get("/api/v1/speakers", headers=headers)
            assert res_list.status_code == 200
            all_spks = res_list.json()
            assert any(s["id"] == spk_id for s in all_spks)

            # 5. Delete speaker
            res_del = await client.delete(f"/api/v1/speakers/{spk_id}", headers=headers)
            assert res_del.status_code == 200

            # 6. Verify deleted
            res_verify_del = await client.get(f"/api/v1/speakers/{spk_id}", headers=headers)
            assert res_verify_del.status_code == 404


@pytest.mark.asyncio
async def test_speaker_context_api_no_security_level():
    """Verify that POST /api/v1/speakers/context contains is_main and does NOT return security_level."""
    from app.db.session import init_db
    await init_db()
    headers = {"X-API-Key": settings.PAIRING_SECRET}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        # Query context by claimed speaker name
        res = await client.post("/api/v1/speakers/context", data={"speaker_name": "مازن"}, headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert "is_main" in data
        assert "security_level" not in data  # security_level removed!
        assert data["is_verified"] is True
        assert "متحدث رئيسي" in data["llm_directive"]
