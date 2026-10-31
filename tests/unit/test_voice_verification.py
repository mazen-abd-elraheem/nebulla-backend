"""
Unit tests for Speaker Verification Service (benefits_section.docx §14.3).
Tests:
- Audio decoding and conversion to float32
- Embedding normalization
- Verification matching & Level 1 / Level 2 threshold scoring
- Enrolment with outlier rejection
- Right to be forgotten (deletion)
"""

import io
import struct
import wave
import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models.user import User
from app.models.voiceprint import Voiceprint
from app.services.voice_verification.speaker_service import (
    AudioDecodeError,
    SpeakerVerificationService,
    VoiceprintError,
    _drop_outliers,
    _unit,
    decode_audio,
)


def _generate_wav(duration_s: float = 2.0, sample_rate: int = 16000, freq: float = 440.0) -> bytes:
    """Generate a clean 16-bit mono PCM WAV for testing."""
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


class MockEmbeddingBackend:
    """Deterministic mock embedding backend that outputs reproducible normalized vectors."""
    model_id = "mock-ecapa-tdnn"

    def __init__(self, vector_map=None):
        self._vector_map = vector_map or {}
        self._default_dim = 192

    def available(self) -> bool:
        return True

    def embed(self, samples: np.ndarray) -> np.ndarray:
        # Generate deterministic vector based on mean and length of audio
        mean_val = float(np.mean(samples)) if len(samples) else 0.0
        vec = np.zeros(self._default_dim, dtype=np.float32)
        # Seed first elements
        vec[0] = 1.0 + mean_val
        vec[1] = float(len(samples) % 100) / 100.0
        return _unit(vec)


# ── Audio Decoding Tests ──────────────────────────────────────────────────────

class TestAudioDecoding:
    def test_decode_wav(self):
        wav_bytes = _generate_wav(duration_s=1.5, sample_rate=16000)
        pcm = decode_audio(wav_bytes, target_sr=16000)
        assert isinstance(pcm, np.ndarray)
        assert pcm.dtype == np.float32
        assert len(pcm) == int(1.5 * 16000)
        assert np.max(pcm) <= 1.0
        assert np.min(pcm) >= -1.0

    def test_decode_raw_pcm(self):
        raw = (np.ones(16000, dtype=np.int16) * 16384).tobytes()
        pcm = decode_audio(raw, target_sr=16000)
        assert len(pcm) == 16000
        assert pytest.approx(float(pcm[0]), 0.01) == 0.5

    def test_invalid_wav_raises(self):
        with pytest.raises(AudioDecodeError):
            decode_audio(b"RIFF\x00\x00\x00\x00WAVEfmt corrupt payload")

    def test_unit_normalization(self):
        v = np.array([3.0, 4.0], dtype=np.float32)
        u = _unit(v)
        assert pytest.approx(float(np.linalg.norm(u)), 1e-5) == 1.0
        assert pytest.approx(float(u[0]), 1e-5) == 0.6
        assert pytest.approx(float(u[1]), 1e-5) == 0.8


# ── Outlier Dropping Tests ────────────────────────────────────────────────────

class TestOutlierDropping:
    def test_outlier_filtering(self):
        # 4 identical vectors, 1 orthogonal outlier
        base = np.zeros(10, dtype=np.float32)
        base[0] = 1.0
        outlier = np.zeros(10, dtype=np.float32)
        outlier[1] = 1.0

        samples = [base.copy(), base.copy(), base.copy(), base.copy(), outlier]
        kept = _drop_outliers(samples, floor=0.5)
        assert len(kept) == 4
        for k in kept:
            assert k[0] == 1.0


# ── Speaker Verification Service Tests ────────────────────────────────────────

@pytest.fixture
async def async_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed user 1
    async with async_session() as session:
        u = User(
            id=1,
            full_name="مازن عبد الرحيم",
            email="mazen@nebula.local",
            hashed_password="hash",
            is_active=True,
        )
        session.add(u)
        await session.commit()

    yield async_session
    await engine.dispose()


@pytest.mark.asyncio
class TestSpeakerVerificationService:
    async def test_verify_no_enrollment_fails_closed(self, async_db):
        backend = MockEmbeddingBackend()
        svc = SpeakerVerificationService(backend=backend)

        wav = _generate_wav(duration_s=2.0)
        res = await svc.verify(wav, session_factory=async_db)

        assert res.available is True
        assert res.enrolled is False
        assert res.passed_l1 is False
        assert res.passed_l2 is False

    async def test_enroll_and_verify_success(self, async_db):
        backend = MockEmbeddingBackend()
        svc = SpeakerVerificationService(backend=backend)

        samples = [_generate_wav(duration_s=2.0, freq=440.0) for _ in range(5)]

        async with async_db() as session:
            vp = await svc.enroll(
                session,
                user_id=1,
                speaker_name="مازن",
                samples=samples,
                max_level=2,
            )
            await session.commit()
            assert vp.id is not None
            assert vp.speaker_name == "مازن"
            assert vp.samples_count == 5

        # Now verify with an audio sample
        test_wav = _generate_wav(duration_s=2.0, freq=440.0)
        res = await svc.verify(test_wav, session_factory=async_db)

        assert res.available is True
        assert res.enrolled is True
        assert res.user_id == 1
        assert res.speaker_name == "مازن"
        assert res.score is not None
        assert res.score > 0.9
        assert res.passed_l1 is True
        assert res.passed_l2 is True

    async def test_enroll_too_few_samples_raises(self, async_db):
        backend = MockEmbeddingBackend()
        svc = SpeakerVerificationService(backend=backend)

        # Only 2 samples (less than minimum 5)
        samples = [_generate_wav(duration_s=2.0) for _ in range(2)]
        async with async_db() as session:
            with pytest.raises(VoiceprintError, match="Provide 5–20 samples"):
                await svc.enroll(
                    session,
                    user_id=1,
                    speaker_name="مازن",
                    samples=samples,
                )

    async def test_right_to_be_forgotten_deletion(self, async_db):
        backend = MockEmbeddingBackend()
        svc = SpeakerVerificationService(backend=backend)

        # Enroll
        samples = [_generate_wav(duration_s=2.0) for _ in range(5)]
        async with async_db() as session:
            await svc.enroll(session, user_id=1, speaker_name="مازن", samples=samples)
            await session.commit()

        # Delete
        async with async_db() as session:
            deleted = await svc.delete(session, user_id=1)
            assert deleted is True
            await session.commit()

        # Verify deletion from DB
        async with async_db() as session:
            row = (await session.execute(select(Voiceprint).where(Voiceprint.user_id == 1))).scalar_one_or_none()
            assert row is None

        # Verification now returns enrolled=False
        test_wav = _generate_wav(duration_s=2.0)
        res = await svc.verify(test_wav, session_factory=async_db)
        assert res.enrolled is False
