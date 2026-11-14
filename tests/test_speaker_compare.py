# -*- coding: utf-8 -*-
"""
Tests for Two-Voice Comparison and Sub-Second Speaker Identification.
User Requirements:
1. "عاوز الغي الجوزاء بتاع التعرف علي الوغات" (Remove language detection).
2. "و عاوز يتعرف علي الصوت اقل من ثانيه" (Recognize voice clips in less than 1 second, e.g. 0.25s).
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
    spk_wav1 = generate_tone(140.0, 1.2)
    spk_wav2 = generate_tone(140.0, 1.2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {
            "file1": ("voice1.wav", spk_wav1, "audio/wav"),
            "file2": ("voice2.wav", spk_wav2, "audio/wav"),
        }
        res = await client.post("/api/v1/speakers/compare?threshold=0.68", files=files)
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
    enrolled_audio = generate_tone(130.0, 1.5)
    different_audio = generate_tone(320.0, 1.5, high_freq_boost=0.5)

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
        res = await client.post("/api/v1/speakers/compare?threshold=0.68", files=compare_files)
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

        # Voice 2 should be recognized as un-enrolled / unknown
        v2 = data["voice2"]
        assert v2["is_enrolled"] is False
        assert "غير مسجل" in v2["speaker_name"]

        # Arabic summary presence
        assert "arabic_summary" in data
        assert speaker_name in data["arabic_summary"]

        # 3. Clean up
        del_res = await client.delete(f"/api/v1/speakers/{speaker_name}")
        assert del_res.status_code == 200
        speaker_service.invalidate()


@pytest.mark.asyncio
async def test_subsecond_voice_identification_and_compare():
    """
    Verify voice recognition works on audio LESS THAN 1 SECOND (e.g. 0.25s and 0.35s).
    Requirement: 'عاوز يتعرف علي الصوت اقل من ثانيه'
    """
    speaker_name = "SubSecondSpeaker"
    # Audio of only 0.45s for enrollment
    enroll_audio = generate_tone(150.0, 0.45)
    # Audio of only 0.25s (< 1 second!) for testing
    subsecond_voice1 = generate_tone(150.0, 0.25)
    subsecond_voice2 = generate_tone(150.0, 0.30)
    subsecond_diff = generate_tone(340.0, 0.25)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Enroll speaker with sub-second sample
        enroll_files = {"file": ("enroll.wav", enroll_audio, "audio/wav")}
        enroll_res = await client.post(
            "/api/v1/speakers/enroll",
            data={"speaker_name": speaker_name, "face_id": "42"},
            files=enroll_files
        )
        assert enroll_res.status_code == 200, f"Enroll failed: {enroll_res.text}"

        speaker_service = get_speaker_service()
        speaker_service.invalidate()

        # 2. Test 1:N Identify on 0.25s audio (< 1s)
        ident_res = await client.post(
            "/api/v1/speakers/identify",
            files={"file": ("short.wav", subsecond_voice1, "audio/wav")}
        )
        assert ident_res.status_code == 200, f"Identify failed: {ident_res.text}"
        ident_data = ident_res.json()
        assert ident_data["is_identified"] is True
        assert ident_data["speaker_name"] == speaker_name
        assert ident_data["audio_seconds"] == 0.25
        assert ident_data["face_id"] == 42

        # 3. Test Compare on sub-second audio (0.25s vs 0.30s of same speaker)
        comp_res = await client.post(
            "/api/v1/speakers/compare?threshold=0.68",
            files={
                "file1": ("s1.wav", subsecond_voice1, "audio/wav"),
                "file2": ("s2.wav", subsecond_voice2, "audio/wav"),
            }
        )
        assert comp_res.status_code == 200, f"Compare sub-second failed: {comp_res.text}"
        comp_data = comp_res.json()
        assert comp_data["success"] is True
        assert comp_data["is_same_speaker"] is True
        assert comp_data["voice1"]["speaker_name"] == speaker_name
        assert comp_data["voice2"]["speaker_name"] == speaker_name
        assert comp_data["voice1"]["audio_seconds"] == 0.25
        assert comp_data["voice2"]["audio_seconds"] == 0.30

        # 4. Test Compare on sub-second audio of different speakers (0.25s vs 0.25s)
        comp_diff_res = await client.post(
            "/api/v1/speakers/compare?threshold=0.68",
            files={
                "file1": ("s1.wav", subsecond_voice1, "audio/wav"),
                "file2": ("diff.wav", subsecond_diff, "audio/wav"),
            }
        )
        assert comp_diff_res.status_code == 200
        comp_diff_data = comp_diff_res.json()
        assert comp_diff_data["is_same_speaker"] is False
        assert comp_diff_data["voice1"]["is_enrolled"] is True
        assert comp_diff_data["voice2"]["is_enrolled"] is False

        # Clean up
        await client.delete(f"/api/v1/speakers/{speaker_name}")
        speaker_service.invalidate()


@pytest.mark.asyncio
async def test_pure_speaker_biometrics_no_language_or_transcript():
    """Verify that speaker identification outputs pure biometric identity without language or transcript fields."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        v1 = generate_tone(150.0, 0.5)
        v2 = generate_tone(150.0, 0.5)
        res = await client.post(
            "/api/v1/speakers/compare",
            files={"file1": ("v1.wav", v1, "audio/wav"), "file2": ("v2.wav", v2, "audio/wav")}
        )
        assert res.status_code == 200
        data = res.json()
        # Verify language is NOT returned (pure speaker identity)
        assert "language" not in data["voice1"]
        assert "language_code" not in data["voice1"]
        assert "language" not in data["voice2"]
        assert "language_code" not in data["voice2"]
        # Verify transcripts are NOT returned
        assert "transcript" not in data["voice1"]
        assert "transcript" not in data["voice2"]
        # Verify pure identity fields are present
        assert "speaker_name" in data["voice1"]
        assert "is_enrolled" in data["voice1"]
        assert "similarity" in data["voice1"]
        assert "match_percentage" in data["voice1"]


@pytest.mark.asyncio
async def test_compare_two_different_enrolled_speakers_never_matches():
    """
    Verify that comparing two distinct enrolled individuals (e.g. منه vs يوستينا)
    is GUARANTEED to declare them different people with 0.0% match percentage,
    even if they share similar room acoustics or pitch.
    """
    spk_a_name = "EnrolledPersonA"
    spk_b_name = "EnrolledPersonB"

    # Person A (135 Hz) and Person B (220 Hz)
    spk_a_audio = generate_tone(135.0, 1.2)
    spk_b_audio = generate_tone(220.0, 1.2)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Enroll Person A
        res_a = await client.post(
            "/api/v1/speakers/enroll",
            data={"speaker_name": spk_a_name},
            files={"file": ("a.wav", spk_a_audio, "audio/wav")},
        )
        assert res_a.status_code == 200

        # Enroll Person B
        res_b = await client.post(
            "/api/v1/speakers/enroll",
            data={"speaker_name": spk_b_name},
            files={"file": ("b.wav", spk_b_audio, "audio/wav")},
        )
        assert res_b.status_code == 200

        speaker_service = get_speaker_service()
        speaker_service.invalidate()

        # Compare Person A vs Person B
        comp_res = await client.post(
            "/api/v1/speakers/compare?threshold=0.68",
            files={
                "file1": ("a.wav", spk_a_audio, "audio/wav"),
                "file2": ("b.wav", spk_b_audio, "audio/wav"),
            },
        )
        assert comp_res.status_code == 200
        data = comp_res.json()

        # MUST be different speakers with strictly 0.0% match percentage
        assert data["success"] is True
        assert data["is_same_speaker"] is False
        assert data["match_percentage"] == 0.0
        assert f"الصوت الأول لـ [{spk_a_name}]" in data["comparison_verdict"]
        assert f"الصوت الثاني لـ [{spk_b_name}]" in data["comparison_verdict"]
        assert "شخصين مختلفين" in data["comparison_verdict"]

        assert data["voice1"]["speaker_name"] == spk_a_name
        assert data["voice1"]["is_enrolled"] is True
        assert data["voice2"]["speaker_name"] == spk_b_name
        assert data["voice2"]["is_enrolled"] is True

        # Clean up
        await client.delete(f"/api/v1/speakers/{spk_a_name}")
        await client.delete(f"/api/v1/speakers/{spk_b_name}")
        speaker_service.invalidate()

