"""Abstract base classes for all swappable AI providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional

from app.providers.llm.base import BaseLLMProvider


class BaseSTTProvider(ABC):
    """Speech-to-Text provider interface."""

    @abstractmethod
    async def transcribe(self, audio_bytes: bytes) -> str:
        """Convert raw audio bytes to a text transcript."""
        ...

    async def transcribe_stream(self, audio_bytes: bytes) -> AsyncIterator[str]:
        """Streaming transcription. Default: yield the full result at once."""
        result = await self.transcribe(audio_bytes)
        yield result


class BaseTTSProvider(ABC):
    """
    Text-to-Speech provider interface.
    Root base for Egyptian voice cloning powered by VoiceTut XTTS.
    """

    @abstractmethod
    async def synthesize(self, text: str, **kwargs) -> bytes:
        """Convert text to WAV audio bytes."""
        ...

    async def synthesize_stream(self, text: str, **kwargs) -> AsyncIterator[bytes]:
        """Streaming synthesis. Default: yield the full WAV at once."""
        wav = await self.synthesize(text, **kwargs)
        yield wav

    async def clone_voice(
        self,
        reference_wav: str,
        text: str,
        language: str = "arz",
        **kwargs,
    ) -> bytes:
        """Clone voice from reference WAV audio."""
        return await self.synthesize(text, ref_audio=reference_wav, language=language, **kwargs)

    @classmethod
    def get_default(cls) -> "BaseTTSProvider":
        """Returns the default VoiceTut-powered XTTS engine."""
        from app.providers.tts.xtts.provider import XTTSProvider
        return XTTSProvider()


__all__ = ["BaseSTTProvider", "BaseTTSProvider", "BaseLLMProvider"]
