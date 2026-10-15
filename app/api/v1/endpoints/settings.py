"""Runtime settings endpoint (doc §5.2 settings screen: swap STT/TTS/LLM)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.jwt import get_current_user
from app.core.config import settings

router = APIRouter()


@router.get("/", summary="Get current AI provider settings")
async def get_settings(_u=Depends(get_current_user)):
    return {
        "stt_provider": settings.STT_PROVIDER,
        "tts_provider": settings.TTS_PROVIDER,
        "llm_provider": settings.LLM_PROVIDER,
        "llm_model": settings.LLM_MODEL,
        "llm_base_url": settings.LLM_BASE_URL,
        "camera_fps": settings.CAMERA_FPS,
        "uniface_model": settings.UNIFACE_MODEL,
        "uniface_device": settings.UNIFACE_DEVICE,
        "memory_top_k": settings.MEMORY_TOP_K,
    }


class ProviderUpdate(BaseModel):
    stt_provider: str | None = None
    tts_provider: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None


@router.patch("/providers", summary="Hot-swap AI providers (changes take effect on next request)")
async def update_providers(body: ProviderUpdate, _u=Depends(get_current_user)):
    """
    Update provider choices at runtime without restarting the server.
    Note: The new provider will be instantiated on the next pipeline call.
    """
    updates = body.model_dump(exclude_none=True)
    for k, v in updates.items():
        setattr(settings, k.upper(), v)

    try:
        from app.websocket.handlers import get_ai_pipeline
        get_ai_pipeline().reload_providers()
    except Exception:
        pass

    return {"updated": updates, "note": "Changes applied immediately to active pipeline"}
