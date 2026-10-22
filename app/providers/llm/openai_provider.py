"""OpenAI API LLM provider."""

from typing import AsyncIterator
from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.prompt_builder import build_rag_messages
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class OpenAIProvider(BaseLLMProvider):
    async def generate(
        self,
        prompt: str,
        context: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        chunks = []
        async for t in self.generate_stream(prompt, context, system_prompt):
            chunks.append(t)
        return "".join(chunks)

    async def generate_stream(
        self,
        prompt: str,
        context: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        try:
            from openai import AsyncOpenAI  # type: ignore[import]
            client = AsyncOpenAI(api_key=settings.LLM_API_KEY)
            messages = build_rag_messages(
                prompt=prompt,
                context=context,
                system_prompt=system_prompt,
            )
            stream = await client.chat.completions.create(
                model=settings.LLM_MODEL or "gpt-4o-mini",
                messages=messages,
                stream=True,
                max_tokens=settings.TTS_MAX_NEW_TOKENS or 150,
            )
            async for chunk in stream:
                token = chunk.choices[0].delta.content or ""
                if token:
                    yield token
        except ImportError:
            logger.error("openai package not installed. Run: pip install openai")
            yield "في مشكلة في الاتصال بـ OpenAI. تأكد من تثبيت مكتبة openai."
        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            yield f"معلش، حصل خطأ في التواصل مع OpenAI: {str(e)}"


class AnthropicProvider(BaseLLMProvider):
    async def generate(
        self,
        prompt: str,
        context: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        chunks = []
        async for t in self.generate_stream(prompt, context, system_prompt):
            chunks.append(t)
        return "".join(chunks)

    async def generate_stream(
        self,
        prompt: str,
        context: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        try:
            from anthropic import AsyncAnthropic  # type: ignore[import]
            from app.providers.llm.prompt_builder import build_rag_system_prompt
            client = AsyncAnthropic(api_key=settings.LLM_API_KEY)
            sys_prompt = build_rag_system_prompt(context=context, system_prompt=system_prompt)
            async with client.messages.stream(
                model=settings.LLM_MODEL or "claude-3-5-sonnet-20241022",
                max_tokens=settings.TTS_MAX_NEW_TOKENS or 150,
                system=sys_prompt,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for text in stream.text_stream:
                    yield text
        except ImportError:
            logger.error("anthropic package not installed. Run: pip install anthropic")
            yield "في مشكلة في الاتصال بـ Anthropic. تأكد من تثبيت مكتبة anthropic."
        except Exception as e:
            logger.error(f"Anthropic error: {e}")
            yield f"معلش، حصل خطأ في التواصل مع Anthropic: {str(e)}"
