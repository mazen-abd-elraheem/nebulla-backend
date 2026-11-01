"""Main API v1 router — aggregates all endpoint sub-routers."""

from fastapi import APIRouter

from app.auth.router import router as auth_router
from app.api.v1.endpoints import (
    devices,
    personalities,
    memories,
    conversations,
    signals,
    calibration,
    voice_clone,
    audio,
    settings as settings_ep,
    diagnostics,
    faces,
    phone_actions,
)

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(faces.router,          prefix="/faces",          tags=["faces"])
api_router.include_router(devices.router,        prefix="/devices",        tags=["devices"])
api_router.include_router(personalities.router,  prefix="/personalities",  tags=["personalities"])
api_router.include_router(memories.router,       prefix="/memories",       tags=["memories"])
api_router.include_router(conversations.router,  prefix="/conversations",  tags=["conversations"])
api_router.include_router(signals.router,        prefix="/signals",        tags=["signals"])
api_router.include_router(calibration.router,    prefix="/calibration",    tags=["calibration"])
api_router.include_router(voice_clone.router,    prefix="/voice-clone",    tags=["voice-clone"])
api_router.include_router(audio.router,          prefix="/audio",          tags=["audio"])
api_router.include_router(phone_actions.router,  prefix="/actions",        tags=["phone-actions"])
api_router.include_router(settings_ep.router,    prefix="/settings",       tags=["settings"])
api_router.include_router(diagnostics.router,    prefix="/diagnostics",    tags=["diagnostics"])
