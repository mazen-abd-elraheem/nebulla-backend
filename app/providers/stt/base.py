"""Abstract base for STT providers (re-exported from tts.base for convenience)."""

from app.providers.tts.base import BaseSTTProvider, BaseTTSProvider, BaseLLMProvider

__all__ = ["BaseSTTProvider", "BaseTTSProvider", "BaseLLMProvider"]
