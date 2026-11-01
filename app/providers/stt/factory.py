"""STT provider factory — selects the implementation from config (doc §6)."""

from typing import Dict
from app.providers.tts.base import BaseSTTProvider
from app.core.logger import get_logger

logger = get_logger(__name__)

_provider_cache: Dict[str, BaseSTTProvider] = {}


def get_stt_provider(name: str | None = None) -> BaseSTTProvider:
    """Return cached STT provider instance matching *name*."""
    provider_name = (name or "whisper").lower().strip()

    if provider_name in _provider_cache:
        return _provider_cache[provider_name]

    if provider_name == "whisper":
        from app.providers.stt.whisper import WhisperProvider
        instance = WhisperProvider()
    elif provider_name == "qwencleo":
        from app.providers.stt.qwencleo import QwenCleoProvider
        instance = QwenCleoProvider()
    elif provider_name in ("groq", "openai"):
        from app.providers.stt.groq_provider import GroqSTTProvider
        instance = GroqSTTProvider()
    elif provider_name == "nemotron":
        from app.providers.stt.nemotron import NemotronProvider
        instance = NemotronProvider()
    else:
        logger.warning(f"Unknown STT provider '{name}'. Falling back to 'whisper'.")
        from app.providers.stt.whisper import WhisperProvider
        instance = WhisperProvider()

    _provider_cache[provider_name] = instance
    return instance
