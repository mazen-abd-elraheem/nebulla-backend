"""Mock LLM provider for testing RAG + LLM without external services."""

import asyncio
from typing import AsyncIterator
from app.providers.llm.base import BaseLLMProvider
from app.core.logger import get_logger

logger = get_logger(__name__)


class MockLLMProvider(BaseLLMProvider):
    """
    Mock LLM that simulates an LLM response incorporating RAG retrieved context.
    Ideal for unit/integration testing and API validation without external API keys or Ollama.
    """

    async def generate(
        self,
        prompt: str,
        context: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> str:
        chunks = []
        async for token in self.generate_stream(prompt, context, system_prompt):
            chunks.append(token)
        return "".join(chunks)

    async def generate_stream(
        self,
        prompt: str,
        context: list[str] | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[str]:
        if context and len(context) > 0:
            primary_memory = context[0]
            simulated_response = (
                f"أهلاً بك! بناءً على ما أتذكره، {primary_memory}. [happy]"
            )
        else:
            simulated_response = (
                f"أهلاً يا صديقي! استلمت سؤالك: '{prompt}'. أنا Nebula وجاهز لمساعدتك! [happy]"
            )

        words = simulated_response.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.01)
