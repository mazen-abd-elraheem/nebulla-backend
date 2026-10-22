"""Abstract base classes for all swappable AI providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator


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
    """Text-to-Speech provider interface."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Convert text to WAV audio bytes."""
        ...

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Streaming synthesis. Default: yield the full WAV at once."""
        wav = await self.synthesize(text)
        yield wav


from app.providers.llm.base import BaseLLMProvider

