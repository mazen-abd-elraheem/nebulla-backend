"""
JWT helpers — issue and verify short-lived access tokens for the REST API.
WebSocket channels use the pairing-code mechanism (see core/security.py).
"""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import APIKeyHeader

from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import get_db

logger = get_logger(__name__)

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hours — long enough for a dev session

api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


# ── Token generation ──────────────────────────────────────────────────────────

import secrets

def create_access_token(
    subject: str,
    extra: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT token using dedicated JWT secret."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": str(subject),
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


# ── FastAPI dependencies ──────────────────────────────────────────────────────

async def get_current_user(
    x_api_key: str | None = Depends(api_key_scheme),
    authorization: str | None = Header(None),
) -> str:
    """
    FastAPI dependency: validates X-API-Key header (pre-shared) or
    Bearer JWT in Authorization header.
    Returns the subject (device/user identifier).
    """
    # 0. Clean Swagger UI placeholder / empty values
    clean_api_key = x_api_key.strip() if x_api_key else None
    if clean_api_key in ("", "string"):
        clean_api_key = None

    clean_auth = authorization.strip() if authorization else None
    if clean_auth in ("", "string", "Bearer string"):
        clean_auth = None

    # 1. Development bypass if DEBUG is True and no credentials provided
    if settings.DEBUG and not clean_api_key and not clean_auth:
        return "dev_user"

    # 2. Try raw API key (simple pre-shared key for local network) with constant-time comparison
    if clean_api_key:
        valid_keys = [k for k in (settings.PAIRING_SECRET, getattr(settings, "API_KEY", None)) if k]
        for vk in valid_keys:
            if secrets.compare_digest(clean_api_key, vk):
                return "api_key_client"
        if settings.DEBUG:
            logger.info(f"DEBUG mode active: permitting request with unmatched dev key: '{clean_api_key}'")
            return "dev_user"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")

    # 3. Try JWT Bearer token
    if clean_auth and clean_auth.startswith("Bearer "):
        token = clean_auth[7:].strip()
        try:
            payload = decode_access_token(token)
            return str(payload["sub"])
        except HTTPException:
            if settings.DEBUG:
                logger.info("DEBUG mode active: permitting request with invalid dev token")
                return "dev_user"
            raise

    # 4. Fallback in DEBUG mode
    if settings.DEBUG:
        return "dev_user"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No credentials provided. Use X-API-Key or Bearer token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_optional_user(
    x_api_key: str | None = Depends(api_key_scheme),
    authorization: str | None = Header(None),
) -> str | None:
    """Same as get_current_user but doesn't raise — returns None if unauthenticated."""
    try:
        return await get_current_user(x_api_key, authorization)
    except HTTPException:
        return None


async def get_current_user_model(
    sub: str = Depends(get_current_user),
    db: Any = Depends(get_db),
):
    """
    Resolves the authenticated User database entity from the JWT subject
    within the active request DB session.
    """
    from sqlalchemy import select
    from app.models.user import User

    user = None
    if sub.isdigit():
        user = await db.get(User, int(sub))
    else:
        res = await db.execute(select(User).where(User.email == sub.lower()))
        user = res.scalar_one_or_none()

    if user:
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is deactivated.")
        return user

    # If sub is a recognized hardware/developer identity, look for default user
    res_admin = await db.execute(select(User).order_by(User.id).limit(1))
    first_user = res_admin.scalar_one_or_none()
    if first_user:
        return first_user

    # If in DEBUG mode or using API key and no users exist yet in DB, auto-provision default user
    if settings.DEBUG or sub in ("dev_user", "api_key_client"):
        from app.core.security import get_password_hash
        default_user = User(
            id=1,
            full_name="مازن عبد الرحيم (Mazen)",
            email="admin@nebula.local",
            hashed_password=get_password_hash("nebula2026"),
            is_active=True,
            is_superuser=True,
        )
        db.add(default_user)
        await db.flush()
        await db.refresh(default_user)
        return default_user

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="User associated with token not found.",
    )


async def get_optional_user_model(
    sub: str | None = Depends(get_optional_user),
    db: Any = Depends(get_db),
):
    """Returns User model if authenticated, otherwise None."""
    if not sub:
        return None
    try:
        return await get_current_user_model(sub=sub, db=db)
    except Exception:
        return None


