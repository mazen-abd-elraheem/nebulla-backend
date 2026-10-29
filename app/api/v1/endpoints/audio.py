"""
Audio REST endpoints for Speech-to-Text (STT) and VoiceTut Egyptian Speech Synthesis / Cloning.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
POST /api/v1/audio/transcribe  — transcribe any audio file (WAV, MP3, M4A, etc.) to text
POST /api/v1/audio/voicetut    — synthesize text using VoiceTut (speaker preset or cloned voice)
GET  /api/v1/audio/speakers    — list available Egyptian speakers in VoiceTut
"""

import io
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response

from app.auth.jwt import get_optional_user
from app.core.config import settings
from app.core.logger import get_logger
from app.providers.tts.voicetut import VoiceTutProvider
from app.services.voice_clone.voice_clone_service import _save_and_convert_to_wav, _wav_duration

logger = get_logger(__name__)

router = APIRouter()
_voicetut = VoiceTutProvider()

_AUDIO_RESPONSES = {
    200: {
        "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}},
        "description": "WAV audio file",
    }
}


# ── Transcribe (STT) ──────────────────────────────────────────────────────────

@router.post(
    "/transcribe",
    summary="Transcribe spoken audio into text (STT)",
)
async def transcribe_audio(
    file: UploadFile = File(..., description="Audio file (WAV, MP3, M4A, OGG, FLAC, etc.)"),
    provider: Optional[str] = Form(None, description="STT provider name (default from settings)"),
    _user: Optional[str] = Depends(get_optional_user),
):
    """
    Transcribe speech from an uploaded audio file into Arabic text.
    Supports all mobile and desktop formats (WAV, MP3, M4A, AAC, etc.).
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Filename is missing.",
        )

    ext = Path(file.filename).suffix.lower()
    allowed_exts = {
        ".wav", ".mp3", ".m4a", ".mp4", ".ogg", ".opus",
        ".flac", ".aac", ".3gp", ".webm", ".wma", ".amr"
    }
    if ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported format '{ext}'. Accepted: {', '.join(sorted(allowed_exts))}",
        )

    raw_bytes = await file.read()
    if len(raw_bytes) < 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Audio file is empty or corrupted.",
        )

    # Convert to standard WAV for STT models
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_wav:
        tmp_dest = Path(tmp_wav.name)

    try:
        duration_s = _save_and_convert_to_wav(raw_bytes, ext, tmp_dest)
        wav_data = tmp_dest.read_bytes()
    finally:
        if tmp_dest.exists():
            try:
                tmp_dest.unlink()
            except OSError:
                pass

    chosen_provider = provider or settings.STT_PROVIDER
    t0 = time.perf_counter()

    try:
        from app.providers.stt.factory import get_stt_provider
        stt_instance = get_stt_provider(chosen_provider)
        transcript = await stt_instance.transcribe(wav_data)
    except Exception as exc:
        logger.error(f"STT transcription failed with provider '{chosen_provider}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {exc}",
        )

    latency_ms = (time.perf_counter() - t0) * 1000

    return {
        "success": True,
        "transcription": transcript,
        "duration_s": round(duration_s, 2),
        "latency_ms": round(latency_ms, 1),
        "provider": chosen_provider,
        "filename": file.filename,
    }


# ── VoiceTut Synthesis & Cloning ──────────────────────────────────────────────

@router.post(
    "/voicetut",
    summary="Synthesize or clone voice directly using VoiceTut-TTS (returns WAV)",
    response_class=Response,
    responses=_AUDIO_RESPONSES,
)
async def synthesize_voicetut(
    text: str = Form(..., description="Arabic text to synthesize"),
    speaker: Optional[str] = Form(None, description="Pre-built speaker name (e.g. mohammed, yasmin, ahmed)"),
    file: Optional[UploadFile] = File(None, description="Optional audio file for zero-shot voice cloning"),
    ref_text: Optional[str] = Form(None, description="Optional transcript of the reference audio"),
    num_steps: Optional[int] = Form(None, description="Denoising steps (4 for fast test, 10 for high fidelity)"),
    _user: Optional[str] = Depends(get_optional_user),
):
    """
    Generate Egyptian Arabic speech using VoiceTut-TTS.
    - If a reference audio `file` is provided: clones that voice (zero-shot).
    - If no file is provided: uses the specified pre-built Egyptian `speaker`.
    Returns a standard WAV audio stream.
    """
    cleaned_text = text.strip()
    if not cleaned_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text cannot be empty.",
        )

    ref_audio_path = None
    temp_ref_path = None

    if file and file.filename:
        ext = Path(file.filename).suffix.lower()
        raw_bytes = await file.read()
        if len(raw_bytes) > 100:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
                temp_ref_path = Path(tmp_f.name)
            _save_and_convert_to_wav(raw_bytes, ext, temp_ref_path)
            ref_audio_path = str(temp_ref_path)

    try:
        t0 = time.perf_counter()
        wav_bytes = await _voicetut.synthesize(
            text=cleaned_text,
            speaker=speaker,
            ref_audio=ref_audio_path,
            ref_text=ref_text,
            num_step=num_steps,
        )
        latency_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"VoiceTut synthesis completed in {latency_ms:.1f}ms ({len(wav_bytes):,} bytes)")

        return Response(
            content=wav_bytes,
            media_type="audio/wav",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Disposition": 'inline; filename="voicetut_output.wav"',
                "X-Latency-Ms": str(round(latency_ms, 1)),
            },
        )
    finally:
        if temp_ref_path and temp_ref_path.exists():
            try:
                temp_ref_path.unlink()
            except OSError:
                pass


# ── List VoiceTut Speakers ────────────────────────────────────────────────────

@router.get(
    "/speakers",
    summary="List available cloned Egyptian speakers in VoiceTut",
)
async def list_speakers(
    _user: Optional[str] = Depends(get_optional_user),
):
    """Return all available cloned Egyptian speaker names in VoiceTut."""
    speakers = VoiceTutProvider.list_speakers()
    default_speaker = "mazen" if "mazen" in speakers else (speakers[0] if speakers else "personality_1")
    return {
        "speakers": speakers,
        "count": len(speakers),
        "default": default_speaker,
    }
