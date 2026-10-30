"""STT provider factory — selects the implementation from config (doc §6)."""

from app.providers.tts.base import BaseSTTProvider
from app.core.logger import get_logger

logger = get_logger(__name__)


def get_stt_provider(name: str | None = None) -> BaseSTTProvider:
    """Return the STT provider instance matching *name*."""
    provider_name = (name or "whisper").lower().strip()

    if provider_name == "whisper":
        from app.providers.stt.whisper import WhisperProvider
        return WhisperProvider()

    if provider_name == "qwencleo":
        from app.providers.stt.qwencleo import QwenCleoProvider
        return QwenCleoProvider()

    if provider_name == "groq":
        from app.providers.stt.groq_provider import GroqSTTProvider
        return GroqSTTProvider()

    if provider_name == "openai":
        from app.providers.stt.groq_provider import GroqSTTProvider
        return GroqSTTProvider()

    if provider_name == "nemotron":
        from app.providers.stt.nemotron import NemotronProvider
        return NemotronProvider()

    # Default fallback to whisper
    logger.warning(f"Unknown STT provider '{name}'. Falling back to 'whisper'.")
    from app.providers.stt.whisper import WhisperProvider
    return WhisperProvider()
