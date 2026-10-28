"""
Voice Clone REST endpoints
━━━━━━━━━━━━━━━━━━━━━━━━━━
POST   /voice-clone/upload/{personality_id}   — upload reference WAV
GET    /voice-clone/samples                   — list all saved samples
GET    /voice-clone/voices                    — list available cloned voices
DELETE /voice-clone/samples/{personality_id}  — delete a sample
POST   /voice-clone/synthesize               — synthesise text in cloned voice
GET    /voice-clone/synthesize               — play or stream cloned voice (Swagger UI / browser audio)
POST   /voice-clone/test                     — quick test (returns WAV audio)
GET    /voice-clone/test                     — quick test (playable directly in browser)
"""

import os
import pathlib
from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.auth.jwt import get_current_user, get_optional_user
from app.core.config import settings
from app.services.voice_clone.voice_clone_service import VoiceCloneService

router = APIRouter()
_last_synthesized_audio: dict = {}
CACHE_DIR = pathlib.Path("data/voice_samples")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LATEST_WAV_FILE = CACHE_DIR / "latest_synthesized.wav"


def _svc() -> VoiceCloneService:
    return VoiceCloneService.get_instance()


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post(
    "/upload",
    summary="Upload any audio/recording/video file to clone voice immediately",
    status_code=status.HTTP_201_CREATED,
)
async def upload_voice_sample_default(
    file: UploadFile = File(..., description="Audio or video file (WAV, MP3, MP4, M4A, AAC, OGG, Opus), 1.5–120s"),
    transcript: str | None = Form(None, description="Optional text transcript of the spoken audio for max cloning accuracy"),
    personality_id: int | None = Form(None, description="Optional personality ID (defaults to active personality or 1)"),
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    Upload any voice recording (WAV, MP3, MP4, M4A, etc.) to immediately clone it.
    Automatically binds to the active personality and updates the database.
    """
    pid = personality_id or 1
    path = await svc.upload_sample(pid, file, transcript=transcript)
    return {
        "message": "Voice recording uploaded and cloned successfully!",
        "path": path,
        "personality_id": pid,
    }


@router.post(
    "/upload/{personality_id}",
    summary="Upload a voice reference sample (WAV, MP4, etc.) for a specific personality",
    status_code=status.HTTP_201_CREATED,
)
async def upload_voice_sample(
    personality_id: int = Path(..., description="The personality to bind this voice to"),
    file: UploadFile = File(..., description="WAV, MP3, MP4, M4A, etc., 1.5–120 seconds of clean speech"),
    transcript: str | None = Form(None, description="Optional text transcript of the spoken audio for max cloning accuracy"),
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    Upload a voice reference sample.
    The file can be any audio or video format (WAV, MP3, MP4, M4A, AAC, OGG, Opus).
    Automatically converted to standard WAV audio and synced to database.
    """
    path = await svc.upload_sample(personality_id, file, transcript=transcript)
    return {"message": "Sample saved and cloned successfully", "path": path, "personality_id": personality_id}


# ── List samples ──────────────────────────────────────────────────────────────

@router.get("/samples", summary="List all stored voice samples")
async def list_samples(
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    return {"samples": svc.list_samples()}


@router.get("/voices", summary="List all available cloned voice samples")
async def list_available_voices(
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    Returns all cloned voice samples available in the system.
    """
    samples = svc.list_samples()
    return {
        "active_provider": settings.TTS_PROVIDER,
        "cloned_samples": samples,
        "usage_example": {
            "voice_id": 1,
            "text": "أهلاً بيك، الصوت ده مستنسخ بصوتك المرفوع على النظام",
        }
    }


# ── Delete sample ─────────────────────────────────────────────────────────────

@router.delete("/samples/{personality_id}", summary="Delete a voice sample")
async def delete_sample(
    personality_id: int = Path(...),
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    deleted = await svc.delete_sample(personality_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found")
    return {"message": "Sample deleted", "personality_id": personality_id}


# ── Synthesise ────────────────────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    text: str = Field(..., description="النص العربي المراد نطقه بالصوت المستنسخ", examples=["أهلاً بيكم يا شباب، الصوت المصري المستنسخ شغال تمام!"])
    personality_id: int | None = Field(1, description="معرف الشخصية / الصوت المستنسخ (ID) - مثلاً 1 للاستنساخ على عينة الصوت رقم 1", examples=[1])
    voice_id: int | None = Field(None, description="معرف الصوت (ID) - رقم العينة المستنسخة مثل 1", examples=[1])
    language: str = Field("ar", description="Language code (default: ar)", examples=["ar"])
    ref_text: str | None = Field(None, description="نص العينة المرجعية إن وجد لرفع الدقة", examples=[None])
    num_steps: int | None = Field(4, description="خطوات التوليد (4 لتوليد سريع على كارت الشاشة)", examples=[4])


_AUDIO_RESPONSES = {
    200: {
        "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}},
        "description": "WAV audio file",
    }
}


@router.post(
    "/synthesize",
    summary="Synthesise text in a cloned voice (returns WAV audio bytes)",
    response_class=Response,
    responses=_AUDIO_RESPONSES,
)
async def synthesize(
    body: SynthesizeRequest,
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    Convert *text* to speech strictly in the user's cloned voice using VoiceTut.
    Returns a WAV audio file. No fallback models used.
    """
    cleaned_text = body.text.strip()
    if not cleaned_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text cannot be empty.",
        )
    if all(ch in "?!.,;: \t\n\r" for ch in cleaned_text):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Received text has no pronounceable characters.",
        )

    # Sanitize target PID
    target_pid: int | None = None
    if body.voice_id is not None:
        try:
            target_pid = int(body.voice_id)
        except Exception:
            target_pid = None

    if target_pid is None and body.personality_id is not None and body.personality_id > 0:
        target_pid = body.personality_id

    if target_pid is None:
        target_pid = 1

    actual_ref_text = body.ref_text if (body.ref_text and body.ref_text.strip() and body.ref_text.strip() != "string") else None
    steps = body.num_steps if (body.num_steps and body.num_steps > 0) else 4

    wav_bytes = await svc.synthesize(
        text=cleaned_text,
        personality_id=target_pid,
        language=body.language,
        ref_text=actual_ref_text,
        num_step=steps,
    )

    # Cache latest audio to disk and memory for immediate browser streaming
    try:
        LATEST_WAV_FILE.write_bytes(wav_bytes)
    except Exception:
        pass

    cache_key = target_pid if target_pid is not None else 1
    _last_synthesized_audio[cache_key] = wav_bytes
    _last_synthesized_audio["latest"] = wav_bytes

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(wav_bytes)),
            "Content-Disposition": 'inline; filename="cloned_voice.wav"',
        },
    )


@router.get(
    "/synthesize",
    summary="Play or stream cloned voice (supports browser audio players & Swagger UI)",
    response_class=Response,
    responses=_AUDIO_RESPONSES,
)
async def synthesize_get(
    text: str | None = Query(None, description="النص المراد نطقه بالصوت المستنسخ"),
    voice_id: int | None = Query(None, description="معرف الصوت المستنسخ (ID مثل 1)"),
    personality_id: int | None = Query(None, description="معرف الشخصية (ID مثل 1)"),
    num_steps: int | None = Query(4, description="عدد خطوات التوليد (الافتراضي: 4 للسرعة)"),
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    GET endpoint for `/synthesize`:
    1. If called without text (e.g. by Swagger UI embedded <audio> tag or browser),
       it immediately serves the latest synthesized audio clip with byte-range support.
    2. If text is provided, it generates speech on-the-fly in the cloned voice and streams it back.
    """
    if text and text.strip():
        req = SynthesizeRequest(
            text=text,
            voice_id=voice_id,
            personality_id=personality_id,
            num_steps=num_steps or 4,
        )
        return await synthesize(req, _user=_user, svc=svc)

    if LATEST_WAV_FILE.exists() and LATEST_WAV_FILE.stat().st_size > 0:
        return FileResponse(
            path=str(LATEST_WAV_FILE),
            media_type="audio/wav",
            content_disposition_type="inline",
            filename="cloned_voice.wav",
        )

    pid = personality_id or (int(voice_id) if voice_id else 1)
    cached = _last_synthesized_audio.get(pid) or _last_synthesized_audio.get("latest")
    if cached:
        return Response(
            content=cached,
            media_type="audio/wav",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(cached)),
                "Content-Disposition": 'inline; filename="cloned_voice.wav"',
            },
        )

    # Fallback default
    req = SynthesizeRequest(
        text="أهلاً بيك يا صديقي! الصوت المصري المستنسخ شغال وجاهز تماماً.",
        personality_id=pid,
        num_steps=4,
    )
    return await synthesize(req, _user=_user, svc=svc)


# ── Quick test ────────────────────────────────────────────────────────────────

@router.post(
    "/test",
    summary="Quick voice clone test — say hello in Egyptian Arabic",
    response_class=Response,
    responses=_AUDIO_RESPONSES,
)
async def test_voice(
    personality_id: int | None = Query(None),
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """Returns a short WAV clip of 'أهلاً يا صديقي!' in the cloned voice."""
    pid = personality_id or 1
    wav_bytes = await svc.synthesize(
        text="أهلاً يا صديقي! الروبوت بيكلم بصوتك المستنسخ.",
        personality_id=pid,
        language="ar",
        num_step=4,
    )
    try:
        LATEST_WAV_FILE.write_bytes(wav_bytes)
    except Exception:
        pass

    _last_synthesized_audio[pid] = wav_bytes
    _last_synthesized_audio["latest"] = wav_bytes

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(wav_bytes)),
            "Content-Disposition": 'inline; filename="test_voice.wav"',
        },
    )


@router.get(
    "/test",
    summary="Quick voice clone test via GET (playable directly in browser)",
    response_class=Response,
    responses=_AUDIO_RESPONSES,
)
async def test_voice_get(
    personality_id: int | None = Query(None),
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    return await test_voice(personality_id=personality_id, _user=_user, svc=svc)
