"""
Auth router — REST endpoints for login, token refresh, and API key management.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.auth.jwt import create_access_token, get_current_user
from app.core.security import verify_pairing_code

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    pairing_code: str
    device_name: str = "unknown"


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 60 * 60 * 8  # seconds


@router.post("/token", response_model=TokenResponse, summary="Exchange pairing code for JWT")
async def login(body: LoginRequest):
    """
    Exchange the pairing code for a short-lived JWT access token.
    Used by the Flutter desktop app to authenticate REST calls.
    """
    if not verify_pairing_code(body.pairing_code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid pairing code",
        )
    token = create_access_token(
        subject=body.device_name,
        extra={"device": body.device_name},
    )
    return TokenResponse(access_token=token)


@router.get("/me", summary="Get current authenticated identity")
async def whoami(current_user: str = Depends(get_current_user)):
    return {"identity": current_user}
