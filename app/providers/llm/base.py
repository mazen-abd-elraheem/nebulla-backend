"""
Abstract base class for LLM providers.
"""

from abc import ABC, abstractmethod
from typing import AsyncIterator


class BaseLLMProvider(ABC):
    """Large Language Model provider interface."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        context: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        """Generate a complete response (non-streaming)."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        context: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response, yielding tokens as they arrive."""
        ...
