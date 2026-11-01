"""STT provider factory — supports QwenCleo Egyptian Arabic ASR and Whisper."""

from typing import Dict
from app.providers.tts.base import BaseSTTProvider
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_provider_cache: Dict[str, BaseSTTProvider] = {}


def get_stt_provider(name: str | None = None) -> BaseSTTProvider:
    """Return cached STT provider instance matching *name*."""
    provider_name = (name or getattr(settings, "STT_PROVIDER", "qwencleo")).lower().strip()

    if provider_name in _provider_cache:
        return _provider_cache[provider_name]

    if provider_name == "qwencleo":
        from app.providers.stt.qwencleo import QwenCleoProvider
        instance = QwenCleoProvider()
    elif provider_name == "whisper":
        from app.providers.stt.whisper import WhisperProvider
        instance = WhisperProvider()
    elif provider_name == "nemotron":
        from app.providers.stt.nemotron import NemotronProvider
        instance = NemotronProvider()
    else:
        logger.warning(f"Unknown STT provider '{name}'. Falling back to 'qwencleo'.")
        from app.providers.stt.qwencleo import QwenCleoProvider
        instance = QwenCleoProvider()

    _provider_cache[provider_name] = instance
    return instance
