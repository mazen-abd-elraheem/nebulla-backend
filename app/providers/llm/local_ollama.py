"""Local Ollama LLM provider — no internet needed (doc §11: works offline on local GPU)."""

import json
from typing import AsyncIterator, List, Dict, Optional

import httpx

from app.providers.llm.base import BaseLLMProvider, DEFAULT_SYSTEM_PROMPT
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class LocalOllamaProvider(BaseLLMProvider):
    """Streams responses from a local Ollama server (Llama 3, Qwen, etc.)."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or getattr(settings, "LLM_MODEL", "llama3")

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

        # Model resolution: fall back to llama3 if an OpenAI or Claude model name is configured
        model = self.model or getattr(settings, "LLM_MODEL", "llama3")
        if any(prefix in model.lower() for prefix in ("claude", "gpt-", "text-embedding")):
            model = "llama3"

        max_tokens = min(getattr(settings, "LLM_MAX_TOKENS", 30), 30)
        temperature = getattr(settings, "LLM_TEMPERATURE", 0.05)
        top_p = getattr(settings, "LLM_TOP_P", 0.85)
        repeat_penalty = getattr(settings, "LLM_REPEAT_PENALTY", 1.15)

        # Optimize for CPU physical cores (4 threads on i5 prevents thread thrashing)
        import os
        cpu_count = os.cpu_count() or 4
        optimal_threads = max(1, cpu_count // 2 if cpu_count > 2 else cpu_count)

        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": "24h",  # Keep model hot in RAM permanently, eliminates 50s cold load
            "options": {
                "temperature": temperature,
                "top_p": top_p,
                "repeat_penalty": repeat_penalty,
                "num_predict": max_tokens,
                "num_ctx": 1024,  # Compact KV cache saves CPU memory bandwidth & RAM
                "num_thread": optimal_threads,  # Matches 4 physical cores for max AVX2 throughput
                "num_batch": 256,  # Fast batch evaluation of input tokens
                "stop": [
                    "<|eot_id|>",
                    "<|end_of_text|>",
                    "<|im_end|>",
                    "<|endoftext|>",
                    "<|im_start|>",
                    "<start_of_turn>",
                    "<end_of_turn>",
                    "<eos>",
                ],
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
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
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
            logger.error(f"Ollama HTTP error {e.response.status_code}: {e.response.text}")
            yield f"في خطأ في تشغيل موديل {settings.LLM_MODEL} على Ollama."
        except Exception as e:
            logger.error(f"Ollama error: {e}")
            yield "في خطأ تقني في المعالجة. جرب تاني."
