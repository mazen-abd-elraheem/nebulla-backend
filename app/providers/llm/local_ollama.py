"""Local Ollama LLM provider — no internet needed (doc §11: works offline on local GPU)."""

import os
import json
from typing import AsyncIterator, List, Dict, Optional

import httpx

from app.providers.llm.base import BaseLLMProvider, DEFAULT_SYSTEM_PROMPT
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

_ollama_client: Optional[httpx.AsyncClient] = None


def _get_ollama_client() -> httpx.AsyncClient:
    global _ollama_client
    if _ollama_client is None or _ollama_client.is_closed:
        timeout = httpx.Timeout(getattr(settings, "LLM_TIMEOUT", 120.0), connect=15.0)
        _ollama_client = httpx.AsyncClient(timeout=timeout)
    return _ollama_client


class LocalOllamaProvider(BaseLLMProvider):
    """Streams responses from a local Ollama server (nebula-rag, llama3, qwen, etc.)."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or getattr(settings, "LLM_MODEL", "nebula-rag")

    async def generate(
        self,
        prompt: str,
        context: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        chunks = []
        async for token in self.generate_stream(prompt, context, system_prompt, history):
            chunks.append(token)
        return "".join(chunks)

    async def generate_stream(
        self,
        prompt: str,
        context: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> AsyncIterator[str]:
        effective_system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        messages: List[Dict[str, str]] = [{"role": "system", "content": effective_system_prompt}]

        if context:
            memories_text = "\n".join(f"- {m}" for m in context if m)
            already_in_prompt = any(kw in effective_system_prompt for kw in ("ذكريات", "الذاكرة", "RAG Context", "Verified Context"))
            if memories_text.strip() and not already_in_prompt:
                messages.append({
                    "role": "system",
                    "content": f"ذكريات مرتبطة:\n{memories_text}",
                })

        # Append multi-turn conversation history
        if history:
            for msg in history:
                role = "assistant" if msg.get("role") in ("robot", "assistant") else "user"
                content = msg.get("content", "")
                if content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": prompt})

        # Model resolution: use configured or requested model directly without fallback
        model = self.model or getattr(settings, "LLM_MODEL", "nebula-rag")

        max_tokens = min(getattr(settings, "LLM_MAX_TOKENS", 45) or 45, 60)
        num_threads = min(os.cpu_count() or 8, 8)

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": "24h",
            "options": {
                "num_predict": max_tokens,
                "num_ctx": 1024,
                "num_batch": 256,
                "num_thread": num_threads,
                "temperature": getattr(settings, "LLM_TEMPERATURE", 0.0),
                "top_p": getattr(settings, "LLM_TOP_P", 0.85),
                "top_k": 30,
                "repeat_penalty": getattr(settings, "LLM_REPEAT_PENALTY", 1.15),
            },
        }

        timeout = httpx.Timeout(getattr(settings, "LLM_TIMEOUT", 120.0), connect=15.0)

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    f"{settings.LLM_BASE_URL}/api/chat",
                    json=payload,
                ) as resp:
                    status_code = getattr(resp, "status_code", 200)
                    if isinstance(status_code, int) and status_code >= 400:
                        err_bytes = await resp.aread()
                        err_text = err_bytes.decode("utf-8", errors="replace")
                        logger.error(f"Ollama HTTP error {resp.status_code}: {err_text}")
                        if resp.status_code == 404:
                            yield f"الموديل '{model}' غير موجود على خادم Ollama. يرجى التأكد من تثبيت الموديل المطلوب."
                        else:
                            yield f"في خطأ في تشغيل موديل {model} على Ollama."
                        return

                    stream_iter = resp.aiter_lines()
                    import asyncio
                    if asyncio.iscoroutine(stream_iter):
                        stream_iter = await stream_iter

                    async for line in stream_iter:
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            token = data.get("message", {}).get("content", "")
                            if token:
                                import re
                                token = re.sub(r"[\u4e00-\u9fff]", "", token)
                                if token:
                                    yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            logger.error(f"Cannot connect to Ollama at {settings.LLM_BASE_URL}. Is it running?")
            yield "معلش، في مشكلة في الاتصال بـ Ollama. اتأكد إن البرنامج شغال."
        except httpx.TimeoutException:
            logger.error(f"Ollama request timed out after {getattr(settings, 'LLM_TIMEOUT', 120.0)}s")
            yield "استغرق الموديل وقتاً أطول من المعتاد في المعالجة. جرب تاني أو اتأكد من كفاءة الجهاز."
        except httpx.HTTPStatusError as e:
            try:
                err_text = (await e.response.aread()).decode("utf-8", errors="replace")
            except Exception:
                err_text = str(e)
            logger.error(f"Ollama HTTP error {e.response.status_code}: {err_text}")
            if e.response.status_code == 404:
                yield f"الموديل '{model}' غير موجود على خادم Ollama. يرجى التأكد من تثبيت الموديل المطلوب."
                return
            yield f"في خطأ في تشغيل موديل {model} على Ollama."
        except httpx.ResponseNotRead as e:
            logger.error(f"Ollama streaming response read error: {e}")
            yield f"في خطأ في قراءة استجابة موديل {model} على Ollama."
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            yield "في خطأ تقني في المعالجة. جرب تاني."
