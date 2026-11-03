"""
Speaker Management & Voiceprint Verification / Identification API Endpoints.
(benefits_section.docx §14.3, "التحقق بالصوت").

Endpoints:
  - POST /api/v1/speakers/identify: 1:N Speaker identification from recorded audio.
      Returns speaker identity or "الصوت غير مسجل في السيستم" (Unknown Speaker).
  - POST /api/v1/speakers/enroll: Enroll/register a new speaker voiceprint.
  - GET  /api/v1/speakers: List all enrolled speakers.
  - DELETE /api/v1/speakers/{speaker_name}: Delete a speaker voiceprint.
  - GET  /api/v1/speakers/status: Get voice engine backend & enrollment statistics.
"""

import io
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import get_db
from app.models.voiceprint import Voiceprint
from app.services.voice_verification.speaker_service import (
    AudioDecodeError,
    VoiceprintError,
    decode_audio,
    get_speaker_service,
)

logger = get_logger(__name__)

router = APIRouter()


@router.post(
    "/identify",
    summary="Identify speaker from audio (1:N identification)",
    description=(
        "Identify who is speaking from recorded audio. "
        "Returns the matching speaker name, match percentage, and status. "
        "If unrecognized or score is below threshold, returns 'unknown' ('الصوت غير مسجل في السيستم')."
    ),
    status_code=status.HTTP_200_OK,
)
async def identify_speaker(
    request: Request,
    file: Optional[UploadFile] = File(None, description="WAV / Audio file to identify"),
    threshold: Optional[float] = Query(None, description="Cosine similarity threshold override (default: from settings)"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Identify speaker from multipart audio file or raw request body bytes."""
    speaker_service = get_speaker_service()

    audio_bytes: Optional[bytes] = None
    if file is not None:
        audio_bytes = await file.read()
    else:
        # Check raw body
        body = await request.body()
        if body and len(body) > 0:
            audio_bytes = body

    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio data provided. Send a WAV file via form-data ('file') or raw body bytes.",
        )

    res = await speaker_service.identify(audio_bytes, threshold=threshold)
    return res


@router.post(
    "/diarize",
    summary="Multi-speaker diarization, count, language detection & multilingual tracking",
    description=(
        "Analyzes an audio file to determine: "
        "1. How many people spoke in total (speaker diarization & count). "
        "2. The spoken language of each speech turn (Arabic, English, French, etc.). "
        "3. Identifies if any speaker switched between multiple languages."
    ),
    status_code=status.HTTP_200_OK,
)
async def diarize_speakers(
    request: Request,
    file: Optional[UploadFile] = File(None, description="Audio file to analyze"),
    threshold: Optional[float] = Query(None, description="Cosine similarity threshold override (default: 0.86)"),
    transcripts_json: Optional[str] = Form(None, description="Optional JSON list of transcript segments with timestamps and text"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Diarize speakers and detect languages from audio file or raw bytes."""
    speaker_service = get_speaker_service()

    audio_bytes: Optional[bytes] = None
    if file is not None:
        audio_bytes = await file.read()
    else:
        body = await request.body()
        if body and len(body) > 0:
            audio_bytes = body

    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No audio data provided. Send an audio file via form-data ('file') or raw body bytes.",
        )

    transcripts_list = None
    if transcripts_json:
        try:
            import json
            transcripts_list = json.loads(transcripts_json)
        except Exception:
            pass

    res = await speaker_service.diarize_and_identify(
        audio=audio_bytes,
        threshold=threshold,
        transcripts=transcripts_list,
    )
    if not res.get("success", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.get("error", "فشل تحليل المتحدثين في الصوت."),
        )
    return res



@router.post(
    "/compare",
    summary="Compare two voice clips & identify speaker and spoken language",
    description=(
        "Compares two uploaded voice clips directly: "
        "1. Checks if they belong to the same person or different people. "
        "2. Identifies Voice 1 from enrolled database voiceprints (with Face ID, Personality ID, Memory ID). "
        "3. Identifies Voice 2 from enrolled database voiceprints (with Face ID, Personality ID, Memory ID). "
        "4. Detects whether each person spoke Arabic (العربية) or English (الإنجليزية)."
    ),
    status_code=status.HTTP_200_OK,
)
async def compare_speakers(
    file1: UploadFile = File(..., description="First audio file (Voice 1)"),
    file2: UploadFile = File(..., description="Second audio file (Voice 2)"),
    threshold: Optional[float] = Query(None, description="Cosine similarity threshold override (default: 0.82)"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Compare two voice recordings and detect spoken language."""
    audio_bytes1 = await file1.read()
    audio_bytes2 = await file2.read()

    if not audio_bytes1 or not audio_bytes2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="يجب إرسال كلا الملفين الصوتيين (file1 و file2) لإجراء المقارنة.",
        )

    speaker_service = get_speaker_service()
    res = await speaker_service.compare_two_speakers(
        audio1=audio_bytes1,
        audio2=audio_bytes2,
        threshold=threshold,
    )
    if not res.get("success", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res.get("error", "فشلت عملية مقارنة الصوتين."),
        )
    return res


@router.post(
    "/enroll",
    summary="Enroll a speaker voiceprint",
    description="Registers or updates a speaker's voiceprint from one or more audio sample clips.",
    status_code=status.HTTP_200_OK,
)
async def enroll_speaker(
    speaker_name: str = Form(..., description="Name or identifier of the speaker"),
    file: Optional[UploadFile] = File(None, description="Primary audio recording sample (any audio format: WAV/MP3/M4A/OGG/WebM/AAC/AMR)"),
    files: Optional[List[UploadFile]] = File(None, description="Multiple audio sample clips for averaging"),
    face_id: Optional[int] = Form(None, description="Optional linked Neural Face ID"),
    personality_id: Optional[int] = Form(None, description="Optional linked Personality ID"),
    memory_id: Optional[int] = Form(None, description="Optional linked Memory ID"),
    max_level: int = Form(2, description="Security level (default: 2)"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Enroll a speaker into the database."""
    clean_name = speaker_name.strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Speaker name cannot be empty.",
        )

    audio_samples: List[bytes] = []

    if file is not None:
        data = await file.read()
        if data:
            audio_samples.append(data)

    if files:
        for f in files:
            data = await f.read()
            if data:
                audio_samples.append(data)

    if not audio_samples:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one audio recording sample is required for voiceprint enrollment.",
        )

    speaker_service = get_speaker_service()
    try:
        voiceprint = await speaker_service.enroll(
            db=db,
            speaker_name=clean_name,
            samples=audio_samples,
            max_level=max_level,
            face_id=face_id,
            personality_id=personality_id,
            memory_id=memory_id,
        )
        await db.commit()
    except VoiceprintError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"فشل تسجيل البصمة الصوتية: {e}",
        )
    except Exception as e:
        await db.rollback()
        logger.exception("Unexpected error enrolling speaker '%s': %s", clean_name, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"حدث خطأ داخلي أثناء تسجيل بصمة الصوت: {e}",
        )

    return {
        "success": True,
        "speaker_name": voiceprint.speaker_name,
        "user_id": voiceprint.user_id,
        "face_id": getattr(voiceprint, "face_id", None),
        "personality_id": getattr(voiceprint, "personality_id", None),
        "memory_id": getattr(voiceprint, "memory_id", None),
        "samples_count": voiceprint.samples_count,
        "embedding_dim": voiceprint.embedding_dim,
        "model_id": voiceprint.model_id,
        "message": f"تم تسجيل بصمة الصوت للمتحدث '{clean_name}' بنجاح",
    }


@router.get(
    "",
    summary="List enrolled speakers",
    description="Returns all enrolled speaker voiceprints stored in the database.",
    status_code=status.HTTP_200_OK,
)
async def list_speakers(
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all voiceprints."""
    rows = (await db.execute(select(Voiceprint).order_by(Voiceprint.created_at.desc()))).scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "speaker_name": r.speaker_name,
            "samples_count": r.samples_count,
            "embedding_dim": r.embedding_dim,
            "model_id": r.model_id,
            "max_level": r.max_level,
            "face_id": getattr(r, "face_id", None),
            "personality_id": getattr(r, "personality_id", None),
            "memory_id": getattr(r, "memory_id", None),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.delete(
    "/{speaker_name}",
    summary="Delete a speaker voiceprint",
    description="Deletes all voiceprints associated with the specified speaker name.",
    status_code=status.HTTP_200_OK,
)
async def delete_speaker(
    speaker_name: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Delete speaker voiceprint by name."""
    clean_name = speaker_name.strip()
    speaker_service = get_speaker_service()
    deleted = await speaker_service.delete_by_name(db, clean_name)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"المتحدث '{clean_name}' غير موجود في النظام.",
        )
    await db.commit()
    return {
        "success": True,
        "speaker_name": clean_name,
        "message": f"تم حذف بصمة الصوت للمتحدث '{clean_name}' بنجاح.",
    }


@router.get(
    "/status",
    summary="Voiceprint engine status",
    description="Returns status of the speaker recognition engine, active backend, and count of enrolled speakers.",
    status_code=status.HTTP_200_OK,
)
async def speaker_engine_status(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """System voiceprint status."""
    speaker_service = get_speaker_service()
    rows = (await db.execute(select(Voiceprint))).scalars().all()
    return {
        "backend_model": speaker_service._backend.model_id,
        "backend_available": speaker_service._backend.available(),
        "enrolled_count": len(rows),
        "threshold_l1": speaker_service.default_threshold,
        "threshold_l2": settings.SPEAKER_THRESHOLD_L2,
        "sample_rate": settings.SPEAKER_SAMPLE_RATE,
        "verification_enabled": settings.SPEAKER_VERIFICATION_ENABLED,
    }

