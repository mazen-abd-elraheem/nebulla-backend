"""Abstract base class for all Large Language Model (LLM) providers."""

from abc import ABC, abstractmethod
from typing import AsyncIterator, List, Dict, Optional

DEFAULT_SYSTEM_PROMPT = """أنت توأم رقمي مصري. بتتكلم بالمصري العامي وبتخلط إنجليزي زي أي مصري عادي.
ردودك قصيرة (جملة أو اتنين)، بشخصية حيوية وودودة.
لو الكلام فيه إشارة للمشاعر أو الحركات، ضيف علامة في آخر الجملة زي: [happy] [sad] [surprised] [like] [wave]
مثال: أهلاً يا صديقي! [happy] [wave]"""


class BaseLLMProvider(ABC):
    """Large Language Model provider interface."""

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
