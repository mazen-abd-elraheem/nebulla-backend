"""Integration tests for Audio and Voice Clone API endpoints."""

import io
import wave
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.db.session import init_db
from app.core.config import settings


def _create_dummy_wav(duration_s: float = 2.0, sample_rate: int = 24000) -> bytes:
    """Generate a valid dummy PCM 16-bit mono WAV in-memory."""
    buf = io.BytesIO()
    num_samples = int(duration_s * sample_rate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # Generate a simple 440Hz tone so RMS > 0
        import math
        import struct
        data = bytearray()
        for i in range(num_samples):
            val = int(10000 * math.sin(2 * math.pi * 440 * i / sample_rate))
            data.extend(struct.pack("<h", val))
        wf.writeframes(bytes(data))
    return buf.getvalue()


@pytest.fixture(autouse=True)
async def setup_db():
    await init_db()


@pytest.mark.asyncio
async def test_get_speakers_endpoint():
    """Verify listing VoiceTut Egyptian speakers."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/api/v1/audio/speakers")
    assert res.status_code == 200
    data = res.json()
    assert "speakers" in data
    assert len(data["speakers"]) > 0
    assert "mohammed" in data["speakers"]


@pytest.mark.asyncio
async def test_transcribe_audio_endpoint():
    """Verify STT audio transcription endpoint."""
    wav_bytes = _create_dummy_wav(duration_s=2.0)
    files = {"file": ("test_input.wav", wav_bytes, "audio/wav")}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/audio/transcribe", files=files)

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert "transcription" in data
    assert data["duration_s"] > 0
    assert "latency_ms" in data


@pytest.mark.asyncio
async def test_voice_clone_upload_and_samples():
    """Verify uploading reference sample and retrieving it from samples list."""
    wav_bytes = _create_dummy_wav(duration_s=2.5)
    files = {"file": ("my_voice.wav", wav_bytes, "audio/wav")}
    data = {"personality_id": "99", "transcript": "أهلاً بيكم في الاختبار"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Upload
        res_up = await client.post("/api/v1/voice-clone/upload", files=files, data=data)
        assert res_up.status_code == 201
        assert "path" in res_up.json()

        # List samples
        res_list = await client.get("/api/v1/voice-clone/samples")
        assert res_list.status_code == 200
        samples = res_list.json()["samples"]
        pids = [s["personality_id"] for s in samples]
        assert 99 in pids

        # Clean up
        res_del = await client.delete("/api/v1/voice-clone/samples/99")
        assert res_del.status_code == 200


@pytest.mark.asyncio
async def test_voice_clone_synthesize_endpoint():
    """Verify speech synthesis returns WAV audio."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "text": "تجربة توليد الصوت من خلال الـ API",
            "personality_id": 1,
            "num_steps": 4,
        }
        res = await client.post("/api/v1/voice-clone/synthesize", json=payload)

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("audio/")
    assert len(res.content) > 1000

    # Verify WAV header
    with wave.open(io.BytesIO(res.content), "rb") as wf:
        assert wf.getnchannels() in (1, 2)
        assert wf.getframerate() > 8000
        assert wf.getnframes() > 0


@pytest.mark.asyncio
async def test_voice_clone_quick_test():
    """Verify quick test endpoint returns valid WAV."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post("/api/v1/voice-clone/test")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("audio/")
    assert len(res.content) > 1000
