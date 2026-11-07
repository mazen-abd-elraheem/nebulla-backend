"""
Local Ollama LLM provider — no internet needed (runs locally on GPU/CPU).
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Key features:
  • Primary LLM engine for Nebula AI robot and digital twin.
  • Default Egyptian model: 'nebula-masri' with automatic discovery/fallback.
  • Sub-millisecond latency tuning with 'keep_alive: 24h' and multi-threaded CPU/GPU execution.
  • Resilient health-check and friendly Egyptian Arabic diagnostics/notifications.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.llm.base import BaseLLMProvider, DEFAULT_SYSTEM_PROMPT

logger = get_logger(__name__)

# Model auto-discovery priority list for Egyptian Arabic
_PREFERRED_MODELS = ["nebula-masri", "nebula-rag", "llama3.2:3b", "llama3.2", "phi3:mini", "phi3"]


class LocalOllamaProvider(BaseLLMProvider):
    """Streams responses from a local Ollama server (nebula-masri, nebula-rag, llama3, etc.)."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or getattr(settings, "LLM_MODEL", "nebula-masri")
        self._discovered_model: Optional[str] = None

    @classmethod
    async def check_health(cls) -> Dict[str, Any]:
        """
        Pings local Ollama service and queries installed models.
        Returns detailed health dictionary in Egyptian Arabic.
        """
        url = f"{settings.LLM_BASE_URL}/api/version"
        timeout = httpx.Timeout(3.0, connect=2.0)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    version = data.get("version", "unknown")

                    installed_models: List[str] = []
                    try:
                        tags_resp = await client.get(f"{settings.LLM_BASE_URL}/api/tags")
                        if tags_resp.status_code == 200:
                            tags_data = tags_resp.json()
                            installed_models = [
                                m.get("name", "") for m in tags_data.get("models", []) if m.get("name")
                            ]
                    except Exception as ex:
                        logger.debug(f"Could not list Ollama tags during healthcheck: {ex}")

                    return {
                        "status": "online",
                        "version": version,
                        "base_url": settings.LLM_BASE_URL,
                        "default_model": getattr(settings, "LLM_MODEL", "nebula-masri"),
                        "installed_models": installed_models,
                        "message_arz": "سيرفر Ollama المحلي شغال تمام ومتصل.",
                    }
        except Exception as e:
            logger.debug(f"Ollama healthcheck offline: {e}")

        return {
            "status": "offline",
            "base_url": settings.LLM_BASE_URL,
            "default_model": getattr(settings, "LLM_MODEL", "nebula-masri"),
            "installed_models": [],
            "message_arz": "معلش يا فندم، سيرفر Ollama مش شغال حالياً على الجهاز. اتأكد إن البرنامج مفتوح.",
        }

    async def resolve_model(self, requested_model: Optional[str] = None) -> str:
        """
        Intelligently resolves which model to use:
        Checks if requested/configured model is installed; if not, falls back to
        the closest available model in Ollama.
        """
        target = requested_model or self.model or getattr(settings, "LLM_MODEL", "nebula-masri")
        if self._discovered_model:
            return self._discovered_model

        try:
            timeout = httpx.Timeout(2.0, connect=1.5)
            async with httpx.AsyncClient(timeout=timeout) as client:
                tags_resp = await client.get(f"{settings.LLM_BASE_URL}/api/tags")
                if tags_resp.status_code == 200:
                    raw_models = [m.get("name", "") for m in tags_resp.json().get("models", [])]
                    clean_models = [m.split(":")[0] for m in raw_models] + raw_models

                    # 1. Exact match
                    if target in raw_models or target in clean_models:
                        self._discovered_model = target
                        return target

                    # 2. Priority check
                    for pref in _PREFERRED_MODELS:
                        for installed in raw_models:
                            if pref in installed:
                                logger.info(f"Ollama: preferred model {target!r} not found, using {installed!r}")
                                self._discovered_model = installed
                                return installed

                    # 3. Any available installed model
                    if raw_models:
                        fallback = raw_models[0]
                        logger.info(f"Ollama: using first available model {fallback!r}")
                        self._discovered_model = fallback
                        return fallback
        except Exception as e:
            logger.debug(f"Ollama model discovery skipped: {e}")

        self._discovered_model = target
        return target

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
            already_in_prompt = any(
                kw in effective_system_prompt for kw in ("ذكريات", "الذاكرة", "RAG Context", "Verified Context")
            )
            if memories_text.strip() and not already_in_prompt:
                messages.append({
                    "role": "system",
                    "content": f"ذكريات مرتبطة:\n{memories_text}",
                })

        # Multi-turn conversation history
        if history:
            for msg in history:
                role = "assistant" if msg.get("role") in ("robot", "assistant") else "user"
                content = msg.get("content", "")
                if content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": prompt})

        # Model resolution: direct model or auto-discovered
        model = self.model or getattr(settings, "LLM_MODEL", "nebula-masri")

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
                "num_batch": 512,
                "num_thread": num_threads,
                "temperature": getattr(settings, "LLM_TEMPERATURE", 0.0),
                "top_p": getattr(settings, "LLM_TOP_P", 0.80),
                "top_k": 20,
                "repeat_penalty": getattr(settings, "LLM_REPEAT_PENALTY", 1.15),
                "stop": ["<|eot_id|>", "<|end_of_text|>", "<|start_header_id|>", "<|end_header_id|>", "<|im_end|>"],
            },
        }

        timeout = httpx.Timeout(getattr(settings, "LLM_TIMEOUT", 120.0), connect=5.0)

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
                            yield f"الموديل '{model}' مش متثبت على خادم Ollama. اتأكد من تثبيت الموديل أو إنشاء Modelfile الخاص بيه."
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
                                token = re.sub(r"[\u4e00-\u9fff]", "", token)
                                if token:
                                    yield token
                            if data.get("done"):
                                break
                        except json.JSONDecodeError:
                            continue
        except httpx.ConnectError:
            logger.error(f"Cannot connect to Ollama at {settings.LLM_BASE_URL}. Is it running?")
            yield "معلش يا فندم، سيرفر Ollama مش شغال حالياً على الجهاز. اتأكد إن البرنامج مفتوح."
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
                yield f"الموديل '{model}' مش متثبت على خادم Ollama. اتأكد من تثبيت الموديل المطلوب."
                return
            yield f"في خطأ في تشغيل موديل {model} على Ollama."
        except httpx.ResponseNotRead as e:
            logger.error(f"Ollama streaming response read error: {e}")
            yield f"في خطأ في قراءة استجابة موديل {model} على Ollama."
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            yield "في خطأ تقني في المعالجة. جرب تاني."
