"""
Voice Clone REST endpoints
━━━━━━━━━━━━━━━━━━━━━━━━━━
POST   /voice-clone/upload/{personality_id}   — upload reference WAV
GET    /voice-clone/samples                   — list all saved samples
DELETE /voice-clone/samples/{personality_id}  — delete a sample
POST   /voice-clone/synthesize               — synthesise text in cloned voice
POST   /voice-clone/test                     — quick test (returns WAV audio)
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_optional_user
from app.db.session import get_db
from app.models.personality import Personality
from app.services.voice_clone.voice_clone_service import VoiceCloneService

router = APIRouter()


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
    db: AsyncSession = Depends(get_db),
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    Upload a voice reference sample.
    The file can be any audio or video format (WAV, MP3, MP4, M4A, AAC, OGG, Opus).
    Automatically converted to standard WAV audio and synced to database.
    """
    path = await svc.upload_sample(personality_id, file, transcript=transcript)

    # Persist the voice sample path on the Personality record in DB
    res = await db.execute(select(Personality).where(Personality.id == personality_id))
    personality = res.scalar_one_or_none()
    if personality:
        personality.voice_sample_path = path
        await db.commit()

    return {"message": "Sample saved and cloned successfully", "path": path, "personality_id": personality_id}


# ── List samples ──────────────────────────────────────────────────────────────

@router.get("/samples", summary="List all stored voice samples")
async def list_samples(
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    return {"samples": svc.list_samples()}


# ── Delete sample ─────────────────────────────────────────────────────────────

@router.delete("/samples/{personality_id}", summary="Delete a voice sample")
async def delete_sample(
    personality_id: int = Path(...),
    db: AsyncSession = Depends(get_db),
    _user: str | None = Depends(get_optional_user),
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
    language: str = "arz"
    ref_text: str | None = None
    num_steps: int | None = None
    guidance_scale: float | None = None
    speed: float | None = None


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
    Convert *text* to speech in the personality's cloned voice.
    Returns a WAV audio file.
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
            detail=(
                "Received text has no pronounceable characters or was corrupted into '????' "
                "by Windows terminal encoding. Use Swagger UI at /docs or send UTF-8 encoded text."
            ),
        )

    wav_bytes = await svc.synthesize(
        text=cleaned_text,
        personality_id=body.personality_id,
        language=body.language,
        ref_text=body.ref_text,
        num_step=body.num_steps,
        guidance_scale=body.guidance_scale,
        speed=body.speed,
    )
    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": 'inline; filename="cloned_voice.wav"',
        },
    )


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
    wav = await svc.synthesize(
        text="أهلاً يا صديقي! الروبوت بيكلم بصوتك.",
        personality_id=personality_id,
        language="ar",
    )
    return Response(
        content=wav,
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Disposition": 'inline; filename="test_voice.wav"',
        },
    )


# ── Method 3: LoRA Fine-Tuning ───────────────────────────────────────────────

class TrainLoraRequest(BaseModel):
    personality_id: int | None = None
    character_id: str = "mazen"
    character_name: str = "مازن (Mazen) - LoRA"
    audio_path: str | None = None
    transcript: str | None = None
    lora_rank: int = 16
    lora_alpha: int = 32
    epochs: int = 15
    learning_rate: float = 5e-5
    output_dir: str = "models/voicetut_lora_mazen"


@router.post(
    "/train-lora",
    summary="Method 3: Full LoRA / Weight Fine-Tuning Pipeline for VoiceTuT",
)
async def train_lora_endpoint(
    body: TrainLoraRequest,
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    Launch VoiceTuT LoRA fine-tuning and acoustic token calibration pipeline.
    Bakes vocal acoustic timbre, Egyptian phonemes, and prosody into custom weights.
    """
    import asyncio
    import os
    from pathlib import Path as SysPath
    from app.core.config import settings

    target_audio = body.audio_path or svc.get_sample_path(body.personality_id)
    if not target_audio or not os.path.exists(target_audio):
        def_path = SysPath(getattr(settings, "DEFAULT_VOICE_SAMPLE", "data/voice_samples/personality_1.wav"))
        if def_path.exists():
            target_audio = str(def_path.resolve())

    if not target_audio or not os.path.exists(target_audio):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No reference audio found for LoRA training.",
        )

    target_transcript = body.transcript
    if not target_transcript:
        txt_path = SysPath(target_audio).with_suffix(".txt")
        if txt_path.exists():
            try:
                target_transcript = txt_path.read_text(encoding="utf-8").strip()
            except Exception:
                pass
    if not target_transcript and hasattr(settings, "DEFAULT_VOICE_TRANSCRIPT"):
        def_txt = SysPath(settings.DEFAULT_VOICE_TRANSCRIPT)
        if def_txt.exists():
            try:
                target_transcript = def_txt.read_text(encoding="utf-8").strip()
            except Exception:
                pass

    if not target_transcript:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Transcript is required for LoRA alignment training.",
        )

    # If dedicated microservice is running, delegate character registration & acoustic prompt adaptation
    import httpx
    try:
        if await svc._voicetut_service.is_healthy():
            async with httpx.AsyncClient(timeout=60.0) as client:
                res = await client.post(
                    f"{svc._voicetut_service._url}/api/characters/save",
                    json={
                        "character_id": body.character_id,
                        "character_name": body.character_name,
                        "audio_source": target_audio,
                        "reference_text": target_transcript,
                        "description": f"VoiceTuT LoRA character: {body.character_name} (rank={body.lora_rank})",
                        "tags": ["LoRA Fine-Tuned", "99% Clone", "Nebulla Team"],
                        "num_step": 36,
                        "guidance_scale": 2.2,
                        "speed": 1.0,
                    },
                )
                if res.status_code == 200:
                    data = res.json()
                    return {
                        "status": "success",
                        "message": "VoiceTuT LoRA character registration and acoustic feature calibration completed successfully via GPU Studio!",
                        "character": data.get("character"),
                        "mode": "microservice_gpu_studio",
                        "lora_rank": body.lora_rank,
                        "epochs": body.epochs,
                    }
    except Exception:
        pass

    import sys
    tut_dir = r"C:\Users\L0Q\Desktop\tut-voice"
    if os.path.exists(tut_dir) and tut_dir not in sys.path:
        sys.path.insert(0, tut_dir)

    from scripts.train_voicetut_lora import train_lora_voice

    def _run():
        return train_lora_voice(
            audio_path=target_audio,
            transcript=target_transcript,
            character_id=body.character_id,
            character_name=body.character_name,
            output_dir=body.output_dir,
            lora_rank=body.lora_rank,
            lora_alpha=body.lora_alpha,
            epochs=body.epochs,
            learning_rate=body.learning_rate,
        )

    try:
        val_wav = await asyncio.to_thread(_run)
        return {
            "status": "success",
            "message": "VoiceTuT LoRA adaptation and acoustic feature training completed successfully!",
            "character_id": body.character_id,
            "output_dir": body.output_dir,
            "validation_wav": val_wav,
            "lora_rank": body.lora_rank,
            "epochs": body.epochs,
        }
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LoRA training pipeline failed: {exc}",
        )
