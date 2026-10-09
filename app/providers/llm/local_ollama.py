"""Local Ollama LLM provider — no internet needed (doc §11: works offline on local GPU)."""

import asyncio
from typing import AsyncIterator

import httpx

from app.providers.tts.base import BaseLLMProvider
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_SYSTEM_PROMPT = """أنت توأم رقمي مصري. بتتكلم بالمصري العامي وبتخلط إنجليزي زي أي مصري عادي.
ردودك قصيرة (جملة أو اتنين)، بشخصية حيوية وودودة.
لو الكلام فيه إشارة للمشاعر، ضيف علامة في آخر الجملة زي: [happy] [sad] [surprised] [like] [wave]
مثال: أهلاً يا صديقي! [happy] [wave]"""


class LocalOllamaProvider(BaseLLMProvider):
    """Streams responses from a local Ollama server (Llama 3, Qwen, etc.)."""

    async def generate(self, prompt: str, context: list[str] | None = None) -> str:
        chunks = []
        async for token in self.generate_stream(prompt, context):
            chunks.append(token)
        return "".join(chunks)

    async def generate_stream(
        self, prompt: str, context: list[str] | None = None
    ) -> AsyncIterator[str]:
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        if context:
            memories_text = "\n".join(f"- {m}" for m in context)
            messages.append({
                "role": "system",
                "content": f"ذكريات مرتبطة:\n{memories_text}",
            })
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": settings.LLM_MODEL,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.7, "num_predict": 150},
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.LLM_BASE_URL}/api/chat",
                    json=payload,
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line:
                            continue
                        import json
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
            logger.error(f"Cannot connect to Ollama at {settings.LLM_BASE_URL}. Is it running?")
            yield "معلش، في مشكلة في الاتصال. حاول تاني."
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            yield "في خطأ تقني. جرب تاني."
