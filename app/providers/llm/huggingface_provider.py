"""
Hugging Face LLM Provider — supports MBZUAI-Paris/Nile-Chat-3x4B-A6B and local/remote HF models.
Features real-time token streaming with TextIteratorStreamer.
"""

import asyncio
import re
import threading
from typing import AsyncIterator, List, Dict, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.llm.base import BaseLLMProvider, DEFAULT_SYSTEM_PROMPT

logger = get_logger(__name__)


class HuggingFaceProvider(BaseLLMProvider):
    """
    Hugging Face / Nile-Chat LLM Provider.
    Supports MBZUAI-Paris/Nile-Chat-3x4B-A6B and open-source models natively.
    """

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or getattr(settings, "HF_MODEL_NAME", "MBZUAI-Paris/Nile-Chat-3x4B-A6B")
        self._tokenizer = None
        self._model = None
        self._lock = asyncio.Lock()
        self._load_error = None

    def reset_client(self) -> None:
        self._model = None
        self._tokenizer = None
        self._load_error = None

    async def _ensure_loaded(self):
        if self._model is not None or self._load_error is not None:
            return
        async with self._lock:
            if self._model is None and self._load_error is None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._load_model_sync)

    def _load_model_sync(self):
        try:
            # Enforce strict model allowlist to prevent arbitrary remote code execution
            allowed_models = {"MBZUAI-Paris/Nile-Chat-3x4B-A6B"}
            configured = getattr(settings, "HF_MODEL_NAME", None)
            if configured:
                allowed_models.add(configured)

            if self.model_name not in allowed_models:
                raise ValueError(
                    f"Untrusted Hugging Face model repository '{self.model_name}'. "
                    f"Allowed models: {sorted(list(allowed_models))}"
                )

            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            logger.info(f"Loading Hugging Face model and tokenizer for: {self.model_name}")
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                token=settings.LLM_API_KEY or None,
            )
            if self._tokenizer.pad_token is None:
                self._tokenizer.pad_token = self._tokenizer.eos_token

            device_map = "auto" if torch.cuda.is_available() else "cpu"
            torch_dtype = torch.float16 if torch.cuda.is_available() else torch.float32

            self._model = AutoModelForCausalLM.from_pretrained(
                self.model_name,
                trust_remote_code=True,
                device_map=device_map,
                torch_dtype=torch_dtype,
                token=settings.LLM_API_KEY or None,
                low_cpu_mem_usage=True,
            )
            self._model.eval()
            logger.info(f"Successfully loaded HF model: {self.model_name} on {device_map}")
        except Exception as e:
            logger.error(f"Failed to load Hugging Face model {self.model_name}: {e}")
            self._load_error = str(e)

    def _format_messages(
        self,
        prompt: str,
        context: Optional[List[str]],
        system_prompt: Optional[str],
        history: Optional[List[Dict[str, str]]],
    ) -> List[Dict[str, str]]:
        effective_system = system_prompt or DEFAULT_SYSTEM_PROMPT

        if context:
            memories_text = "\n".join(f"- {m}" for m in context if m)
            already_in_prompt = any(kw in effective_system for kw in ("ذكريات", "الذاكرة", "RAG Context", "Verified Context"))
            if memories_text.strip() and not already_in_prompt:
                effective_system += f"\n\nمعلومات الذاكرة المعتمدة:\n{memories_text}"

        messages: List[Dict[str, str]] = [{"role": "system", "content": effective_system}]

        if history:
            for msg in history:
                role = "assistant" if msg.get("role") in ("robot", "assistant") else "user"
                content = msg.get("content", "")
                if content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": prompt})
        return messages

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
        await self._ensure_loaded()

        if self._load_error or self._model is None:
            # Fall back to local Ollama if HF weights not downloaded locally
            logger.warning(f"HF Model not available locally ({self._load_error}). Forwarding to Ollama...")
            from app.providers.llm.local_ollama import LocalOllamaProvider
            provider = LocalOllamaProvider()
            async for tok in provider.generate_stream(prompt, context, system_prompt, history):
                yield tok
            return

        from transformers import TextIteratorStreamer
        import torch

        messages = self._format_messages(prompt, context, system_prompt, history)

        try:
            input_text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
            inputs = self._tokenizer(input_text, return_tensors="pt")
            device = next(self._model.parameters()).device
            inputs = {k: v.to(device) for k, v in inputs.items()}

            streamer = TextIteratorStreamer(
                self._tokenizer,
                skip_prompt=True,
                skip_special_tokens=True,
            )

            max_tokens = min(getattr(settings, "LLM_MAX_TOKENS", 70), 90)
            temperature = getattr(settings, "LLM_TEMPERATURE", 0.05)
            top_p = getattr(settings, "LLM_TOP_P", 0.85)

            gen_kwargs = dict(
                **inputs,
                streamer=streamer,
                max_new_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                do_sample=temperature > 0.0,
            )

            thread = threading.Thread(target=self._model.generate, kwargs=gen_kwargs)
            thread.start()

            loop = asyncio.get_event_loop()
            while thread.is_alive() or not streamer.text_queue.empty():
                token = await loop.run_in_executor(None, streamer.text_queue.get)
                if token:
                    cleaned = re.sub(r"[\u4e00-\u9fff]", "", token)
                    if cleaned:
                        yield cleaned

        except Exception as e:
            logger.error(f"Error during Hugging Face generation: {e}")
            yield "حصل خطأ في معالجة الموديل. جرب مرة تانية."
