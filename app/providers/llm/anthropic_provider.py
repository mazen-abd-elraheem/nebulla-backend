"""Anthropic Claude LLM provider."""

from typing import AsyncIterator, List, Dict, Optional

from app.providers.llm.base import BaseLLMProvider, DEFAULT_SYSTEM_PROMPT
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class AnthropicProvider(BaseLLMProvider):
    """Anthropic Claude API provider with streaming support."""

    def __init__(self, model: Optional[str] = None):
        self._client = None
        self.model = model

    def reset_client(self) -> None:
        """Reset cached client so new credentials take effect."""
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        from anthropic import AsyncAnthropic  # type: ignore[import]
        api_key = settings.LLM_API_KEY or "missing-key"
        self._client = AsyncAnthropic(api_key=api_key)
        return self._client

    async def generate(
        self,
        prompt: str,
        context: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        chunks = []
        async for t in self.generate_stream(prompt, context, system_prompt, history):
            chunks.append(t)
        return "".join(chunks)

    async def generate_stream(
        self,
        prompt: str,
        context: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        try:
            client = self._get_client()
        except ImportError:
            logger.error("anthropic package not installed. Run: pip install anthropic")
            yield "حزمة anthropic غير مثبتة. يرجى تثبيتها لاستخدام مزود Claude."
            return

        effective_system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        if context:
            memories_text = "\n".join(f"- {m}" for m in context if m)
            if memories_text.strip() and "ذكريات" not in effective_system_prompt:
                effective_system_prompt += f"\n\nذكريات مرتبطة:\n{memories_text}"

        messages: List[Dict[str, str]] = []
        if history:
            for msg in history:
                role = "assistant" if msg.get("role") in ("robot", "assistant") else "user"
                content = msg.get("content", "")
                if content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": prompt})

        # Model resolution: use configured or requested model directly without fallback
        model = self.model or settings.LLM_MODEL or "claude-3-5-sonnet-20241022"

        max_tokens = getattr(settings, "LLM_MAX_TOKENS", 250)

        try:
            async with client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=effective_system_prompt,
                messages=messages,
            ) as stream:
                async for text in stream.text_stream:
                    if text:
                        yield text
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            yield "حدث خطأ أثناء الاتصال بمزود Anthropic Claude."
