"""
Abstract base class for LLM providers.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class BaseLLMProvider(ABC):
    """Large Language Model provider interface."""

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        context: list[str] | list[dict] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate a complete response (non-streaming)."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        context: list[str] | list[dict] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Generate a streaming response, yielding tokens as they arrive."""
        ...
