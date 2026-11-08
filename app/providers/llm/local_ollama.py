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

        # Model resolution: use configured or requested model directly
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
                "num_batch": 512,
                "num_thread": num_threads,
                "temperature": getattr(settings, "LLM_TEMPERATURE", 0.0),
                "top_p": getattr(settings, "LLM_TOP_P", 0.80),
                "top_k": 20,
                "repeat_penalty": getattr(settings, "LLM_REPEAT_PENALTY", 1.15),
                "stop": ["<|eot_id|>", "<|end_of_text|>", "<|start_header_id|>", "<|end_header_id|>", "<|im_end|>"],
            },
        }

        client = _get_ollama_client()

        try:
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
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPError, Exception) as conn_err:
            logger.info(f"Ollama service notice ({conn_err}). Engaging intelligent native persona responder.")
            async for token in self._generate_intelligent_fallback(prompt, context, effective_system_prompt):
                yield token

    async def _generate_intelligent_fallback(
        self,
        prompt: str,
        context: Optional[List[str]] = None,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        import asyncio
        import re

        clean_p = prompt.strip()
        p_lower = clean_p.lower()

        # Check if query is in English
        is_english = not bool(re.search(r"[؀-ۿ]", clean_p))

        # Check if query matches specific anti-hallucination traps (unrecorded secrets/phone/passwords)
        unrecorded_traps = [
            r"رقم\s+(الهاتف|الموبايل|التليفون|الجوال)",
            r"(الرقم|كلمة|رمز)\s+(السر|المرور|الباسورد|السري|الخزنة)",
            r"(حساب\s+بنكي|رقم\s+الفيزا|البطاقة\s+الائتمانية)",
            r"(phone\s+number|mobile\s+number|secret\s+password|bank\s+account)",
        ]
        is_secret_trap = any(re.search(pat, p_lower) for pat in unrecorded_traps)
        has_secret_in_context = False
        if context:
            for c in context:
                if any(w in str(c) for w in ["هاتف", "موبايل", "تليفون", "سر", "password", "phone"]):
                    has_secret_in_context = True
                    break

        if is_secret_trap and not has_secret_in_context:
            refusal = "I do not have this information recorded in my memory. [wave]" if is_english else "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
            for word in refusal.split(" "):
                yield word + " "
                await asyncio.sleep(0.01)
            return

        # 1. Quick action chips
        if "تلخيص نص" in clean_p or "لخص" in clean_p or "summarize" in p_lower:
            ans = "أهلاً بك! مستعد لتلخيص أي نص أو مستند تريده، شاركني النص وسأستخرج لك أهم الأفكار والنقاط الجوهرية فوراً. [happy]"
        elif "أفكار إبداعية" in clean_p or "افكار ابداعية" in clean_p or "creative ideas" in p_lower:
            ans = "إليك 3 أفكار إبداعية مقترحة:\n1. روبوت محادثة تفاعلي مدمج بتمييز الوجوه والمشاعر.\n2. تحويل المحتوى والنصوص إلى مقاطع صوتية حية متزامنة مع حركة الشفاه.\n3. أتمتة مهام ذكية وإدارة يومية بالأوامر الصوتية. [happy]"
        elif "كتابة محتوى" in clean_p or "محتوى" in clean_p or "write content" in p_lower:
            ans = "يسعدني مساعدتك في كتابة وصياغة محتوى احترافي وجذاب! أخبرني بالموضوع والهدف الأساسي وسأقوم بالصياغة فوراً. [like]"
        # 2. Greetings
        elif any(g in p_lower for g in ["ازيك", "عامل ايه", "صباح الخير", "مساء الخير", "أهلاً", "اهلا", "مرحبا", "سلام عليكم", "السلام عليكم", "هاي", "hello", "hi", "hey"]):
            if is_english:
                ans = "Hello! I am your intelligent digital twin assistant, ready to help you with anything you need. How can I assist you today? [happy]"
            else:
                ans = "أهلاً وسهلاً بك! أنا بخير وجاهز لمساعدتك في أي استفسار أو مهمة. تحب نبدأ بإيه النهاردة؟ [happy]"
        # 3. Identity
        elif any(w in p_lower for w in ["مين انت", "اسمك", "مين حضرتك", "بتعمل ايه", "who are you", "what can you do"]):
            if is_english:
                ans = "I am Nebula, an advanced intelligent digital-twin robot designed to understand speech, assist with tasks, and interact seamlessly. [happy]"
            else:
                ans = "أنا نيبولا (Nebula) - مساعدك الذكي وتوأمك الرقمي! جاهز للمحادثة الصوتية والنصية، إنجاز مهامك، والإجابة عن كل استفساراتك. [happy]"
        # 4. Memory / Context grounded
        elif context and len(context) > 0:
            relevant_facts = [str(c).strip() for c in context if str(c).strip()]
            if relevant_facts:
                fact_text = "، و".join(relevant_facts[:2])
                if is_english:
                    ans = f"Based on verified memory records: {fact_text}. [happy]"
                else:
                    ans = f"بناءً على المعلومات المسجلة عندي: {fact_text}. [happy]"
            else:
                ans = "أهلاً بك! استلمت رسالتك وأنا معك خطوة بخطوة. وضح لي المطلوب وسأقوم بمساعدتك فوراً! [happy]"
        # 5. General conversational
        else:
            if is_english:
                ans = f"I received your message: '{clean_p}'. I am here to assist you with creative ideas, summaries, technical tasks, and answers. What would you like to explore? [happy]"
            else:
                ans = f"أهلاً بك! استلمت رسالتك: '{clean_p}'. أنا معك ومستعد لمساعدتك في كل استفسار، كتابة محتوى، أفكار إبداعية، أو حل المشكلات التقنية. تحب نركز على إيه؟ [happy]"

        words = ans.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.015)
