# -*- coding: utf-8 -*-
import io
import wave
import subprocess
import numpy as np
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.services.voice_verification.speaker_service import get_speaker_service, decode_audio


def generate_wav(freq: float = 220.0, duration_sec: float = 1.5, sr: int = 16000) -> bytes:
    t = np.linspace(0, duration_sec, int(sr * duration_sec), endpoint=False)
    sig = 0.5 * np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(4 * np.pi * freq * t)
    pcm = (sig * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


@pytest.mark.asyncio
async def test_universal_recorder_and_crossmodal_ids():
    wav_bytes = generate_wav(freq=180.0, duration_sec=1.5)

    # 1. Test universal decode on WAV
    pcm = decode_audio(wav_bytes)
    assert pcm is not None and len(pcm) >= 16000

    # 2. Test universal decode on compressed format using imageio_ffmpeg
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        proc = subprocess.run(
            [exe, "-y", "-i", "pipe:0", "-f", "mp3", "pipe:1"],
            input=wav_bytes,
            capture_output=True,
            check=True
        )
        mp3_bytes = proc.stdout
        pcm_from_mp3 = decode_audio(mp3_bytes)
        assert pcm_from_mp3 is not None
        assert len(pcm_from_mp3) > 10000
    except Exception as e:
        pytest.fail(f"Universal MP3 decode failed: {e}")

    # 3. Test API enrollment with face_id, personality_id, memory_id
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Enroll test speaker "TestCrossModal"
        files = {"file": ("sample.wav", wav_bytes, "audio/wav")}
        data = {
            "speaker_name": "TestCrossModal",
            "face_id": "12",
            "personality_id": "34",
            "memory_id": "56",
        }
        res = await client.post("/api/v1/speakers/enroll", files=files, data=data)
        assert res.status_code == 200, f"Enroll failed: {res.text}"
        enroll_payload = res.json()
        assert enroll_payload["success"] is True
        assert enroll_payload["face_id"] == 12
        assert enroll_payload["personality_id"] == 34
        assert enroll_payload["memory_id"] == 56

        # 4. Test identify returns face_id, personality_id, memory_id
        res_ident = await client.post("/api/v1/speakers/identify", files={"file": ("sample.wav", wav_bytes, "audio/wav")})
        assert res_ident.status_code == 200
        ident_payload = res_ident.json()
        assert ident_payload["is_identified"] is True
        assert ident_payload["speaker_name"] == "TestCrossModal"
        assert ident_payload["face_id"] == 12
        assert ident_payload["personality_id"] == 34
        assert ident_payload["memory_id"] == 56

        # Clean up enrolled test speaker
        await client.delete("/api/v1/speakers/TestCrossModal")
