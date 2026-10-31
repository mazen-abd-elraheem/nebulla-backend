# -*- coding: utf-8 -*-
import io
import wave
import numpy as np
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.voice_verification.speaker_service import get_speaker_service


def generate_harmonic_speech(freq: float, duration_sec: float, sr: int = 16000) -> np.ndarray:
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    sig = 0.5 * np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t) + 0.15 * np.sin(6 * np.pi * freq * t)
    sig += np.random.normal(0, 0.005, size=t.shape)
    return (sig * 32767).astype(np.int16)


def create_composite_wav(sr: int = 16000) -> bytes:
    # Speaker A (130 Hz) - Turn 1 (2.0s)
    spk_a_turn1 = generate_harmonic_speech(130, 2.0, sr)
    silence = np.zeros(int(sr * 0.5), dtype=np.int16)
    # Speaker B (250 Hz) - Turn 2 (2.0s)
    spk_b_turn2 = generate_harmonic_speech(250, 2.0, sr)
    # Speaker A (130 Hz) - Turn 3 (2.0s)
    spk_a_turn3 = generate_harmonic_speech(130, 2.0, sr)

    combined = np.concatenate([spk_a_turn1, silence, spk_b_turn2, silence, spk_a_turn3])
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(combined.tobytes())
    return buf.getvalue()


@pytest.mark.asyncio
async def test_diarization_service_and_endpoint():
    wav_bytes = create_composite_wav()
    transcripts_json = (
        '[{"turn_index": 1, "text": "أهلاً وسهلاً بكم في هذا الاجتماع"},'
        ' {"turn_index": 2, "text": "Good morning everyone let us proceed"},'
        ' {"turn_index": 3, "text": "Thank you I will conclude the session in English"}]'
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("conversation.wav", wav_bytes, "audio/wav")}
        data = {"transcripts_json": transcripts_json}
        res = await client.post("/api/v1/speakers/diarize", files=files, data=data)

        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
        payload = res.json()

        assert payload["success"] is True
        assert payload["total_speakers_count"] == 2
        assert "العربية (Arabic)" in payload["all_detected_languages"]
        assert "الإنجليزية (English)" in payload["all_detected_languages"]

        # Check multilingual speakers detection: Speaker 1 spoke Arabic in Turn 1 and English in Turn 3
        multi_list = payload["multilingual_speakers"]
        assert len(multi_list) >= 1, "Expected at least one multilingual speaker"
        multi_spk = multi_list[0]
        assert "العربية (Arabic)" in multi_spk["languages"]
        assert "الإنجليزية (English)" in multi_spk["languages"]
        assert len(payload["timeline_segments"]) == 3
