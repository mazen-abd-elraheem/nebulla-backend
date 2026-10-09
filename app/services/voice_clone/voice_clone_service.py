"""
Voice Clone Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

High-level service that manages:
  • Voice sample upload + validation
  • Personality ↔ reference-WAV binding
  • XTTS synthesis with the cloned voice
  • Streaming chunks back to the phone app

Used by the REST API (/api/v1/voice-clone/*) and by the AI pipeline.
"""

import io
import os
import uuid
import wave
from pathlib import Path
from typing import AsyncIterator

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.tts.xtts.provider import XTTSProvider

logger = get_logger(__name__)

_SAMPLES_DIR = Path("data/voice_samples")
_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

_MIN_DURATION_S = 3.0    # minimum acceptable sample length
_MAX_DURATION_S = 120.0  # cap to avoid huge uploads


class VoiceCloneService:
    """
    Manages voice samples and drives XTTS synthesis.
    One XTTSProvider is shared and the reference wav is swapped per request.
    """

    def __init__(self):
        self._xtts = XTTSProvider()
        self._personality_voice_map: dict[int, str] = {}  # personality_id → wav path

    # ── Sample management ─────────────────────────────────────────────────────

    async def upload_sample(
        self,
        personality_id: int,
        file: UploadFile,
    ) -> str:
        """
        Receive an audio upload, validate it, save it, and bind it to a personality.

        Returns the saved file path.
        Accepted formats: .wav  (other formats should be converted client-side)
        """
        if not file.filename or not file.filename.lower().endswith(".wav"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Only WAV files are accepted. Please convert your recording first.",
            )

        raw = await file.read()
        duration = _wav_duration(raw)

        if duration < _MIN_DURATION_S:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Sample too short ({duration:.1f}s). Minimum is {_MIN_DURATION_S}s.",
            )
        if duration > _MAX_DURATION_S:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Sample too long ({duration:.1f}s). Maximum is {_MAX_DURATION_S}s.",
            )

        # Save with a stable name per personality (overwrite on re-upload)
        filename = f"personality_{personality_id}.wav"
        dest = _SAMPLES_DIR / filename
        dest.write_bytes(raw)

        self._personality_voice_map[personality_id] = str(dest)
        logger.info(f"Voice sample saved for personality {personality_id}: {dest} ({duration:.1f}s)")
        return str(dest)

    def get_sample_path(self, personality_id: int) -> str | None:
        """Return the stored WAV path for a personality, or None if not found."""
        # Check in-memory map first
        if personality_id in self._personality_voice_map:
            return self._personality_voice_map[personality_id]
        # Fall back to disk
        p = _SAMPLES_DIR / f"personality_{personality_id}.wav"
        if p.exists():
            self._personality_voice_map[personality_id] = str(p)
            return str(p)
        return None

    def list_samples(self) -> list[dict]:
        """List all stored voice samples."""
        results = []
        for wav in sorted(_SAMPLES_DIR.glob("personality_*.wav")):
            pid_str = wav.stem.replace("personality_", "")
            try:
                pid = int(pid_str)
                duration = _wav_duration(wav.read_bytes())
                results.append({
                    "personality_id": pid,
                    "filename": wav.name,
                    "duration_s": round(duration, 2),
                    "size_bytes": wav.stat().st_size,
                })
            except Exception:
                pass
        return results

    async def delete_sample(self, personality_id: int) -> bool:
        """Delete a stored voice sample."""
        p = _SAMPLES_DIR / f"personality_{personality_id}.wav"
        if p.exists():
            p.unlink()
            self._personality_voice_map.pop(personality_id, None)
            logger.info(f"Deleted voice sample for personality {personality_id}")
            return True
        return False

    # ── Synthesis ─────────────────────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        personality_id: int | None = None,
        reference_wav: str | None = None,
        language: str = "ar",
    ) -> bytes:
        """
        Synthesise *text* in the cloned voice.

        Priority of voice reference:
          1. Explicit reference_wav path (override)
          2. Personality-bound sample (personality_id lookup)
          3. Default XTTS reference (from settings)

        Returns WAV bytes.
        """
        wav_path = reference_wav or (
            self.get_sample_path(personality_id) if personality_id else None
        )

        if wav_path:
            return await self._xtts.clone_voice(wav_path, text, language)
        else:
            return await self._xtts.synthesize(text)

    async def synthesize_stream(
        self,
        text: str,
        personality_id: int | None = None,
        reference_wav: str | None = None,
        language: str = "ar",
    ) -> AsyncIterator[bytes]:
        """Streaming variant — yields WAV chunks for low-latency playback."""
        wav_bytes = await self.synthesize(text, personality_id, reference_wav, language)
        chunk_size = 4096
        for i in range(0, len(wav_bytes), chunk_size):
            yield wav_bytes[i : i + chunk_size]

    # ── Singleton ─────────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "VoiceCloneService":
        """Return the process-level singleton."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance


# ── Internal helpers ──────────────────────────────────────────────────────────

def _wav_duration(raw: bytes) -> float:
    """Return the duration of a WAV file in seconds."""
    try:
        with wave.open(io.BytesIO(raw)) as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0
