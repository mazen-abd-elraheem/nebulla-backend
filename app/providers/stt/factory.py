"""STT provider factory — strictly Egyptian Arabic ASR (QwenCleo)."""

from app.providers.tts.base import BaseSTTProvider
from app.core.logger import get_logger

logger = get_logger(__name__)


def get_stt_provider(name: str | None = None) -> BaseSTTProvider:
    """Return the STT provider instance matching *name* (exclusively QwenCleo)."""
    provider_name = (name or "qwencleo").lower().strip()

    if provider_name == "qwencleo":
        from app.providers.stt.qwencleo import QwenCleoProvider
        return QwenCleoProvider()

    if provider_name == "nemotron":
        from app.providers.stt.nemotron import NemotronProvider
        return NemotronProvider()

    raise ValueError(
        f"Invalid or disabled STT provider: {name!r}. "
        "Strict single-engine policy: choose 'qwencleo'."
    )

