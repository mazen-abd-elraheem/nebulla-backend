"""
TTS provider factory — strictly VoiceTut-powered XTTS voice cloning engine.
"""

from __future__ import annotations

from typing import Optional

from app.core.logger import get_logger
from app.providers.tts.base import BaseTTSProvider

logger = get_logger(__name__)


def get_tts_provider(name: Optional[str] = None) -> BaseTTSProvider:
    """
    Return the TTS provider instance (exclusively VoiceTut-powered XTTS).
    Defaults strictly to XTTSProvider.
    """
    from app.core.config import settings

    provider_name = (name or getattr(settings, "TTS_PROVIDER", "xtts")).lower().strip()

    if provider_name in ("xtts", "voicetut", "voicetut_service", "default", "local"):
        from app.providers.tts.xtts.provider import XTTSProvider
        return XTTSProvider()

    logger.warning(f"Unknown or non-standard TTS provider {name!r}, falling back strictly to VoiceTut XTTS.")
    from app.providers.tts.xtts.provider import XTTSProvider
    return XTTSProvider()
