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

logger = get_logger(__name__)

_ALGORITHM = "HS256"
_TOKEN_EXPIRE_MINUTES = 60 * 8  # 8 hours — long enough for a dev session

api_key_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)


# ── Token generation ──────────────────────────────────────────────────────────

def create_access_token(subject: str, extra: dict[str, Any] | None = None) -> str:
    """Create a signed JWT token."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.PAIRING_SECRET, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT token. Raises HTTPException on failure."""
    try:
        return jwt.decode(token, settings.PAIRING_SECRET, algorithms=[_ALGORITHM])
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
    # 0. Development bypass if DEBUG is True and no credentials provided
    if settings.DEBUG and not x_api_key and not authorization:
        return "dev_user"

    # 1. Try raw API key (simple pre-shared key for local network)
    if x_api_key:
        import hashlib
        key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
        # In production query DB for this hash; for now accept any matching pairing secret
        if x_api_key == settings.PAIRING_SECRET:
            return "api_key_client"
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")

    # 2. Try JWT Bearer token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        payload = decode_access_token(token)
        return payload["sub"]

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
