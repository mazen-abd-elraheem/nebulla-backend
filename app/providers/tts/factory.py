"""
TTS provider factory — strictly VoiceTut-TTS (in-process or standalone microservice).
"""

from app.providers.tts.base import BaseTTSProvider
from app.core.logger import get_logger

logger = get_logger(__name__)


def get_tts_provider(name: str | None = None) -> BaseTTSProvider:
    """Return the TTS provider instance matching *name* (exclusively VoiceTut)."""
    provider_name = (name or "voicetut_service").lower().strip()

    if provider_name == "voicetut_service":
        from app.providers.tts.voicetut_microservice import VoiceTutMicroserviceProvider
        return VoiceTutMicroserviceProvider()

    if provider_name == "voicetut":
        from app.providers.tts.voicetut import VoiceTutProvider
        return VoiceTutProvider()

    raise ValueError(
        f"Invalid or disabled TTS provider: {name!r}. "
        "Strict single-engine policy: choose from 'voicetut_service' or 'voicetut'."
    )

