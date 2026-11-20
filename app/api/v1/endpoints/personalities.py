"""
Personalities CRUD endpoints — user-scoped with global system defaults.
"""

import os
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user_model, get_optional_user_model
from app.db.session import get_db
from app.models.personality import Personality
from app.models.user import User
from app.websocket.manager import manager

router = APIRouter()


class PersonalityCreate(BaseModel):
    id: Optional[int] = Field(None, description="Optional explicit personality ID (e.g. 0, 1, 2)")
    name: str
    description: str | None = None
    system_prompt: str = ""
    dialect: str = "cairo"
    language_mix: str = "ar_en"
    voice_sample_path: str | None = None
    image_path: str | None = None
    tone: str | None = "ودود وعفوي ومباشر"


class PersonalityUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    dialect: str | None = None
    language_mix: str | None = None
    voice_sample_path: str | None = None
    image_path: str | None = None
    tone: str | None = None
    is_active: bool | None = None


class PersonalitySpeakRequest(BaseModel):
    text: str = Field(..., description="Text for the personality to speak")
    mood: Optional[str] = Field("happy", description="Eyes mood (happy, alert, thinking, etc.)")
    broadcast_to_phone: bool = Field(True, description="Whether to send audio to connected phone")


@router.get("", include_in_schema=False)
@router.get("/", summary="List all accessible personalities (user-owned + shared defaults)")
async def list_personalities(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user_model),
):
    """
    Returns global system default personalities (user_id is None)
    plus custom personalities created by the authenticated user.
    """
    if current_user:
        stmt = (
            select(Personality)
            .where(or_(Personality.user_id == None, Personality.user_id == current_user.id))  # noqa: E711
            .order_by(Personality.user_id.is_(None), Personality.id)
        )
    else:
        stmt = (
            select(Personality)
            .where(or_(Personality.user_id == None, Personality.user_id == 1))  # noqa: E711
            .order_by(Personality.user_id.is_(None), Personality.id)
        )

    r = await db.execute(stmt)
    personalities = list(r.scalars().all())
    for p in personalities:
        if "مازن" in p.name:
            p.name = "التوأم الرقمي (Digital Twin)"
            p.description = "التوأم الرقمي والمساعد الذكي لنيبولا بصوت طبيعي"
    return {"personalities": [_p(p) for p in personalities]}


@router.post("", status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a user-owned personality")
async def create_personality(
    body: PersonalityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user_model),
):
    """
    Create a new robot personality profile tied to the authenticated user (or default user/system).
    """
    data = body.model_dump()
    data["user_id"] = current_user.id if current_user else None

    p = Personality(**data)
    db.add(p)
    try:
        await db.flush()
        await db.refresh(p)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"معرفناش نعمل الشخصية بسبب مشكلة في البيانات: {exc.orig}",
        )
    return _p(p)


@router.get("/{pid}", summary="Get personality by ID")
async def get_personality(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user_model),
):
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    # If personality is private to a user, enforce ownership
    if p.user_id is not None:
        if current_user and current_user.id != p.user_id and not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="معندكش صلاحية تفتح أو تشوف الشخصية دي.",
            )

    return _p(p)


@router.patch("/{pid}", summary="Update a personality")
async def update_personality(
    pid: int,
    body: PersonalityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user_model),
):
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    if p.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="الشخصية دي من شخصيات السيستم الأساسية ومينفعش تعدلها.",
        )

    if current_user and p.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="غير مصرح لك بتعديل هذه الشخصية.",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="تقدر تعدل الشخصيات بتاعتك أنت بس.",
        )

    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    try:
        await db.flush()
        await db.refresh(p)
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"معرفناش نعدل الشخصية بسبب مشكلة في البيانات: {exc.orig}",
        )
    return _p(p)


@router.delete("/{pid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personality(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_model),
):
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    if p.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="مينفعش تمسح شخصية أساسية من شخصيات السيستم.",
        )

    if p.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="تقدر تمسح الشخصيات اللي أنت عملتها بس.",
        )

    await db.delete(p)


@router.post("/{pid}/activate", summary="Set this personality as the active one")
async def activate_personality(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user_model),
):
    target = await db.get(Personality, pid)
    if not target:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    if target.user_id is not None and current_user and target.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="مينفعش تشغل شخصية خاصة بمستخدم تاني.",
        )

    # Deactivate all accessible personalities
    if current_user:
        stmt = select(Personality).where(
            or_(Personality.user_id == None, Personality.user_id == current_user.id)  # noqa: E711
        )
    else:
        stmt = select(Personality)

    all_p = (await db.execute(stmt)).scalars().all()
    for p in all_p:
        p.is_active = False

    target.is_active = True
    await db.flush()
    await db.commit()
    return {"active_personality_id": pid}


@router.get("/{pid}/tone", summary="Retrieve speaking tone and style of the personality")
async def get_personality_tone(
    pid: int,
    db: AsyncSession = Depends(get_db),
    _u: Optional[User] = Depends(get_optional_user_model),
):
    """
    Returns the tone, emotional style, dialect, and voice profile of the specified personality.
    """
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")
    return {
        "id": p.id,
        "name": p.name,
        "tone": getattr(p, "tone", None) or "ودود وعفوي ومباشر",
        "dialect": p.dialect or "cairo",
        "language_mix": p.language_mix or "ar_en",
        "speaking_style": f"لهجة {p.dialect} بنبرة {getattr(p, 'tone', 'طبيعية')} وسرعة رد خاطفة",
        "has_cloned_voice": bool(p.voice_sample_path),
        "voice_sample_path": p.voice_sample_path,
    }


@router.get("/{pid}/image", summary="Get personality photo / avatar")
@router.get("/{pid}/photo", summary="View personality photo directly in browser")
async def get_personality_image(
    pid: int,
    view: bool = Query(True, description="Whether to view the actual image inline in browser"),
    download: bool = Query(False, description="Whether to download as an attachment file"),
    db: AsyncSession = Depends(get_db),
    _u: Optional[User] = Depends(get_optional_user_model),
):
    """
    Returns personality photo information or streams the image file directly for display.
    """
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    img_path = getattr(p, "image_path", None)
    if (view or download) and img_path and os.path.exists(img_path):
        media_type = "image/png" if img_path.endswith(".png") else "image/jpeg"
        disp = "attachment" if download else "inline"
        return FileResponse(
            img_path,
            media_type=media_type,
            filename=os.path.basename(img_path),
            content_disposition_type=disp,
        )

    return {
        "id": p.id,
        "name": p.name,
        "image_path": img_path,
        "has_image": bool(img_path and os.path.exists(img_path)),
    }


@router.post("/{pid}/upload-image", summary="Upload real photo for this personality")
async def upload_personality_image(
    pid: int,
    file: UploadFile = File(..., description="Image file (PNG, JPG, JPEG, WEBP)"),
    db: AsyncSession = Depends(get_db),
    _u: Optional[User] = Depends(get_optional_user_model),
):
    """
    Upload real photo for the personality and update its image path.
    """
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    os.makedirs("data/images", exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".png"
    target_path = f"data/images/personality_{pid}{ext}"

    content = await file.read()
    with open(target_path, "wb") as f:
        f.write(content)

    p.image_path = target_path
    await db.commit()
    await db.refresh(p)

    return {
        "status": "success",
        "personality_id": p.id,
        "personality_name": p.name,
        "image_path": target_path,
        "message": f"تم رفع وتحديث صورة الشخصية ({p.name}) بصورتك الحقيقية بنجاح.",
    }


@router.post("/{pid}/display-image", summary="Display personality photo on screen / phone")
async def display_personality_image(
    pid: int,
    db: AsyncSession = Depends(get_db),
    _u: Optional[User] = Depends(get_optional_user_model),
):
    """
    Broadcasts display photo event to the phone app and desktop interface ([screen:photo]).
    """
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    img_path = getattr(p, "image_path", None)
    await manager.send_to_phone({
        "t": "screen",
        "mode": "photo",
        "personality_id": p.id,
        "personality_name": p.name,
        "image_path": img_path,
    })
    await manager.broadcast_to_desks({
        "t": "screen",
        "mode": "photo",
        "personality_id": p.id,
        "personality_name": p.name,
        "image_path": img_path,
    })
    return {
        "status": "success",
        "personality_id": p.id,
        "personality_name": p.name,
        "image_path": img_path,
        "message": f"تم إرسال أمر عرض صورة الشخصية ({p.name}) على شاشات الروبوت بنجاح.",
    }


@router.get("/{pid}/voice", summary="Get personality cloned voice reference")
async def get_personality_voice(
    pid: int,
    download: bool = Query(False, description="Whether to stream the actual reference audio file"),
    db: AsyncSession = Depends(get_db),
    _u: Optional[User] = Depends(get_optional_user_model),
):
    """
    Returns personality reference voice sample info or streams the WAV audio file.
    """
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    v_path = p.voice_sample_path
    if download and v_path and os.path.exists(v_path):
        return FileResponse(v_path, media_type="audio/wav", filename=os.path.basename(v_path))

    return {
        "id": p.id,
        "name": p.name,
        "voice_sample_path": v_path,
        "has_voice_sample": bool(v_path and os.path.exists(v_path)),
    }


@router.post("/{pid}/upload-voice", summary="Upload / record voice sample for this personality")
async def upload_personality_voice(
    pid: int,
    file: UploadFile = File(..., description="Audio file (WAV, MP3, M4A, OGG, Opus) containing the person's voice"),
    transcript: Optional[str] = Form(None, description="Optional text transcript of the spoken words in the audio"),
    db: AsyncSession = Depends(get_db),
    _u: Optional[User] = Depends(get_optional_user_model),
):
    """
    Upload a dedicated voice recording for this personality to clone and use exclusively.
    """
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    from app.services.voice_clone.voice_clone_service import VoiceCloneService
    svc = VoiceCloneService.get_instance()

    saved_path = await svc.upload_sample(personality_id=pid, file=file, transcript=transcript)
    p.voice_sample_path = saved_path
    await db.commit()
    await db.refresh(p)

    return {
        "status": "success",
        "personality_id": p.id,
        "personality_name": p.name,
        "voice_sample_path": saved_path,
        "message": f"تم رفع وتثبيت بصمة الصوت الخاصة بالشخصية ({p.name}) بنجاح، وأصبح صوتها مخصصاً لها فقط.",
    }


@router.delete("/{pid}/voice", summary="Remove voice sample of this personality")
async def delete_personality_voice(
    pid: int,
    db: AsyncSession = Depends(get_db),
    _u: Optional[User] = Depends(get_optional_user_model),
):
    """
    Deletes the dedicated voice sample for this personality.
    """
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    v_path = getattr(p, "voice_sample_path", None)
    if v_path and os.path.exists(v_path):
        try:
            os.remove(v_path)
        except OSError:
            pass

    p.voice_sample_path = None
    await db.commit()
    return {
        "status": "success",
        "personality_id": p.id,
        "message": f"تم مسح بصمة الصوت للشخصية ({p.name}) بنجاح.",
    }


@router.post(
    "/{pid}/speak",
    summary="Play voice: synthesize text using personality voice & tone",
    responses={
        200: {
            "content": {
                "audio/wav": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
            "description": "Standard 16-bit PCM WAV audio playable directly in browser",
        },
        404: {
            "description": "الشخصية غير موجودة أو ملهاش بصمة صوت مخصصة",
        },
    },
)
async def personality_play_voice(
    pid: int,
    body: PersonalitySpeakRequest,
    db: AsyncSession = Depends(get_db),
    _u: Optional[User] = Depends(get_optional_user_model),
):
    """
    Synthesize speech using the personality's cloned voice and tone,
    optionally broadcasting to phone speaker and desktop.
    Strictly uses ONLY this personality's dedicated voice (no fallback to other people's voices).
    """
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="الشخصية دي مش موجودة عندنا.")

    v_path = getattr(p, "voice_sample_path", None)
    if not v_path or v_path in ("string", "none", "null") or not os.path.exists(v_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"الشخصية ({p.name}) ملهاش بصمة صوت مخصصة حتى الآن. يرجى رفع أو تسجيل عينة صوت للشخصية أولاً لتفعيل الرد الصوتي الخاص بيها.",
        )

    from app.services.voice_clone.voice_clone_service import VoiceCloneService
    from app.utils.masri_normalizer import clean_llm_output_for_speech
    from app.utils.audio_utils import ensure_wav_bytes, apply_personality_acoustic_profile

    cleaned_text = clean_llm_output_for_speech(body.text)
    svc = VoiceCloneService.get_instance()

    # Synthesize audio strictly with this personality's reference voice
    raw_audio = await svc.synthesize(cleaned_text, personality_id=pid, reference_wav=v_path)
    
    # Ensure 100% compliant 16-bit PCM WAV & apply distinct acoustic timbre
    audio_bytes = ensure_wav_bytes(raw_audio)
    audio_bytes = apply_personality_acoustic_profile(audio_bytes, personality_id=pid)

    if body.broadcast_to_phone:
        if body.mood:
            await manager.send_to_phone({"t": "eyes", "mood": body.mood})
        await manager.send_to_phone(audio_bytes)

    return Response(
        content=audio_bytes,
        media_type="audio/wav",
        headers={
            "Content-Disposition": f'inline; filename="personality_{pid}_speech.wav"',
            "Content-Length": str(len(audio_bytes)),
            "Accept-Ranges": "bytes",
            "X-Personality-ID": str(pid),
        },
    )


def _p(p: Personality) -> dict:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "name": p.name,
        "description": p.description,
        "system_prompt": p.system_prompt,
        "dialect": p.dialect,
        "language_mix": p.language_mix,
        "voice_sample_path": p.voice_sample_path,
        "image_path": getattr(p, "image_path", None),
        "tone": getattr(p, "tone", None) or "ودود وعفوي ومباشر",
        "is_active": p.is_active,
    }
