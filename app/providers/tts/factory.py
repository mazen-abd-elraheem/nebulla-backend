"""
TTS provider factory — selects VoiceTut, XTTS, or ar-EG free service (doc §6).
"""

from app.providers.tts.base import BaseTTSProvider
from app.core.logger import get_logger

logger = get_logger(__name__)


def get_tts_provider(name: str) -> BaseTTSProvider:
    """Return the TTS provider instance matching *name*."""
    if name == "voicetut":
        from app.providers.tts.voicetut import VoiceTutProvider
        return VoiceTutProvider()

    if name == "xtts":
        from app.providers.tts.xtts.provider import XTTSProvider
        return XTTSProvider()

    if name == "ar_eg_free":
        from app.providers.tts.ar_eg_free import ArEgFreeProvider
        return ArEgFreeProvider()

    if name == "voicetut_service":
        from app.providers.tts.voicetut_microservice import VoiceTutMicroserviceProvider
        return VoiceTutMicroserviceProvider()

    raise ValueError(
        f"Unknown TTS provider: {name!r}. "
        "Choose from: voicetut, voicetut_service, xtts, ar_eg_free"
    )
