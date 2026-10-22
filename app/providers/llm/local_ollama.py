"""Local Ollama LLM provider — no internet needed (doc §11: works offline on local GPU)."""

import asyncio
import json
from typing import AsyncIterator

import httpx

from app.providers.llm.base import BaseLLMProvider
from app.providers.llm.prompt_builder import build_rag_messages
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class LocalOllamaProvider(BaseLLMProvider):
    """Streams responses from a local Ollama server (Llama 3, Qwen, etc.)."""

    async def generate(
        self,
        prompt: str,
        context: list[str] | list[dict] | None = None,
        system_prompt: str | None = None,
        **kwargs,
    ) -> str:
        chunks = []
        async for token in self.generate_stream(prompt, context, system_prompt, **kwargs):
            chunks.append(token)
        return "".join(chunks)

    async def generate_stream(
        self,
        prompt: str,
        context: list[str] | list[dict] | None = None,
        system_prompt: str | None = None,
        **kwargs,
    ) -> AsyncIterator[str]:
        messages = build_rag_messages(
            prompt=prompt,
            context=context,
            system_prompt=system_prompt,
            **kwargs,
        )

        max_tokens = getattr(settings, "TTS_MAX_NEW_TOKENS", 150) or 150
        payload = {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.7, "num_predict": max_tokens},
        }

        base_url = settings.LLM_BASE_URL.rstrip("/")
        try:
            timeout = httpx.Timeout(180.0, connect=10.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/api/chat",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            logger.error(f"Cannot connect to Ollama at {base_url}. Is it running? (Run: ollama serve)")
            yield "معلش، في مشكلة في الاتصال بـ Ollama. تأكد من تشغيل السيرفر."
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Ollama returned HTTP {e.response.status_code}. "
                f"Make sure model '{settings.LLM_MODEL}' is downloaded (run: ollama pull {settings.LLM_MODEL})"
            )
            yield f"في مشكلة في موديل Ollama ({settings.LLM_MODEL})."
        except Exception as e:
            logger.error(f"Ollama unexpected error: {e}")
            yield "في خطأ تقني في استدعاء الموديل المحلي. جرب تاني."
