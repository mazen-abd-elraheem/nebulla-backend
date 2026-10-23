"""
Voice Clone REST endpoints
━━━━━━━━━━━━━━━━━━━━━━━━━━
POST   /voice-clone/upload/{personality_id}   — upload reference WAV
GET    /voice-clone/samples                   — list all saved samples
DELETE /voice-clone/samples/{personality_id}  — delete a sample
POST   /voice-clone/synthesize               — synthesise text in cloned voice
POST   /voice-clone/test                     — quick test (returns WAV audio)
"""

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.session import get_db
from app.models.personality import Personality
from app.services.voice_clone.voice_clone_service import VoiceCloneService

router = APIRouter()


def _svc() -> VoiceCloneService:
    return VoiceCloneService.get_instance()


# ── Upload ────────────────────────────────────────────────────────────────────

@router.post(
    "/upload/{personality_id}",
    summary="Upload a voice reference sample (WAV or MP4) for a personality",
    status_code=status.HTTP_201_CREATED,
)
async def upload_voice_sample(
    personality_id: int = Path(..., description="The personality to bind this voice to"),
    file: UploadFile = File(..., description="WAV or MP4 file, 3–120 seconds of clean speech"),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    Upload a voice reference sample.
    The file must be a WAV or MP4 (audio or video), at least 3 seconds long.
    MP4 files are automatically converted to standard WAV audio.
    Longer samples (30–60 s) produce better cloning quality.
    """
    path = await svc.upload_sample(personality_id, file)

    # Persist the voice sample path on the Personality record in DB
    res = await db.execute(select(Personality).where(Personality.id == personality_id))
    personality = res.scalar_one_or_none()
    if personality:
        personality.voice_sample_path = path
        await db.commit()

    return {"message": "Sample saved", "path": path, "personality_id": personality_id}


# ── List samples ──────────────────────────────────────────────────────────────

@router.get("/samples", summary="List all stored voice samples")
async def list_samples(
    _user: str = Depends(get_current_user),
    svc: VoiceCloneService = Depends(_svc),
):
    return {"samples": svc.list_samples()}


# ── Delete sample ─────────────────────────────────────────────────────────────

@router.delete("/samples/{personality_id}", summary="Delete a voice sample")
async def delete_sample(
    personality_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
    svc: VoiceCloneService = Depends(_svc),
):
    deleted = await svc.delete_sample(personality_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found")

    res = await db.execute(select(Personality).where(Personality.id == personality_id))
    personality = res.scalar_one_or_none()
    if personality:
        personality.voice_sample_path = None
        await db.commit()

    return {"message": "Sample deleted", "personality_id": personality_id}


# ── Synthesise ────────────────────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    text: str
    personality_id: int | None = None
    language: str = "ar"


@router.post(
    "/synthesize",
    summary="Synthesise text in a cloned voice (returns WAV audio bytes)",
    response_class=Response,
)
async def synthesize(
    body: SynthesizeRequest,
    _user: str = Depends(get_current_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    Convert *text* to speech in the personality's cloned voice.
    Returns a WAV audio file.
    """
    wav_bytes = await svc.synthesize(
        text=body.text,
        personality_id=body.personality_id,
        language=body.language,
    )
    return Response(content=wav_bytes, media_type="audio/wav")


# ── Quick test ────────────────────────────────────────────────────────────────

@router.post(
    "/test",
    summary="Quick voice clone test — say hello in Egyptian Arabic",
    response_class=Response,
)
async def test_voice(
    personality_id: int | None = Query(None),
    _user: str = Depends(get_current_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """Returns a short WAV clip of 'أهلاً يا صديقي!' in the cloned voice."""
    wav = await svc.synthesize(
        text="أهلاً يا صديقي! الروبوت بيكلم بصوتك.",
        personality_id=personality_id,
        language="ar",
    )
    return Response(content=wav, media_type="audio/wav")
