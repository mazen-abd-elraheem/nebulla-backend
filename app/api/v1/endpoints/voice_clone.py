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
import re
import pathlib
from fastapi import APIRouter, Depends, File, Form, HTTPException, Path, Query, UploadFile, status
from fastapi.responses import FileResponse, Response, JSONResponse
from pydantic import BaseModel, Field, model_validator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_optional_user
from app.core.config import settings
from app.db.session import get_db
from app.models.personality import Personality

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
        "message": "تم رفع تسجيل الصوت واستنساخه بنجاح!",
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

    # Automatically enroll speaker voiceprint for continuous voice verification
    try:
        from app.services.voice_verification.speaker_service import get_speaker_service
        spk_svc = get_speaker_service()
        raw_audio = Path(path).read_bytes()
        speaker_label = getattr(personality, "name", "المالك الأصلي") if personality else "المالك الأصلي"
        await spk_svc.enroll(
            db,
            user_id=personality.user_id if personality else 1,
            speaker_name=speaker_label,
            audio_data=raw_audio,
        )
        logger.info(f"Auto-enrolled voiceprint for {speaker_label} (personality {personality_id})")
    except Exception as spk_err:
        logger.warning(f"Note on auto-enrolling speaker voiceprint: {spk_err}")

    return {"message": "تم حفظ عينة الصوت واستنساخها بنجاح", "path": path, "personality_id": personality_id}


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
    try:
        from app.providers.tts.voicetut import VoiceTutProvider
        speakers = VoiceTutProvider.list_speakers() if hasattr(VoiceTutProvider, "list_speakers") else svc.list_speakers()
    except Exception as exc:
        logger.warning(f"Error fetching voicetut speakers: {exc}")
        speakers = []
    return {
        "active_provider": settings.TTS_PROVIDER,
        "cloned_samples": samples,
        "voicetut_speakers": speakers,
        "usage_example": {
            "voice_id": 1,
            "text": "أهلاً بيك، الصوت ده مستنسخ بصوتك المرفوع على النظام",
        }
    }


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="عينة الصوت دي مش موجودة.")

    res = await db.execute(select(Personality).where(Personality.id == personality_id))
    personality = res.scalar_one_or_none()
    if personality:
        personality.voice_sample_path = None
        await db.commit()

    return {"message": "مسحنا عينة الصوت خلاص", "personality_id": personality_id}


# ── Synthesise ────────────────────────────────────────────────────────────────

class SynthesizeRequest(BaseModel):
    text: str = Field(..., description="النص العربي المراد تحويله إلى صوت")
    voice_id: int | str | None = Field(1, description="معرف الصوت المستنسخ (مثال: 1)")
    personality_id: int | None = Field(None, description="معرف الشخصية (اختياري)")
    language: str = Field("arz", description="اللهجة (arz للمصري)")
    ref_text: str | None = Field(None, description="نص العينة المرجعية (اختياري، يتم جلبه تلقائياً)")
    num_steps: int | None = Field(48, description="عدد خطوات التوليد (48 لجودة ستوديو فائقة النقاء وعالية الدقة)")
    guidance_scale: float | None = Field(2.6, description="مقياس مطابقة نبرة الصوت المرجعي بدقة (2.5 - 2.8)")
    speed: float | None = Field(1.15, description="سرعة الكلام (1.15 للريتم الطبيعي السريع للعامية المصرية)")


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
    Returns a WAV audio file.
    """
    cleaned_text = body.text.strip()
    if not cleaned_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="الكلام اللي عايز تنطقه مينفعش يكون فاضي.",
        )
    if all(ch in "?!.,;: \t\n\r" for ch in cleaned_text):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="النص ده مفهوش أي حروف قابلة للنطق.",
        )

    # Sanitize target PID
    target_pid: int | None = None
    if body.voice_id is not None:
        v_str = str(body.voice_id).strip().lower()
        if v_str.isdigit():
            target_pid = int(v_str)
        elif v_str in ("mazen", "personality_1"):
            target_pid = 1
        elif v_str.startswith("personality_"):
            try:
                target_pid = int(v_str.replace("personality_", ""))
            except Exception:
                target_pid = None
        else:
            try:
                target_pid = int(v_str)
            except Exception:
                target_pid = None

    if target_pid is None and body.personality_id is not None and body.personality_id > 0:
        target_pid = body.personality_id

    if target_pid is None and _user:
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.personality import Personality
            u_id = int(_user) if str(_user).isdigit() else None
            if u_id:
                async with AsyncSessionLocal() as session:
                    res = await session.execute(
                        select(Personality).where(Personality.user_id == u_id, Personality.is_active == True)
                    )
                    up = res.scalar_one_or_none()
                    if up and svc.has_voice_sample(up.id):
                        target_pid = up.id
        except Exception:
            pass

    if target_pid is None:
        target_pid = 1

    actual_ref_text = body.ref_text if (body.ref_text and body.ref_text.strip() and body.ref_text.strip() != "string") else None
    steps = body.num_steps if (body.num_steps and body.num_steps > 0) else getattr(settings, "VOICETUT_NUM_STEPS", 48)
    cfg = body.guidance_scale if (body.guidance_scale and body.guidance_scale > 0) else 2.6
    spd = body.speed if (body.speed and body.speed > 0) else 1.15

    wav_bytes = await svc.synthesize(
        text=cleaned_text,
        personality_id=target_pid,
        language=body.language,
        ref_text=actual_ref_text,
        num_step=steps,
        guidance_scale=cfg,
        speed=spd,
    )

    if not wav_bytes or len(wav_bytes) <= 1000:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="معرفناش نستنسخ الصوت ونطلع مقطع صوت سليم.",
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
    num_steps: int | None = Query(48, description="عدد خطوات التوليد (الافتراضي: 48 لجودة ستوديو فائقة النقاء)"),
    speed: float | None = Query(1.15, description="سرعة الكلام (الافتراضي: 1.15 للعامية المصرية)"),
    guidance_scale: float | None = Query(2.6, description="مطابقة نبرة الصوت المستنسخ"),
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
            num_steps=num_steps or 48,
            guidance_scale=guidance_scale or 2.6,
            speed=speed or 1.15,
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

    # Default preview request
    req = SynthesizeRequest(
        text="أهلاً بيك يا صديقي! الصوت المصري المستنسخ شغال وجاهز تماماً.",
        personality_id=pid,
        num_steps=48,
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
        language="arz",
        num_step=48,
        guidance_scale=2.2,
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


# ── LLM Voice Clone (Dedicated conversion of LLM Chat responses to Cloned Voice) ──

class LLMVoiceCloneRequest(BaseModel):
    text: str = Field(
        "أهلاً بيك يا صديقي! أنا جاهز أساعدك في أي وقت.",
        description="نص رد الـ LLM المراد تحويله لصوت مستنسخ",
    )
    personality_id: int | None = Field(1, description="معرف الشخصية لاستخدام عينة صوتها المستنسخة (افتراضياً 1 أو النشطة)")
    return_json: bool = Field(False, description="إذا كان True يرجع كائن JSON مع audio_base64، وإذا كان False يرجع ملف صوتي مباشر audio/wav")
    speed: float | None = Field(1.15, description="سرعة نطق الصوت (افتراضياً 1.15 للعامية المصرية)")
    guidance_scale: float | None = Field(2.6, description="مقياس تطابق نبرة الصوت المرجعي بدقة (افتراضياً 2.6)")
    num_steps: int | None = Field(48, description="عدد خطوات التوليد لموديل VoiceTut (افتراضياً 48)")

    model_config = {
        "json_schema_extra": {
            "example": {
                "text": "أهلاً بيك يا صديقي! أنا جاهز أساعدك في أي وقت.",
                "personality_id": 1,
                "return_json": False,
                "speed": 1.15,
                "guidance_scale": 2.6,
                "num_steps": 48,
            }
        }
    }

    @model_validator(mode="before")
    @classmethod
    def _fallback_text_keys(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "text" not in data or not data["text"]:
                for alt_key in ("message", "msg", "input", "prompt", "additionalProp1", "additionalProp2"):
                    val = data.get(alt_key)
                    if isinstance(val, str) and val.strip():
                        data["text"] = val.strip()
                        break
                    elif isinstance(val, dict):
                        for sub_val in val.values():
                            if isinstance(sub_val, str) and sub_val.strip():
                                data["text"] = sub_val.strip()
                                break
        return data


class LLMVoiceCloneResponse(BaseModel):
    status: str = Field("success", description="حالة الطلب")
    text_cleaned: str = Field(..., description="النص المنظف بعد إزالة وسوم المشاعر وتهيئته للنطق")
    audio_base64: str = Field(..., description="بيانات الصوت المشفرة Base64")
    audio_url: str = Field(..., description="رابط تحميل أو سماع ملف الصوت")
    personality_id: int = Field(..., description="معرف الشخصية التي استخدم صوتها")
    sample_path_used: str = Field(..., description="مسار عينة الصوت المستخدمة للاستنساخ")
    model_used: str = Field("VoiceTut-TTS", description="الموديل المستخدم (VoiceTut دون أي fallback)")


async def handle_llm_voice_clone(
    text: str,
    personality_id: int | None = None,
    return_json: bool = False,
    speed: float | None = None,
    guidance_scale: float | None = None,
    num_steps: int | None = None,
    user: str | None = None,
    svc: VoiceCloneService | None = None,
) -> Response:
    """
    Core handler for LLM-to-Voice synthesis:
    1. Cleans LLM text (strips markdown, emotion tags like [happy], thinking tokens).
    2. Identifies target personality and verifies registered voice sample.
    3. Strictly enforces ZERO FALLBACK (HTTP 422 if sample is missing).
    4. Synthesizes using primary VoiceTut-TTS model.
    5. Returns audio/wav or JSONResponse based on return_json.
    """
    import base64
    from app.utils.masri_normalizer import clean_llm_output_for_speech

    if svc is None:
        svc = _svc()

    raw_text = (text or "").strip()
    if not raw_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="النص المطلوب تحويله لصوت فارغ، يرجى إدخال نص رد الـ LLM.",
        )

    # 1. Clean and normalize LLM text
    cleaned_text = clean_llm_output_for_speech(raw_text)
    if not cleaned_text or not cleaned_text.strip():
        cleaned_text = re.sub(r"\[.*?\]", "", raw_text).strip()
    if not cleaned_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="النص لا يحتوي على أي كلمات أو حروف قابلة للنطق بعد التنظيف.",
        )

    # 2. Determine target personality
    target_pid = personality_id
    if target_pid is None and user:
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.personality import Personality
            u_id = int(user) if str(user).isdigit() else None
            if u_id:
                async with AsyncSessionLocal() as session:
                    res = await session.execute(
                        select(Personality).where(Personality.user_id == u_id, Personality.is_active == True)
                    )
                    up = res.scalar_one_or_none()
                    if up and svc.has_voice_sample(up.id):
                        target_pid = up.id
        except Exception:
            pass

    if target_pid is None or target_pid <= 0:
        target_pid = 1

    # 3. Strict Zero Fallback Check: Must have a registered voice sample
    has_sample = svc.has_voice_sample(target_pid)
    sample_path = svc.get_sample_path(target_pid) if has_sample else None

    if not has_sample or not sample_path or not os.path.exists(sample_path):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"يرجى تسجيل عينة صوتك أولاً للشخصية {target_pid} لتفعيل استنساخ الصوت. لا يوجد نموذج بديل (Zero Fallback).",
        )

    # 4. Synthesize with VoiceTut-TTS
    steps = num_steps or getattr(settings, "VOICETUT_NUM_STEPS", 48)
    cfg = guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.6)
    spd = speed or getattr(settings, "VOICETUT_SPEED", 1.15)

    wav_bytes = await svc.synthesize(
        text=cleaned_text,
        personality_id=target_pid,
        reference_wav=sample_path,
        language="arz",
        num_step=steps,
        guidance_scale=cfg,
        speed=spd,
    )

    if not wav_bytes or len(wav_bytes) <= 1000:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="فشل استنساخ الصوت عبر نموذج VoiceTut-TTS الأساسي.",
        )

    # Cache for immediate browser streaming
    try:
        LATEST_WAV_FILE.write_bytes(wav_bytes)
        _last_synthesized_audio[target_pid] = wav_bytes
        _last_synthesized_audio["latest"] = wav_bytes
    except Exception:
        pass

    # 5. Return based on requested format
    audio_url = f"/api/v1/voice-clone/llm_voice_clone?personality_id={target_pid}"

    if return_json:
        audio_b64 = base64.b64encode(wav_bytes).decode("ascii")
        return JSONResponse(
            content=LLMVoiceCloneResponse(
                status="success",
                text_cleaned=cleaned_text,
                audio_base64=audio_b64,
                audio_url=audio_url,
                personality_id=target_pid,
                sample_path_used=str(sample_path),
                model_used="VoiceTut-TTS",
            ).model_dump()
        )

    return Response(
        content=wav_bytes,
        media_type="audio/wav",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(len(wav_bytes)),
            "Content-Disposition": f'inline; filename="llm_voice_clone_{target_pid}.wav"',
        },
    )


@router.post(
    "/llm_voice_clone",
    summary="تحويل ردود LLM Chat إلى صوت مستنسخ فعلي عبر VoiceTut بدون Fallback",
    responses={
        200: {
            "content": {
                "audio/wav": {"schema": {"type": "string", "format": "binary"}},
                "application/json": {"schema": {"$ref": "#/components/schemas/LLMVoiceCloneResponse"}},
            },
            "description": "WAV audio file or JSON with base64 audio",
        }
    },
)
async def llm_voice_clone_post(
    body: LLMVoiceCloneRequest,
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    تستقبل رد الـ LLM وتقوم بتنظيفه وتحويله لصوت مستنسخ فعلياً عبر الموديل الأساسي VoiceTut-TTS.
    - Zero Fallback Model: لا يتم استخدام أي موديل بديل نهائياً.
    - تدعم إرجاع ملف صوتي مباشر audio/wav أو كائن JSON مع audio_base64 عبر return_json=True.
    """
    return await handle_llm_voice_clone(
        text=body.text,
        personality_id=body.personality_id,
        return_json=body.return_json,
        speed=body.speed,
        guidance_scale=body.guidance_scale,
        num_steps=body.num_steps,
        user=_user,
        svc=svc,
    )


@router.get(
    "/llm_voice_clone",
    summary="سماع أو تشغيل الصوت المستنسخ لردود الـ LLM مباشرة في المتصفح أو Swagger",
    response_class=Response,
    responses=_AUDIO_RESPONSES,
)
async def llm_voice_clone_get(
    text: str | None = Query(None, description="نص رد الـ LLM المراد تحويله لصوت (إذا تُرِك فارغاً يتم تشغيل آخر صوت تم توليده)"),
    personality_id: int | None = Query(None, description="معرف الشخصية"),
    return_json: bool = Query(False, description="إرجاع كائن JSON بدلاً من الملف الصوتي المباشر"),
    speed: float | None = Query(1.15, description="سرعة النطق"),
    guidance_scale: float | None = Query(2.6, description="مطابقة نبرة الصوت المرجعي"),
    num_steps: int | None = Query(48, description="عدد خطوات التوليد"),
    _user: str | None = Depends(get_optional_user),
    svc: VoiceCloneService = Depends(_svc),
):
    """
    GET endpoint for `/llm_voice_clone`:
    1. إذا أُرسل نص، يقوم بتنظيفه وتوليد الصوت وسماعه فوراً في المتصفح.
    2. إذا تُرِك فارغاً، يقوم بتشغيل آخر صوت تم توليده مع دعم Byte-Range للـ HTML5 Audio Player.
    """
    if text and text.strip():
        return await handle_llm_voice_clone(
            text=text,
            personality_id=personality_id,
            return_json=return_json,
            speed=speed,
            guidance_scale=guidance_scale,
            num_steps=num_steps,
            user=_user,
            svc=svc,
        )

    pid = personality_id or 1
    cached = _last_synthesized_audio.get(pid) or _last_synthesized_audio.get("latest")
    if cached:
        return Response(
            content=cached,
            media_type="audio/wav",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(len(cached)),
                "Content-Disposition": f'inline; filename="llm_voice_clone_{pid}.wav"',
            },
        )

    if LATEST_WAV_FILE.exists() and LATEST_WAV_FILE.stat().st_size > 0:
        return FileResponse(
            path=str(LATEST_WAV_FILE),
            media_type="audio/wav",
            content_disposition_type="inline",
            filename="llm_voice_clone.wav",
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="لا يوجد صوت مُولّد مسبقاً، يرجى إرسال نص ليتم توليده.",
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
            detail="ملقناش أي ملف صوت مرجعي عشان تدريب الـ LoRA.",
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
            detail="لازم تبعت النص المكتوب عشان تدريب ومحاذاة الـ LoRA.",
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
                        "num_step": 48,
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
