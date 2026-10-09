"""OpenAI API LLM provider."""

from typing import AsyncIterator
from app.providers.tts.base import BaseLLMProvider
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class OpenAIProvider(BaseLLMProvider):
    async def generate(self, prompt: str, context: list[str] | None = None) -> str:
        chunks = []
        async for t in self.generate_stream(prompt, context):
            chunks.append(t)
        return "".join(chunks)

    async def generate_stream(self, prompt: str, context: list[str] | None = None) -> AsyncIterator[str]:
        try:
            from openai import AsyncOpenAI  # type: ignore[import]
            client = AsyncOpenAI(api_key=settings.LLM_API_KEY)
            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL or "gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                stream=True,
                max_tokens=150,
            )
            async for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    yield token
        except ImportError:
            logger.error("openai package not installed. Run: pip install openai")
            yield "في مشكلة في الاتصال بـ OpenAI."


class AnthropicProvider(BaseLLMProvider):
    async def generate(self, prompt: str, context: list[str] | None = None) -> str:
        raise NotImplementedError("Anthropic provider not yet implemented.")

    async def generate_stream(self, prompt: str, context: list[str] | None = None) -> AsyncIterator[str]:
        raise NotImplementedError("Anthropic provider not yet implemented.")
        yield  # make it a generator
