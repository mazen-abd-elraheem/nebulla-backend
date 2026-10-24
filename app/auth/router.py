"""
Auth Router — Production User Registration, Login, Biometric Neural Face ID,
Password Recovery, and Profile Management endpoints.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import io
import secrets
from typing import Any, Optional

import numpy as np
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import (
    create_access_token,
    get_current_user,
    get_current_user_model,
)
from app.auth.schemas import (
    AuthTokenResponse,
    ForgotPasswordRequest,
    MessageResponse,
    ResetPasswordRequest,
    UserLogin,
    UserRegister,
    UserResponse,
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
        email=user.email,
        is_active=user.is_active,
        has_biometric=user.face_profile_id is not None,
        personalities_count=personalities_count,
        created_at=user.created_at,
    )


def _cosine_similarity(emb1: Any, emb2: Any) -> float:
    """Calculate cosine similarity between two face embeddings."""
    try:
        a = np.array(emb1, dtype=np.float32).flatten()
        b = np.array(emb2, dtype=np.float32).flatten()
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
            detail="البريد الإلكتروني مسجل بالفعل. يرجى تسجيل الدخول أو استخدام بريد آخر.",
        )

    # Hash password with bcrypt
    hashed_pwd = get_password_hash(body.password)

    new_user = User(
        full_name=body.full_name.strip(),
        email=clean_email,
        hashed_password=hashed_pwd,
        terms_accepted=True,
        terms_accepted_at=datetime.now(timezone.utc),
        is_active=True,
    )
    db.add(new_user)
    await db.flush()
    await db.refresh(new_user)

    # Create access token (8 hours initial session)
    token_delta = timedelta(hours=8)
    token = create_access_token(
        subject=str(new_user.id),
        extra={"email": new_user.email, "name": new_user.full_name},
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
    summary="User Login with Email & Password (تسجيل الدخول)",
)
async def login(
    body: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """
    Standard login using Email and Password with optional 'Remember Me':
    - If remember_me is True: token valid for 30 days (2,592,000s)
    - If remember_me is False: token valid for 8 hours (28,800s)
    """
    clean_email = body.email.strip().lower()

    res = await db.execute(select(User).where(User.email == clean_email))
    user = res.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="البريد الإلكتروني أو كلمة المرور غير صحيحة.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="هذا الحساب معطل حالياً. يرجى التواصل مع الدعم الفني.",
        )

    # Determine token lifetime based on remember_me
    if body.remember_me:
        token_delta = timedelta(days=30)
    else:
        token_delta = timedelta(hours=8)

    token = create_access_token(
        subject=str(user.id),
        extra={"email": user.email, "name": user.full_name},
        expires_delta=token_delta,
    )

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
    email: str = Form(..., description="البريد الإلكتروني للمستخدم"),
    file: UploadFile = File(..., description="صورة الوجه المباشرة (JPEG/PNG) للتحقق"),
    db: AsyncSession = Depends(get_db),
):
    """
    1:1 Biometric Face ID Verification matching the 'Neural Face ID' button in UI:
    Verifies live face image against the user's enrolled biometric profile using UniFace.
    """
    clean_email = email.strip().lower()

    res = await db.execute(select(User).where(User.email == clean_email))
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="لم يتم العثور على حساب بهذا البريد الإلكتروني.",
        )

    if not user.face_profile_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="بصمة الوجه (Neural Face ID) غير مفعلة لهذا الحساب بعد. سجل الدخول بكلمة المرور لتفعيلها.",
        )

    # Read image bytes safely
    image_bytes = await file.read(MAX_IMAGE_BYTES + 1)
    if len(image_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="حجم صورة الوجه يتجاوز الحد المسموح به (5 ميجابايت).",
        )

    if not (image_bytes.startswith(b"\xff\xd8") or image_bytes.startswith(b"\x89PNG\r\n\x1a\n")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="صيغة الصورة غير مدعومة. يرجى التقاط صورة بصيغة JPEG أو PNG.",
        )

    # Fetch user's registered face profile
    face_prof = await db.get(FaceProfile, user.face_profile_id)
    if not face_prof or not face_prof.embedding:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="تعذر العثور على بصمة الوجه المسجلة للحساب.",
        )

    # Extract embedding from submitted face
    face_service = get_face_service()
    loop = asyncio.get_event_loop()
    live_embedding = await loop.run_in_executor(
        None, face_service.extract_embedding_sync, image_bytes
    )

    if not live_embedding:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="لم يتم اكتشاف وجه واضح في الصورة. يرجى توجيه الكاميرا جيداً وإعادة المحاولة.",
        )

    # Compare embeddings with cosine similarity
    similarity = _cosine_similarity(live_embedding, face_prof.embedding)
    MATCH_THRESHOLD = 0.50

    if similarity < MATCH_THRESHOLD:
        logger.warning(
            f"Biometric mismatch for {user.email}: similarity {similarity:.3f} < {MATCH_THRESHOLD}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="فشل التحقق: بصمة الوجه غير متطابقة مع بيانات الحساب المسجلة.",
        )

    # Biometric match succeeded
    token_delta = timedelta(hours=8)
    token = create_access_token(
        subject=str(user.id),
        extra={"email": user.email, "name": user.full_name, "auth_method": "face_id"},
        expires_delta=token_delta,
    )

    p_count_res = await db.execute(select(Personality.id).where(Personality.user_id == user.id))
    p_count = len(p_count_res.scalars().all())

    logger.info(f"Neural Face ID login succeeded for {user.email} (similarity: {similarity:.3f})")

    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=int(token_delta.total_seconds()),
        user=_user_to_response(user, personalities_count=p_count),
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
            detail="حجم الصورة يتجاوز الحد المسموح به (5 ميجابايت).",
        )

    if not (image_bytes.startswith(b"\xff\xd8") or image_bytes.startswith(b"\x89PNG\r\n\x1a\n")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="صيغة الصورة غير مدعومة. يرجى رفع صورة JPEG أو PNG صالحة.",
        )

    face_service = get_face_service()
    loop = asyncio.get_event_loop()
    embedding = await loop.run_in_executor(
        None, face_service.extract_embedding_sync, image_bytes
    )

    if not embedding:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="لم يتمكن النظام من اكتشاف وجه واضح في الصورة لاستخراج البصمة.",
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
        message="تم تفعيل بصمة الوجه (Neural Face ID) بنجاح لهذا الحساب.",
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
        message="إذا كان البريد الإلكتروني مسجلاً لدينا، فسيتم إرسال تعليمات استعادة الحساب.",
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
            detail="رمز استعادة كلمة المرور غير صالح أو انتهت صلاحيته.",
        )

    # Hash new password and clear token
    user.hashed_password = get_password_hash(body.new_password)
    user.reset_token = None
    user.reset_token_expires_at = None
    user.updated_at = now
    await db.commit()

    logger.info(f"Password reset successfully for user: {user.email}")

    return MessageResponse(
        message="تمت إعادة تعيين كلمة المرور بنجاح. يمكنك الآن تسجيل الدخول بكلمة المرور الجديدة."
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
            detail="Invalid pairing code",
        )
    token = create_access_token(
        subject=body.device_name,
        extra={"device": body.device_name},
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": 60 * 60 * 8}
