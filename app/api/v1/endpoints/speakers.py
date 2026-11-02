"""
Speaker Management & Voiceprint Verification / Identification API Endpoints.
(benefits_section.docx §14.3, "التحقق بالصوت").

Unified Speaker Entity:
  1. verification_id (Voiceprint biometric embedding ID)
  2. voice_id (TTS cloned voice sample / model identifier)
  3. personality_id (Digital-twin personality prompt ID)
  4. is_main (Whether this speaker is a primary/main owner of the robot)
"""

import io
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import get_db
from app.models.voiceprint import Voiceprint
from app.models.speaker import Speaker
from app.services.voice_verification.speaker_service import (
    AudioDecodeError,
    VoiceprintError,
    decode_audio,
    get_speaker_service,
)

logger = get_logger(__name__)

router = APIRouter()


# ── Pydantic Schemas ──────────────────────────────────────────────────────────

class SpeakerCreate(BaseModel):
    name: str
    verification_id: Optional[int] = None
    voice_id: Optional[str] = None
    personality_id: Optional[int] = None
    is_main: bool = False


class SpeakerUpdate(BaseModel):
    name: Optional[str] = None
    verification_id: Optional[int] = None
    voice_id: Optional[str] = None
    personality_id: Optional[int] = None
    is_main: Optional[bool] = None


class SpeakerContextRequest(BaseModel):
    speaker_name: Optional[str] = None
    user_id: Optional[int] = None


# ── CRUD Endpoints for Speaker Entity ─────────────────────────────────────────

@router.get(
    "",
    summary="List all speakers",
    description="Returns all registered speakers linking verification_id, voice_id, personality_id, and is_main status.",
    status_code=status.HTTP_200_OK,
)
async def list_speakers(
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List all speakers."""
    rows = (await db.execute(select(Speaker).order_by(Speaker.is_main.desc(), Speaker.id.asc()))).scalars().all()
    # If no Speaker records exist yet, fall back to any voiceprints or seed
    if not rows:
        v_rows = (await db.execute(select(Voiceprint).order_by(Voiceprint.id.asc()))).scalars().all()
        for vp in v_rows:
            is_m = "مازن" in vp.speaker_name.lower() or "mazen" in vp.speaker_name.lower()
            spk = Speaker(
                name=vp.speaker_name,
                verification_id=vp.id,
                voice_id=str(vp.personality_id or "1"),
                personality_id=vp.personality_id or 1,
                is_main=is_m,
            )
            db.add(spk)
        if v_rows:
            await db.commit()
            rows = (await db.execute(select(Speaker).order_by(Speaker.is_main.desc(), Speaker.id.asc()))).scalars().all()

    return [
        {
            "id": r.id,
            "name": r.name,
            "verification_id": r.verification_id,
            "voice_id": r.voice_id,
            "personality_id": r.personality_id,
            "is_main": r.is_main,
            "has_voiceprint": bool(r.verification_id),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in rows
    ]


@router.post(
    "",
    summary="Create or register a new speaker profile",
    status_code=status.HTTP_201_CREATED,
)
async def create_speaker(
    payload: SpeakerCreate,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Create a new speaker profile aggregating verification_id, voice_id, personality_id, and is_main."""
    clean_name = payload.name.strip()
    if not clean_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="اسم المتحدث مطلوب ولا يمكن أن يكون فارغاً.",
        )

    # Check if speaker with same name already exists
    existing = (await db.execute(select(Speaker).where(Speaker.name == clean_name))).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"المتحدث '{clean_name}' مسجل مسبقاً في النظام.",
        )

    speaker = Speaker(
        name=clean_name,
        verification_id=payload.verification_id,
        voice_id=payload.voice_id,
        personality_id=payload.personality_id,
        is_main=payload.is_main,
    )
    db.add(speaker)
    await db.commit()
    await db.refresh(speaker)

    get_speaker_service().invalidate()

    return {
        "success": True,
        "id": speaker.id,
        "name": speaker.name,
        "verification_id": speaker.verification_id,
        "voice_id": speaker.voice_id,
        "personality_id": speaker.personality_id,
        "is_main": speaker.is_main,
        "message": f"تم إنشاء ملف المتحدث '{speaker.name}' بنجاح.",
    }


@router.get(
    "/{speaker_id}",
    summary="Get speaker by ID",
    status_code=status.HTTP_200_OK,
)
async def get_speaker(
    speaker_id: int,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get single speaker details by ID."""
    speaker = await db.get(Speaker, speaker_id)
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"المتحدث برقم {speaker_id} غير موجود.",
        )
    return {
        "id": speaker.id,
        "name": speaker.name,
        "verification_id": speaker.verification_id,
        "voice_id": speaker.voice_id,
        "personality_id": speaker.personality_id,
        "is_main": speaker.is_main,
        "has_voiceprint": bool(speaker.verification_id),
        "created_at": speaker.created_at.isoformat() if speaker.created_at else None,
        "updated_at": speaker.updated_at.isoformat() if speaker.updated_at else None,
    }


@router.patch(
    "/{speaker_id}",
    summary="Update speaker attributes (e.g. toggle is_main, change voice_id, personality_id)",
    status_code=status.HTTP_200_OK,
)
async def update_speaker(
    speaker_id: int,
    payload: SpeakerUpdate,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Update speaker profile links, name, or main speaker status."""
    speaker = await db.get(Speaker, speaker_id)
    if not speaker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"المتحدث برقم {speaker_id} غير موجود.",
        )

    if payload.name is not None:
        speaker.name = payload.name.strip()
    if payload.verification_id is not None:
        speaker.verification_id = payload.verification_id
    if payload.voice_id is not None:
        speaker.voice_id = payload.voice_id
    if payload.personality_id is not None:
        speaker.personality_id = payload.personality_id
    if payload.is_main is not None:
        speaker.is_main = payload.is_main

    await db.commit()
    await db.refresh(speaker)

    get_speaker_service().invalidate()

    return {
        "success": True,
        "id": speaker.id,
        "name": speaker.name,
        "verification_id": speaker.verification_id,
        "voice_id": speaker.voice_id,
        "personality_id": speaker.personality_id,
        "is_main": speaker.is_main,
        "message": f"تم تحديث بيانات المتحدث '{speaker.name}' بنجاح.",
    }


@router.delete(
    "/{speaker_identifier}",
    summary="Delete a speaker by ID or name",
    description="Deletes speaker record and any associated voiceprint.",
    status_code=status.HTTP_200_OK,
)
async def delete_speaker(
    speaker_identifier: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Delete speaker by ID or name."""
    clean_ident = speaker_identifier.strip()
    speaker = None
    if clean_ident.isdigit():
        speaker = await db.get(Speaker, int(clean_ident))

    if not speaker:
        res = await db.execute(select(Speaker).where(Speaker.name == clean_ident))
        speaker = res.scalar_one_or_none()

    speaker_service = get_speaker_service()

    if speaker:
        spk_name = speaker.name
        if speaker.verification_id:
            vp = await db.get(Voiceprint, speaker.verification_id)
            if vp:
                await db.delete(vp)
        await db.delete(speaker)
        await speaker_service.delete_by_name(db, spk_name)
        await db.commit()
        return {
            "success": True,
            "speaker_name": spk_name,
            "message": f"تم حذف المتحدث '{spk_name}' بنجاح.",
        }

    # If only voiceprint exists
    deleted = await speaker_service.delete_by_name(db, clean_ident)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"المتحدث '{clean_ident}' غير موجود في النظام.",
        )
    await db.commit()
    return {
        "success": True,
        "speaker_name": clean_ident,
        "message": f"تم حذف المتحدث '{clean_ident}' بنجاح.",
    }


# ── Biometric Identification & Verification ───────────────────────────────────

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
    "/enroll",
    summary="Enroll a speaker voiceprint and bind Speaker profile",
    description="Registers or updates a speaker's voiceprint from audio clips and auto-binds Speaker profile.",
    status_code=status.HTTP_200_OK,
)
async def enroll_speaker(
    speaker_name: str = Form(..., description="Name or identifier of the speaker"),
    file: Optional[UploadFile] = File(None, description="Primary audio recording sample (any audio format: WAV/MP3/M4A/OGG/WebM/AAC/AMR)"),
    files: Optional[List[UploadFile]] = File(None, description="Multiple audio sample clips for averaging"),
    voice_id: Optional[str] = Form(None, description="Optional cloned voice sample or TTS model ID"),
    is_main: Optional[bool] = Form(None, description="Whether this speaker is a main robot owner"),
    face_id: Optional[int] = Form(None, description="Optional linked Neural Face ID"),
    personality_id: Optional[int] = Form(None, description="Optional linked Personality ID"),
    memory_id: Optional[int] = Form(None, description="Optional linked Memory ID"),
    max_level: Optional[int] = Form(2, description="Deprecated / Ignored"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Enroll a speaker into the database and bind Speaker entity."""
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
            face_id=face_id,
            personality_id=personality_id,
            memory_id=memory_id,
            voice_id=voice_id,
            is_main=is_main,
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

    # Fetch associated Speaker record
    spk_res = await db.execute(select(Speaker).where(Speaker.verification_id == voiceprint.id))
    spk = spk_res.scalar_one_or_none()

    return {
        "success": True,
        "speaker_id": spk.id if spk else None,
        "speaker_name": voiceprint.speaker_name,
        "verification_id": voiceprint.id,
        "voice_id": spk.voice_id if spk else str(voiceprint.personality_id or "1"),
        "personality_id": getattr(voiceprint, "personality_id", None),
        "is_main": spk.is_main if spk else ("مازن" in clean_name.lower() or "mazen" in clean_name.lower()),
        "user_id": voiceprint.user_id,
        "face_id": getattr(voiceprint, "face_id", None),
        "memory_id": getattr(voiceprint, "memory_id", None),
        "samples_count": voiceprint.samples_count,
        "embedding_dim": voiceprint.embedding_dim,
        "model_id": voiceprint.model_id,
        "message": f"تم تسجيل بصمة الصوت للمتحدث '{clean_name}' وربطه بنجاح",
    }


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
            detail="No audio data provided for diarization. Send a WAV file via form-data or raw bytes.",
        )

    transcripts = None
    if transcripts_json:
        import json
        try:
            transcripts = json.loads(transcripts_json)
        except Exception as e:
            logger.warning(f"Failed to parse transcripts_json: {e}")

    res = await speaker_service.diarize_and_identify(
        audio=audio_bytes,
        threshold=threshold,
        transcripts=transcripts,
    )
    return res


@router.post(
    "/compare",
    summary="Compare two voice samples and detect language (Voice 1 vs Voice 2)",
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
    speakers = (await db.execute(select(Speaker))).scalars().all()
    return {
        "backend_model": speaker_service._backend.model_id,
        "backend_available": speaker_service._backend.available(),
        "enrolled_count": len(rows),
        "speakers_count": len(speakers),
        "threshold_l1": speaker_service.default_threshold,
        "threshold_l2": settings.SPEAKER_THRESHOLD_L2,
        "sample_rate": settings.SPEAKER_SAMPLE_RATE,
        "verification_enabled": settings.SPEAKER_VERIFICATION_ENABLED,
    }


@router.post(
    "/context",
    summary="Get speaker metadata & voice verification formatted for LLM",
    description="Method 2 (API): Returns structured speaker identity, verification status, confidence, and LLM directive.",
    status_code=status.HTTP_200_OK,
)
async def get_speaker_llm_context(
    request: Request,
    file: Optional[UploadFile] = File(None, description="Optional audio file to verify live"),
    speaker_name: Optional[str] = Form(None, description="Optional claimed speaker name"),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    API endpoint providing LLM-ready speaker identity & voice verification context.
    Security level is removed; utilizes is_verified and is_main.
    """
    speaker_service = get_speaker_service()

    # 1. If audio file provided, perform live 1:N speaker identification
    if file is not None:
        audio_bytes = await file.read()
        if audio_bytes and len(audio_bytes) > 0:
            res = await speaker_service.identify(audio_bytes)
            is_verified = res.get("status") == "identified"
            spk = res.get("speaker_name") if is_verified else None
            conf = res.get("similarity", 0.0)
            is_main = bool(res.get("is_main", False))

            if is_verified and spk:
                main_desc = "متحدث رئيسي" if is_main else "متحدث موثق"
                directive = f"المتحدث الحالي تم التحقق من هويته عبر بصمة الصوت: '{spk}' ({main_desc}، نسبة تطابق {int(conf * 100)}%). تعامل معه بثقة وناده باسمه."
            else:
                directive = "الصوت غير مسجل أو غير مطابق للبصمات الصوتية المحفوظة. يُمنع تنفيذ أي أوامر شخصية أو حساسة بدون تأكيد مسبق."

            return {
                "speaker_name": spk,
                "is_verified": is_verified,
                "is_main": is_main,
                "confidence": round(conf, 4),
                "enrolled": is_verified,
                "status": "verified" if is_verified else "unknown",
                "llm_directive": directive,
            }

    # 2. If claimed speaker name provided, lookup enrollment status in DB
    name = speaker_name
    if not name:
        try:
            body = await request.json()
            name = body.get("speaker_name")
        except Exception:
            name = None

    if name:
        clean_name = name.strip()
        spk_row = (
            await db.execute(select(Speaker).where(Speaker.name.ilike(f"%{clean_name}%")))
        ).scalar_one_or_none()

        is_main = bool(spk_row.is_main) if spk_row else ("مازن" in clean_name.lower() or "mazen" in clean_name.lower())
        vp_row = (
            await db.execute(select(Voiceprint).where(Voiceprint.speaker_name == clean_name))
        ).scalar_one_or_none()

        if spk_row or vp_row:
            disp_name = spk_row.name if spk_row else vp_row.speaker_name
            main_desc = "متحدث رئيسي" if is_main else "متحدث موثق"
            return {
                "speaker_name": disp_name,
                "is_verified": True,
                "is_main": is_main,
                "confidence": 1.0,
                "enrolled": True,
                "status": "verified",
                "llm_directive": f"المتحدث مسجل ببصمة صوت معتمدة باسم '{disp_name}' ({main_desc}).",
            }
        else:
            return {
                "speaker_name": clean_name,
                "is_verified": False,
                "is_main": False,
                "confidence": 0.0,
                "enrolled": False,
                "status": "unverified",
                "llm_directive": f"الاسم '{clean_name}' غير مسجل في بصمات الصوت في النظام.",
            }

    return {
        "speaker_name": None,
        "is_verified": False,
        "is_main": False,
        "confidence": 0.0,
        "enrolled": False,
        "status": "unknown",
        "llm_directive": "صوت المتحدث غير معروف أو غير محدد.",
    }
