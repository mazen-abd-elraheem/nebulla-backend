"""STT provider factory — selects the implementation from config (doc §6)."""

from app.providers.tts.base import BaseSTTProvider
from app.core.logger import get_logger

logger = get_logger(__name__)


def get_stt_provider(name: str) -> BaseSTTProvider:
    """Return the STT provider instance matching *name*."""
    if name == "qwencleo":
        from app.providers.stt.qwencleo import QwenCleoProvider
        return QwenCleoProvider()

    if name == "whisper":
        from app.providers.stt.whisper import WhisperProvider
        return WhisperProvider()

    if name == "nemotron":
        from app.providers.stt.nemotron import NemotronProvider
        return NemotronProvider()

    raise ValueError(f"Unknown STT provider: {name!r}. Choose from: qwencleo, whisper, nemotron")
