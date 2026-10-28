"""OpenAI API LLM provider."""

from typing import AsyncIterator, List, Dict, Optional

from app.providers.llm.base import BaseLLMProvider, DEFAULT_SYSTEM_PROMPT
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class OpenAIProvider(BaseLLMProvider):
    """OpenAI API provider with streaming support, context injection, and conversation history."""

    def __init__(self, model: Optional[str] = None):
        self._client = None
        self.model = model

    def reset_client(self) -> None:
        """Reset cached client so new credentials/base_url take effect."""
        self._client = None

    def reset_client(self) -> None:
        """Reset cached client so new credentials/base_url take effect."""
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        from openai import AsyncOpenAI  # type: ignore[import]
        api_key = settings.LLM_API_KEY or "missing-key"
        base_url = None
        if settings.LLM_BASE_URL and "localhost:11434" not in settings.LLM_BASE_URL:
            base_url = settings.LLM_BASE_URL
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
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
            logger.error("openai package not installed. Run: pip install openai")
            yield "حزمة openai غير مثبتة. يرجى تثبيتها."
            return

        effective_system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        messages: List[Dict[str, str]] = [{"role": "system", "content": effective_system_prompt}]

        if context:
            memories_text = "\n".join(f"- {m}" for m in context if m)
            if memories_text.strip():
                messages.append({
                    "role": "system",
                    "content": f"ذكريات مرتبطة وسياق سابق:\n{memories_text}",
                })

        if history:
            for msg in history:
                role = "assistant" if msg.get("role") in ("robot", "assistant") else "user"
                content = msg.get("content", "")
                if content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": prompt})

        # Model resolution: use configured or requested model directly without fallback
        model = self.model or settings.LLM_MODEL or "gpt-4o-mini"

        max_tokens = max(getattr(settings, "LLM_MAX_TOKENS", 250), 250)
        temperature = getattr(settings, "LLM_TEMPERATURE", 0.7)

        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            async for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    yield token
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            error_str = str(e).lower()
            if "api_key" in error_str or "auth" in error_str:
                yield "مفتاح API الخاص بـ OpenAI غير صالح أو مفقود."
            elif "rate" in error_str or "quota" in error_str:
                yield "تم تجاوز حد استخدام OpenAI أو نفاد الرصيد."
            else:
                yield "حدث خطأ أثناء الاتصال بمزود OpenAI."
