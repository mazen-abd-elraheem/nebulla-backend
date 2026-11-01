# -*- coding: utf-8 -*-
"""
Tests for Two-Voice Comparison and Arabic vs English Language Detection.
User Requirements:
1. "عاوز اضيف الجوزء اللي هو يقارن فيه بين اتنين فويس انا اللي ابعتهم و يقولي كل صوت بتاع مين"
2. "و عاوز الجوزء بتاع الوغات العربي و الانجليزي يقولي الشخص اللي اتكلم اتكلم باني لوغه فيهم"
"""
import io
import wave
import numpy as np
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.voice_verification.speaker_service import get_speaker_service


def generate_tone(freq: float, duration_sec: float, sr: int = 16000, high_freq_boost: float = 0.0) -> bytes:
    """Generates synthetic speech-like WAV bytes with specific pitch and spectral profile."""
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    sig = 0.5 * np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t) + 0.15 * np.sin(6 * np.pi * freq * t)
    if high_freq_boost > 0:
        sig += high_freq_boost * np.sin(2 * np.pi * 3200 * t)
    sig += np.random.normal(0, 0.005, size=t.shape)
    audio_i16 = (sig * 32767 / max(1.0, np.max(np.abs(sig)))).astype(np.int16)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_i16.tobytes())
    return buf.getvalue()


@pytest.mark.asyncio
async def test_compare_two_speakers_same_person():
    """Verify comparing two clips from the same speaker yields is_same_speaker=True with high match %."""
    spk_wav1 = generate_tone(140.0, 1.8)
    spk_wav2 = generate_tone(140.0, 1.8)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {
            "file1": ("voice1.wav", spk_wav1, "audio/wav"),
            "file2": ("voice2.wav", spk_wav2, "audio/wav"),
        }
        res = await client.post("/api/v1/speakers/compare?threshold=0.82", files=files)
        assert res.status_code == 200, f"Error: {res.text}"
        data = res.json()

        assert data["success"] is True
        assert data["is_same_speaker"] is True
        assert data["similarity"] >= 0.85
        assert data["match_percentage"] >= 80.0
        assert "نفس الشخص" in data["comparison_verdict"]


@pytest.mark.asyncio
async def test_compare_two_speakers_different_people_and_identities():
    """Verify comparing two different speakers correctly distinguishes them and returns identity + IDs."""
    speaker_name = "TestCompareAhmed"
    enrolled_audio = generate_tone(130.0, 2.0)
    different_audio = generate_tone(320.0, 2.0, high_freq_boost=0.5)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Enroll speaker with Cross-Modal IDs
        enroll_data = {
            "speaker_name": speaker_name,
            "face_id": "77",
            "personality_id": "88",
            "memory_id": "99",
        }
        enroll_files = {"file": ("enroll.wav", enrolled_audio, "audio/wav")}
        enroll_res = await client.post("/api/v1/speakers/enroll", data=enroll_data, files=enroll_files)
        assert enroll_res.status_code == 200, f"Enroll failed: {enroll_res.text}"
        assert enroll_res.json()["face_id"] == 77
        assert enroll_res.json()["personality_id"] == 88
        assert enroll_res.json()["memory_id"] == 99

        # Invalidate cache if needed
        speaker_service = get_speaker_service()
        speaker_service.invalidate()

        # 2. Compare Voice 1 (Ahmed) vs Voice 2 (Unknown / Different)
        compare_files = {
            "file1": ("ahmed_voice.wav", enrolled_audio, "audio/wav"),
            "file2": ("different_voice.wav", different_audio, "audio/wav"),
        }
        res = await client.post("/api/v1/speakers/compare?threshold=0.82", files=compare_files)
        assert res.status_code == 200, f"Compare failed: {res.text}"
        data = res.json()

        assert data["success"] is True
        # Different people
        assert data["is_same_speaker"] is False
        assert "شخصين مختلفين" in data["comparison_verdict"]

        # Voice 1 should be recognized as Ahmed
        v1 = data["voice1"]
        assert v1["is_enrolled"] is True
        assert v1["speaker_name"] == speaker_name
        assert v1["face_id"] == 77
        assert v1["personality_id"] == 88
        assert v1["memory_id"] == 99
        assert v1["match_percentage"] >= 80.0
        assert "language" in v1

        # Voice 2 should be recognized as un-enrolled / unknown
        v2 = data["voice2"]
        assert v2["is_enrolled"] is False
        assert "غير مسجل" in v2["speaker_name"]
        assert "language" in v2

        # Language verdict presence
        assert "language_verdict" in data
        assert len(data["language_verdict"]) > 0

        # Arabic summary presence
        assert "arabic_summary" in data
        assert speaker_name in data["arabic_summary"]

        # 3. Clean up
        del_res = await client.delete(f"/api/v1/speakers/{speaker_name}")
        assert del_res.status_code == 200
        speaker_service.invalidate()


@pytest.mark.asyncio
async def test_compare_two_speakers_language_detection():
    """Verify explicit language classification (Arabic vs English) for compared audio clips."""
    # Low centroid harmonic -> Arabic
    arabic_audio = generate_tone(150.0, 1.5, high_freq_boost=0.0)
    # High frequency boost / high centroid -> English
    english_audio = generate_tone(220.0, 1.5, high_freq_boost=0.8)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {
            "file1": ("audio_ar.wav", arabic_audio, "audio/wav"),
            "file2": ("audio_en.wav", english_audio, "audio/wav"),
        }
        res = await client.post("/api/v1/speakers/compare", files=files)
        assert res.status_code == 200, f"Compare failed: {res.text}"
        data = res.json()

        assert data["success"] is True
        v1 = data["voice1"]
        v2 = data["voice2"]

        assert v1["language_code"] in ["ar", "en"]
        assert v2["language_code"] in ["ar", "en"]
        assert "العربية" in v1["language"] or "الإنجليزية" in v1["language"]
        assert "العربية" in v2["language"] or "الإنجليزية" in v2["language"]

