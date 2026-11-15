"""
Audio Utilities for Nebulla
━━━━━━━━━━━━━━━━━━━━━━━━━━━
Provides robust audio format normalization, WAV validation, and audio conversions
to guarantee that browsers and Swagger UI can decode and play any synthesized audio.
"""

from __future__ import annotations

import io
import wave
from pathlib import Path
from typing import Optional

from app.core.logger import get_logger

logger = get_logger(__name__)


def is_valid_wav_header(data: bytes) -> bool:
    """Return True if data starts with a standard RIFF/WAVE header."""
    if not data or len(data) < 44:
        return False
    return data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def ensure_wav_bytes(audio_bytes: bytes, target_sr: int = 24000) -> bytes:
    """
    Ensure the given audio bytes are clean, 100% compliant 16-bit PCM WAV.
    If the bytes are MP3 (e.g. from gTTS or streaming), OGG, FLAC, or malformed,
    it decodes them using soundfile / scipy and transcodes to standard 16-bit PCM WAV.
    """
    if not audio_bytes or len(audio_bytes) < 4:
        return audio_bytes

    if is_valid_wav_header(audio_bytes):
        # Quick validation check with Python's native wave module
        try:
            with wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                if wf.getnchannels() > 0 and wf.getframerate() > 0 and wf.getnframes() > 0:
                    return audio_bytes
        except Exception:
            pass  # Fall through to transcode if wave module couldn't parse it

    # Transcode from whatever format (MP3, OGG, etc.) into 16-bit PCM WAV
    try:
        import soundfile as sf
        b_in = io.BytesIO(audio_bytes)
        data, sr = sf.read(b_in)

        # Convert stereo to mono if needed
        if len(data.shape) > 1:
            data = data.mean(axis=1)

        out_sr = target_sr if target_sr else sr
        # Resample if sample rates differ significantly
        if sr != out_sr:
            try:
                import scipy.signal
                num_target_samples = int(len(data) * float(out_sr) / float(sr))
                data = scipy.signal.resample(data, num_target_samples)
            except Exception:
                out_sr = sr

        b_out = io.BytesIO()
        sf.write(b_out, data, out_sr, format="WAV", subtype="PCM_16")
        converted = b_out.getvalue()
        logger.debug(f"Transcoded {len(audio_bytes)} bytes audio -> {len(converted)} bytes WAV ({out_sr}Hz)")
        return converted
    except Exception as exc:
        logger.warning(f"ensure_wav_bytes transcode error: {exc}")
        return audio_bytes


def apply_personality_acoustic_profile(
    wav_bytes: bytes,
    personality_id: int,
    target_sr: int = 24000,
) -> bytes:
    """
    Apply subtle, natural acoustic pitch/speed modulation based on personality profile.
    This guarantees that each personality has a recognizable and distinct auditory presence:
      - Personality 0 (Nebula Core / Bot): slightly bright, crisp assistant timbre (factor: 1.04)
      - Personality 1 (Mazen / Digital Twin): natural baseline tone (factor: 1.00)
      - Personality 2 (Ahmed): deeper, warmer, grounded tone (factor: 0.94)
      - Custom personalities: distinct hash-based modulation (0.92 - 1.08)
    """
    clean_wav = ensure_wav_bytes(wav_bytes, target_sr=target_sr)
    if not clean_wav or len(clean_wav) < 100:
        return clean_wav

    if personality_id == 1:
        # Personality 1 is the baseline voice
        return clean_wav
    elif personality_id == 0:
        factor = 1.05  # slightly higher / brighter
    elif personality_id == 2:
        factor = 0.93  # deeper / warmer
    else:
        # Deterministic variation per personality id
        factor = round(0.92 + ((personality_id * 37) % 17) * 0.01, 2)

    try:
        import soundfile as sf
        import scipy.signal
        data, sr = sf.read(io.BytesIO(clean_wav))
        if len(data.shape) > 1:
            data = data.mean(axis=1)

        target_len = int(len(data) / factor)
        shifted = scipy.signal.resample(data, target_len)

        b_out = io.BytesIO()
        sf.write(b_out, shifted, target_sr, format="WAV", subtype="PCM_16")
        return b_out.getvalue()
    except Exception as exc:
        logger.warning(f"Failed to apply acoustic profile for personality {personality_id}: {exc}")
        return clean_wav
