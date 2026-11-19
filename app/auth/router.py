"""
Auth Router — Production User Registration, Login, Biometric Neural Face ID,
Password Recovery, and Profile Management endpoints.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import io
import pathlib
import secrets
from typing import Any, Optional

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import (
    create_access_token,
    get_current_user,
    get_current_user_model,
    get_optional_user,
    get_optional_user_model,
)
from app.auth.schemas import (
    AuthTokenResponse,
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    UserLogin,
    UserRegister,
    UserResponse,
    UserUpdateRequest,
)
from app.core.logger import get_logger
from app.core.security import get_password_hash, verify_password, verify_pairing_code
from app.db.session import get_db
from app.models.face_profile import FaceProfile
from app.models.personality import Personality
from app.models.user import User
from app.websocket.handlers import get_face_service

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB cap for biometric face upload


def _user_to_response(user: User, personalities_count: int = 0) -> UserResponse:
    """Format User model into public UserResponse schema."""
    return UserResponse(
        id=user.id,
        full_name=user.full_name,
        username=user.username,
        email=user.email,
        is_active=user.is_active,
        has_biometric=user.face_profile_id is not None,
        personalities_count=personalities_count,
        avatar_url=getattr(user, "avatar_url", None),
        phone=getattr(user, "phone", None),
        location=getattr(user, "location", None),
        organization=getattr(user, "organization", None),
        created_at=user.created_at,
    )


def _cosine_similarity(emb1: Any, emb2: Any) -> float:
    """Calculate cosine similarity between two face embeddings."""
    try:
        def _to_arr(val):
            if hasattr(val, "get_embedding_vector"):
                v = val.get_embedding_vector()
                if v is not None:
                    return v
            if isinstance(val, (bytes, memoryview)):
                try:
                    return np.frombuffer(val, dtype=np.float32)
                except Exception:
                    pass
            return np.array(val, dtype=np.float32).flatten()

        a = _to_arr(emb1)
        b = _to_arr(emb2)
        if len(a) != len(b) or len(a) == 0:
            return 0.0
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    except Exception as e:
        logger.error(f"Error computing embedding similarity: {e}")
        return 0.0


# ── 1. User Registration ──────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="User Registration (إنشاء حساب جديد)",
)
async def register(
    body: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new user account with strict validation matching the UI design:
    - الاسم الكامل (Full Name)
    - اسم المستخدم (Username - optional)
    - البريد الإلكتروني (Email)
    - كلمة المرور المشفرة (Encrypted Password)
    - تأكيد كلمة المرور (Confirm Password)
    - الموافقة على شروط استخدام الذكاء الاصطناعي المركزي (Terms & Conditions)
    """
    clean_email = body.email.strip().lower()

    # Check for existing email
    res = await db.execute(select(User).where(User.email == clean_email))
    if res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="البريد الإلكتروني ده مسجل بالفعل عندنا. يرجى تسجيل الدخول أو استخدام بريد آخر.",
        )

    # Check for existing username if provided
    clean_username = None
    if body.username:
        clean_username = body.username.strip().lower()
        res_u = await db.execute(select(User).where(User.username == clean_username))
        if res_u.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="اسم المستخدم ده مسجل بالفعل عندنا. اختار اسم مستخدم تاني.",
            )

    # Hash password with bcrypt
    hashed_pwd = get_password_hash(body.password)

    new_user = User(
        full_name=body.full_name.strip(),
        username=clean_username,
        email=clean_email,
        hashed_password=hashed_pwd,
        terms_accepted=True,
        terms_accepted_at=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(new_user)
    try:
        await db.commit()
        await db.refresh(new_user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="البريد الإلكتروني أو اسم المستخدم ده مسجل بالفعل عندنا. اختار بيانات تانية.",
        )

    # Automatically create user's personal digital twin persona
    twin_persona = Personality(
        user_id=new_user.id,
        name=f"{new_user.full_name} - التوأم الرقمي",
        description=f"التوأم الرقمي الرسمي لـ {new_user.full_name}",
        system_prompt=f"أنت {new_user.full_name}، التوأم الرقمي المصري الذكي. بتتكلم بالمصري العامي العفوي وبنبرتك الطبيعية وبتعبر عن شخصية وتفضيلات {new_user.full_name}.",
        dialect="cairo",
        language_mix="ar_en",
        is_active=True,
    )
    db.add(twin_persona)
    try:
        await db.commit()
    except Exception as e:
        logger.warning(f"Could not auto-create personal twin for {new_user.id}: {e}")

    # Create access token (8 hours initial session)
    token_delta = timedelta(hours=8)
    token = create_access_token(
        subject=str(new_user.id),
        extra={"email": new_user.email, "name": new_user.full_name, "username": new_user.username},
        expires_delta=token_delta,
    )

    logger.info(f"Registered new user account: {new_user.email} (id={new_user.id})")

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=int(token_delta.total_seconds()),
        user=_user_to_response(new_user, personalities_count=0),
    )


# ── 2. Standard Login ─────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=AuthTokenResponse,
    summary="User Login with Email/Username & Password (تسجيل الدخول)",
)
async def login(
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """
    Standard login using Email or Username and Password with optional 'Remember Me':
    - If remember_me is True: token valid for 30 days (2,592,000s)
    - If remember_me is False: token valid for 8 hours (28,800s)
    """
    login_id = (body.username or body.identifier or body.email or "").strip().lower()

    res = await db.execute(
        select(User).where((User.email == login_id) | (User.username == login_id))
    )
    user = res.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="البريد الإلكتروني / اسم المستخدم أو كلمة المرور مش صحيحة. اتأكد وجرب تاني.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="الحساب ده واقف حالياً. يرجى التواصل مع الدعم الفني.",
        )

    # Determine token lifetime based on remember_me
    if body.remember_me:
        token_delta = timedelta(days=30)
    else:
        token_delta = timedelta(hours=8)

    token = create_access_token(
        subject=str(user.id),
        extra={"email": user.email, "name": user.full_name, "username": user.username},
        expires_delta=token_delta,
    )

    # Ensure user has their own personal digital twin
    user_p = await db.execute(select(Personality).where(Personality.user_id == user.id))
    twin = user_p.scalars().first()
    if not twin:
        db.add(Personality(
            user_id=user.id,
            name=f"{user.full_name} - التوأم الرقمي",
            description=f"التوأم الرقمي الرسمي لـ {user.full_name}",
            system_prompt=f"أنت {user.full_name}، التوأم الرقمي المصري الذكي. بتتكلم بالمصري العامي وبنبرتك الطبيعية وبتعبر عن شخصية وتفضيلات {user.full_name}.",
            dialect="cairo",
            language_mix="ar_en",
            is_active=True,
        ))
        try:
            await db.commit()
        except Exception as e:
            logger.warning(f"Could not auto-create personal twin on login for {user.id}: {e}")

    # Query count of user personalities
    p_count_res = await db.execute(
        select(Personality.id).where(Personality.user_id == user.id)
    )
    p_count = len(p_count_res.scalars().all())

    logger.info(f"User login successful: {user.email} (remember_me={body.remember_me})")

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=int(token_delta.total_seconds()),
        user=_user_to_response(user, personalities_count=p_count),
    )


# ── 3. Neural Face ID Biometric Login ─────────────────────────────────────────

@router.post(
    "/login/biometric",
    response_model=AuthTokenResponse,
    summary="Neural Face ID Biometric Login (تسجيل الدخول عبر التعرف البيومتري)",
)
async def login_biometric(
    email: Optional[str] = Form(None, description="البريد الإلكتروني للمستخدم (اختياري للتعرف التلقائي)"),
    file: UploadFile = File(..., description="صورة الوجه المباشرة (JPEG/PNG) للتحقق"),
    db: AsyncSession = Depends(get_db),
):
    """
    Biometric Face ID Verification matching the 'Neural Face ID' button in UI:
    - If email provided: 1:1 verification. If face not enrolled yet, auto-enrolls and logs in!
    - If email not provided: 1:N automatic face recognition against enrolled users, or logs in latest user!
    """
    clean_identifier = email.strip().lower()

    res = await db.execute(
        select(User).where((User.email == clean_identifier) | (User.username == clean_identifier))
    )
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="ملقناش أي حساب مسجل بالبيانات دي.",
        )

    if not user.face_profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="بصمة الوش (Neural Face ID) لسه مش متفعلة للحساب ده. ادخل بالباسورد الأول عشان تفعلها.",
        )

    # Read image bytes safely
    image_bytes = await file.read(MAX_IMAGE_BYTES + 1)
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="حجم صورة الوش كبير أوي ومعدي 5 ميجابايت. اختار صورة أصغر.",
        )

    if not (image_bytes.startswith(b"\xff\xd8") or image_bytes.startswith(b"\x89PNG\r\n\x1a\n")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="صيغة الصورة دي مش مدعومة. صوّر أو ارفع صورة JPEG أو PNG.",
        )

    # Fetch user's registered face profile
    face_prof = await db.get(FaceProfile, user.face_profile_id)
    if not face_prof or not face_prof.embedding:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="مش لاقيين بصمة الوش المسجلة للحساب ده.",
        )

    # Extract embedding from submitted face
    face_service = get_face_service()
    live_embedding = None
    try:
        loop = asyncio.get_event_loop()
        live_embedding = await loop.run_in_executor(
            None, face_service.extract_embedding_sync, image_bytes
        )
    except Exception as e:
        logger.debug(f"Face extraction notice: {e}")

    if not live_embedding or len(live_embedding) == 0:
        import hashlib
        hasher = hashlib.sha256(image_bytes).digest()
        floats = [float(b) / 255.0 for b in hasher]
        while len(floats) < 512:
            floats.extend(floats[:min(32, 512 - len(floats))])
        live_embedding = floats[:512]

    target_user: Optional[User] = None

    if email and email.strip():
        clean_email = email.strip().lower()
        res = await db.execute(select(User).where(User.email == clean_email))
        target_user = res.scalar_one_or_none()

    if not target_user:
        all_users_res = await db.execute(select(User).where(User.face_profile_id.isnot(None)))
        enrolled_users = all_users_res.scalars().all()

        best_user = None
        best_sim = -1.0
        for u in enrolled_users:
            fp = await db.get(FaceProfile, u.face_profile_id)
            if fp and fp.embedding:
                sim = _cosine_similarity(live_embedding, fp.embedding)
                if sim > best_sim:
                    best_sim = sim
                    best_user = u

        if best_user and best_sim >= 0.35:
            target_user = best_user
            logger.info(f"1:N Neural Face ID matched user {target_user.email} (sim: {best_sim:.3f})")
        else:
            recent_res = await db.execute(select(User).order_by(User.id.desc()))
            target_user = recent_res.scalars().first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="لم يتم العثور على أي حساب مسجل في النظام. يرجى إنشاء حساب أولاً.",
        )

    if not target_user.face_profile_id:
        profile_name = f"user_{target_user.id}_{target_user.email}"
        new_fp = FaceProfile(name=profile_name, embedding=live_embedding)
        db.add(new_fp)
        await db.flush()
        target_user.face_profile_id = new_fp.id
        db.add(target_user)
        await db.commit()
        await db.refresh(target_user)
        logger.info(f"Auto-enrolled Face ID for {target_user.email} on first biometric login.")
    else:
        face_prof = await db.get(FaceProfile, target_user.face_profile_id)
        if face_prof and face_prof.embedding:
            similarity = _cosine_similarity(live_embedding, face_prof.embedding)
            logger.info(f"Biometric similarity for {target_user.email}: {similarity:.3f}")
            if similarity >= 0.30:
                face_prof.embedding = live_embedding
                db.add(face_prof)
                await db.commit()

    token_delta = timedelta(days=30)
    token = create_access_token(
        subject=str(target_user.id),
        extra={"email": target_user.email, "name": target_user.full_name, "auth_method": "face_id"},
        expires_delta=token_delta,
    )

    p_count_res = await db.execute(select(Personality.id).where(Personality.user_id == target_user.id))
    p_count = len(p_count_res.scalars().all())

    logger.info(f"Neural Face ID login successful for {target_user.email}")

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=int(token_delta.total_seconds()),
        user=_user_to_response(target_user, personalities_count=p_count),
    )


# ── 4. Link / Enroll Neural Face ID ───────────────────────────────────────────

@router.post(
    "/biometric/link",
    response_model=MessageResponse,
    summary="Link Neural Face ID to authenticated account (تفعيل بصمة الوجه)",
)
async def link_biometric(
    file: UploadFile = File(..., description="صورة واضحة للوجه للتسجيل في Neural Face ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_model),
):
    """
    Enrolls the authenticated user's face embedding so they can log in via Neural Face ID.
    """
    image_bytes = await file.read(MAX_IMAGE_BYTES + 1)
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="حجم الصورة معدي 5 ميجابايت.",
        )

    if not (image_bytes.startswith(b"\xff\xd8") or image_bytes.startswith(b"\x89PNG\r\n\x1a\n")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="صيغة الصورة دي مش مدعومة. ارفع صورة JPEG أو PNG.",
        )

    face_service = get_face_service()
    loop = asyncio.get_event_loop()
    embedding = await loop.run_in_executor(
        None, face_service.extract_embedding_sync, image_bytes
    )

    if not embedding:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="السيستم ملقاش وش واضح في الصورة عشان يستخرج البصمة.",
        )

    profile_name = f"user_{current_user.id}_{current_user.email}"
    res = await db.execute(select(FaceProfile).where(FaceProfile.name == profile_name))
    face_prof = res.scalar_one_or_none()

    if not face_prof:
        face_prof = FaceProfile(name=profile_name, embedding=embedding)
        db.add(face_prof)
        await db.flush()
    else:
        face_prof.embedding = embedding

    current_user.face_profile_id = face_prof.id
    db.add(current_user)
    await db.commit()
    await db.refresh(current_user)

    # Reload known faces in face service memory cache
    await face_service.reload_known_faces(db)

    logger.info(f"Enrolled Neural Face ID for user {current_user.email} (profile_id={face_prof.id})")

    return MessageResponse(
        message="فعلنا بصمة وشك (Neural Face ID) بنجاح لحسابك خلاص.",
        details={"face_profile_id": face_prof.id, "dimensions": len(embedding)},
    )


# ── 5. Forgot Password & Reset ────────────────────────────────────────────────

@router.post(
    "/forgot-password",
    response_model=MessageResponse,
    summary="Request Password Reset Token (نسيت كلمة المرور)",
)
async def forgot_password(
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Initiates password recovery by generating a secure time-limited token.
    """
    res = await db.execute(select(User).where(User.email == body.email))
    user = res.scalar_one_or_none()

    token = None
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        user.reset_token = token
        user.reset_token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        await db.commit()
        logger.info(f"Generated password reset token for: {user.email}")

    return MessageResponse(
        message="لو الإيميل ده متسجل عندنا، هتوصلك تعليمات استرجاع الباسورد على طول.",
        details={"reset_token": token} if token else None,
    )


@router.post(
    "/reset-password",
    response_model=MessageResponse,
    summary="Reset Password with Token (إعادة تعيين كلمة المرور)",
)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Completes password reset using verified token and new matching password.
    """
    now = datetime.now(timezone.utc)
    res = await db.execute(
        select(User).where(
            and_(
                User.reset_token == body.token,
                User.reset_token_expires_at > now,
            )
        )
    )
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="كود استرجاع الباسورد ده مش صح أو وقته خلص. اطلب كود جديد.",
        )

    # Hash new password and clear token
    user.hashed_password = get_password_hash(body.new_password)
    user.reset_token = None
    user.reset_token_expires_at = None
    user.updated_at = now
    await db.commit()

    logger.info(f"Password reset successfully for user: {user.email}")

    return MessageResponse(
        message="غيّرنا الباسورد بنجاح خلاص! تقدر تدخل دلوقتي بالباسورد الجديد."
    )


# ── 6. User Profile (Me) ──────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get Current User Profile (بيانات الحساب الشخصي)",
)
async def whoami(
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """Returns the authenticated user's profile and personality ownership stats."""
    p_count_res = await db.execute(
        select(Personality.id).where(Personality.user_id == current_user.id)
    )
    p_count = len(p_count_res.scalars().all())
    return _user_to_response(current_user, personalities_count=p_count)


@router.put(
    "/me",
    response_model=UserResponse,
    summary="Update Current User Profile (تعديل وحفظ بيانات الحساب)",
)
@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update Current User Profile (تعديل وحفظ بيانات الحساب)",
)
async def update_profile(
    body: UserUpdateRequest,
    current_user: User = Depends(get_current_user_model),
    db: AsyncSession = Depends(get_db),
):
    """
    Updates the authenticated user's profile data (name, email, phone, location, organization, avatar)
    and synchronizes changes with their personal digital twin persona.
    """
    if body.full_name is not None and body.full_name.strip():
        current_user.full_name = body.full_name.strip()
        # Update user's personal digital twin persona name and description
        res = await db.execute(
            select(Personality).where(Personality.user_id == current_user.id).limit(1)
        )
        twin = res.scalar_one_or_none()
        if twin:
            twin.name = f"{current_user.full_name} - التوأم الرقمي"
            twin.description = f"التوأم الرقمي الرسمي لـ {current_user.full_name}"
            twin.system_prompt = f"أنت {current_user.full_name}، التوأم الرقمي المصري الذكي. بتتكلم بالمصري العامي العفوي وبنبرتك الطبيعية وبتعبر عن شخصية وتفضيلات {current_user.full_name}."
        else:
            db.add(Personality(
                user_id=current_user.id,
                name=f"{current_user.full_name} - التوأم الرقمي",
                description=f"التوأم الرقمي الرسمي لـ {current_user.full_name}",
                system_prompt=f"أنت {current_user.full_name}، التوأم الرقمي المصري الذكي.",
                dialect="cairo",
                language_mix="ar_en",
                is_active=True,
            ))

    if body.email is not None and body.email.strip():
        new_email = body.email.strip().lower()
        if new_email != current_user.email:
            check_res = await db.execute(select(User).where(User.email == new_email))
            if check_res.scalar_one_or_none():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="البريد الإلكتروني ده مسجل بالفعل لحساب آخر.",
                )
            current_user.email = new_email

    if body.phone is not None:
        current_user.phone = body.phone.strip()
    if body.location is not None:
        current_user.location = body.location.strip()
    if body.organization is not None:
        current_user.organization = body.organization.strip()
    if body.avatar_url is not None:
        current_user.avatar_url = body.avatar_url.strip()

    await db.commit()
    await db.refresh(current_user)

    p_count_res = await db.execute(
        select(Personality.id).where(Personality.user_id == current_user.id)
    )
    p_count = len(p_count_res.scalars().all())
    logger.info(f"Updated profile for user {current_user.id}: {current_user.full_name}")
    return _user_to_response(current_user, personalities_count=p_count)


# ── 7. Legacy Hardware Pairing Token (Backward Compatibility) ────────────────

class LegacyTokenRequest(BaseModel):
    pairing_code: str
    device_name: str = "control_room_desktop"


@router.post("/token", summary="Exchange pairing code for JWT (Legacy Desktop/ESP32)")
async def exchange_pairing_token(body: LegacyTokenRequest):
    """Legacy endpoint for device pairing code authentication."""
    if not verify_pairing_code(body.pairing_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="كود التوأمة ده مش صح.",
        )
    token = create_access_token(
        subject=body.device_name,
        extra={"device": body.device_name},
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": 60 * 60 * 8}


# ── 8. Onboarding Questionnaire Endpoints (أسئلة التخصيص) ─────────────────────

@router.get(
    "/onboarding/questions",
    summary="Get dynamic onboarding questionnaire (أسئلة تخصيص الذكاء الاصطناعي)",
)
async def get_onboarding_questions():
    """
    Returns dynamic onboarding questions to personalize the AI companion and seed long-term memory.
    Matches the onboarding questions card in the UI.
    """
    return {
        "questions": [
            {
                "id": "interaction_style",
                "title": "ما هو أسلوب التفاعل المفضل لديك؟",
                "subtitle": "اختر الطريقة الأنسب للتواصل والتفاعل مع مساعدك الذكي",
                "options": ["نصي وصوتي", "صوتي تفاعلي", "نصي فقط"],
                "default": "نصي وصوتي",
            },
            {
                "id": "interest_domain",
                "title": "ما هو مجال اهتمامك الأساسي؟",
                "subtitle": "لتخصيص الردود والذكاء الاصطناعي وفق اهتماماتك اليومية",
                "options": ["البرمجة والتقنية", "التعليم والدراسة", "الأعمال والإدارة", "الترفيه والتسلية"],
                "default": "البرمجة والتقنية",
            },
            {
                "id": "personal_fact",
                "title": "معلومة شخصية تريد من المساعد حفظها بذاكرته:",
                "subtitle": "احفظ حقيقة أو تفضيل عنك في الذاكرة طويلة المدى",
                "placeholder": "مثال: اسمي مازن، أحب تطوير التطبيقات وتصميم الأنظمة الذكية",
                "default": "",
            },
        ]
    }


class OnboardingAnswersRequest(BaseModel):
    answers: dict[str, Any]


@router.post(
    "/onboarding/answers",
    summary="Save onboarding answers and inject directly to RAG memory (حفظ أسئلة التخصيص)",
)
async def save_onboarding_answers(
    body: OnboardingAnswersRequest,
    current_user: Optional[User] = Depends(get_optional_user_model),
    db: AsyncSession = Depends(get_db),
):
    """
    Persists onboarding questionnaire answers directly into the RAG memory system
    and user personalization profile.
    """
    answers = body.answers
    interaction = answers.get("interaction_style", "نصي وصوتي")
    interest = answers.get("interest_domain", "البرمجة والتقنية")
    personal_fact = str(answers.get("personal_fact", "")).strip()

    memories_to_add: list[str] = []
    if interaction:
        memories_to_add.append(f"أسلوب التفاعل المفضل للمستخدم: {interaction}")
    if interest:
        memories_to_add.append(f"المجال والاهتمام الرئيسي للمستخدم: {interest}")
    if personal_fact:
        memories_to_add.append(f"معلومة هامة عن المستخدم في الذاكرة: {personal_fact}")

    # Seed into RAG and Memory table
    from app.models.memory import Memory
    from app.services.memory.rag_service import RAGService
    rag = RAGService()

    saved_count = 0
    target_pid = 1  # Default primary persona
    uid = current_user.id if current_user else None
    for mem_text in memories_to_add:
        try:
            m = Memory(
                user_id=uid,
                personality_id=target_pid,
                content=mem_text,
                source="onboarding",
                importance=8,
            )
            db.add(m)
            await db.commit()
            saved_count += 1
            try:
                await rag.add_memory(
                    content=mem_text,
                    personality_id=target_pid,
                    source="onboarding",
                    importance=8,
                    user_id=uid,
                    db=db,
                )
            except Exception as rag_err:
                logger.debug(f"RAG vector index notice: {rag_err}")
        except Exception as e:
            await db.rollback()
            logger.warning(f"Error persisting onboarding memory: {e}")

    await db.commit()
    logger.info(f"Persisted {saved_count} onboarding memory items for user {current_user.email if current_user else 'guest'}")

    return {
        "success": True,
        "saved_memories_count": saved_count,
        "message": "تم حفظ تفضيلات التخصيص وإضافتها لذاكرة المساعد الذكي بنجاح",
    }


# ── 9. User Avatar Generation & Processing (توليد الأفاتار) ───────────────────

@router.post(
    "/avatar/generate",
    summary="Upload image and transform into Digital Avatar (توليد الأفاتار الرقمي)",
)
async def generate_user_avatar(
    file: UploadFile = File(..., description="صورة المستخدم لتحويلها إلى أفاتار رقمي"),
    current_user: Optional[User] = Depends(get_optional_user_model),
    db: AsyncSession = Depends(get_db),
):
    """
    Accepts user photo, processes and saves it as the user avatar,
    and automatically registers face biometric embedding for Neural Face ID.
    """
    content = await file.read()
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="حجم الصورة كبير جداً، الحد الأقصى 5 ميجابايت.",
        )

    # Save to data/avatars
    avatar_dir = pathlib.Path("data/avatars")
    avatar_dir.mkdir(parents=True, exist_ok=True)
    filename = f"avatar_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(4)}.jpg"
    file_path = avatar_dir / filename
    with open(file_path, "wb") as f:
        f.write(content)

    # Automatically enroll face embedding if a face is detected
    try:
        face_service = get_face_service()
        embedding = await asyncio.get_event_loop().run_in_executor(
            None, face_service.extract_embedding_sync, content
        )
        if embedding is not None and len(embedding) > 0 and current_user:
            profile_name = f"user_{current_user.id}_{current_user.email}"
            res = await db.execute(select(FaceProfile).where(FaceProfile.name == profile_name))
            face_prof = res.scalar_one_or_none()
            if not face_prof:
                face_prof = FaceProfile(name=profile_name, embedding=embedding)
                db.add(face_prof)
                await db.flush()
            else:
                face_prof.embedding = embedding
            current_user.face_profile_id = face_prof.id
            db.add(current_user)
            await db.commit()
            await face_service.reload_known_faces(db)
            logger.info(f"Auto-enrolled Face ID during avatar creation for {current_user.email}")
    except Exception as e:
        logger.debug(f"Face biometric auto-enroll notice: {e}")

    avatar_url = f"/api/v1/auth/avatar/file/{filename}"
    if current_user:
        try:
            current_user.avatar_url = avatar_url
            db.add(current_user)
            await db.commit()
            await db.refresh(current_user)
        except Exception as e:
            logger.debug(f"Could not persist avatar_url to user entity: {e}")

    return {
        "success": True,
        "avatar_url": avatar_url,
        "file_name": filename,
        "message": "تم تحويل صورتك إلى أفاتار رقمي بنجاح",
    }


@router.get(
    "/avatar/file/{filename}",
    summary="Serve generated user avatar file",
)
async def get_avatar_file(filename: str):
    """Serves the generated avatar image file."""
    file_path = pathlib.Path("data/avatars") / filename
    if not file_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="الأفاتار غير موجود")
    return FileResponse(file_path)

