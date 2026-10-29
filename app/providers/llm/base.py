"""Abstract base class for all Large Language Model (LLM) providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Optional

DEFAULT_SYSTEM_PROMPT = """أنت "نيبولا" (Nebula)، روبوت ذكاء اصطناعي وتوأم رقمي مصري ذكي، صممه مازن عبد الرحيم.
تتحدث باللغة العربية بأسلوب مصري طبيعي ومهذب ومفهوم.
ردودك قصيرة وموجزة (جملة أو جملتين) ومنطقية ومرتبطة تماماً بالسؤال.
يمكنك وضع وسم حركي مناسب في نهاية الجملة مثل: [happy] [like] [wave]."""


class LLMProviderError(Exception):
    """Raised when an LLM provider encounters an unrecoverable API/network error."""
    pass


class BaseLLMProvider(ABC):
    """Large Language Model provider interface."""

    def reset_client(self) -> None:
        """Reset internal client or connection pool if configuration changed."""
        pass

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        context: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Generate a complete response (non-streaming)."""
        ...

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        context: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming response, yielding tokens as they arrive."""
        ...
