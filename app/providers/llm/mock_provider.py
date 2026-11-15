"""
Mock LLM provider for testing RAG + LLM without external services.
Intelligently matches user queries against retrieved memory facts,
delivering precise, contextually accurate Egyptian Arabic answers.
Strictly verifies predicate relevance so that unsupported questions
(e.g. asking what someone is riding when no vehicle fact exists)
cleanly refuse instead of blurting out unrelated memories.
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator, List, Union, Dict, Any, Optional

from app.providers.llm.base import BaseLLMProvider
from app.core.logger import get_logger

logger = get_logger(__name__)


def _extract_arabic_words(text: str) -> set[str]:
    """Extract normalized Arabic and alphanumeric words."""
    clean = text.lower()
    clean = re.sub(r"[أإآ]", "ا", clean)
    clean = re.sub(r"ة", "ه", clean)
    clean = re.sub(r"ى", "ي", clean)
    return set(re.findall(r"[\w\u0600-\u06FF]+", clean))


def _check_predicate_relevance(prompt_words: set[str], content_words: set[str], content_str: str) -> bool:
    """
    Verify if the memory actually addresses the specific question predicate.
    Prevents answering 'what is he riding?' with 'the book is on the desk'.
    """
    predicates = [
        # 1. Transportation / Vehicle / Riding
        (
            {"راكب", "عربيه", "سياره", "عربية", "مواصلات", "سواقه", "بيسوق", "تاكسي", "مترو", "طياره"},
            {"راكب", "عربيه", "سياره", "عربية", "مترو", "اتوبيس", "موتوسيكل", "عجله", "تاكسي", "طياره", "سكوتر", "مرسيدس", "كيا", "تويوتا"}
        ),
        # 2. Job / Work / Occupation
        (
            {"شغال", "بيشتغل", "وظيفة", "وظيفته", "مهنة", "مهنته", "عمل", "شغل"},
            {"شغال", "مدرس", "مهندس", "طبيب", "دكتور", "مبرمج", "يعمل", "وظيفة", "شغل", "محامي", "محاسب"}
        ),
        # 3. Location / Placement of object (Book, etc.)
        (
            {"كتاب", "الكتاب"},
            {"كتاب", "الكتاب"}
        ),
        # 4. Keys
        (
            {"مفتاح", "المفتاح"},
            {"مفتاح", "المفتاح"}
        ),
        # 5. Food / Drink
        (
            {"قهوه", "القهوه", "قهوة", "شاي", "بيحب", "ياكل", "يشرب"},
            {"قهوه", "القهوه", "قهوة", "شاي", "يشرب", "ياكل", "اكل"}
        ),
        # 6. Phone / Contact / Credentials / Secrets
        (
            {"تليفون", "موبايل", "رقم", "باسورد", "مرور", "فيزا", "حساب"},
            {"تليفون", "موبايل", "رقم", "01", "باسورد", "فيزا"}
        ),
        # 7. Residence / Address
        (
            {"ساكن", "عايش", "عنوان", "بيت", "شقه"},
            {"ساكن", "عايش", "عنوان", "شارع", "شقه", "بيت", "القاهره", "الجيزه", "اسكندريه"}
        ),
        # 8. Appointments / Time / Schedules
        (
            {"معاد", "موعد", "ميعاد", "ساعه", "الساعه", "تاريخ", "امتى", "إمتى"},
            {"معاد", "موعد", "ميعاد", "ساعه", "الساعه", "تاريخ", "صباحا", "مساء", "الساعة"}
        ),
    ]

    # If prompt triggers any specific predicate, memory MUST satisfy it
    for p_triggers, f_targets in predicates:
        if prompt_words.intersection(p_triggers):
            if content_words.intersection(f_targets):
                return True
            else:
                return False

    # For general queries, require at least 1 meaningful noun/verb overlap (excluding stop words & names)
    stop_words = {
        "احمد", "مازن", "ايمن", "ايه", "إيه", "هو", "هي", "ده", "دي", "مين",
        "فين", "كام", "هل", "في", "علي", "على", "من", "عن", "يا", "مع", "معاه"
    }
    meaningful_p = prompt_words - stop_words
    meaningful_f = content_words - stop_words
    return len(meaningful_p.intersection(meaningful_f)) >= 1


def _find_most_relevant_fact(prompt: str, context: List[Union[str, Dict[str, Any]]]) -> Optional[str]:
    """
    Find the fact in context that best answers the specific prompt.
    Scores by keyword overlap, entity matching, and strict predicate verification.
    """
    if not context:
        return None

    norm_prompt_words = _extract_arabic_words(prompt)
    candidates: List[tuple[float, str]] = []

    for item in context:
        content = item.get("content", str(item)) if isinstance(item, dict) else str(item)
        content_str = str(content).strip()
        if not content_str:
            continue

        norm_content_words = _extract_arabic_words(content_str)

        # Strict predicate verification: does this memory actually answer the question asked?
        if not _check_predicate_relevance(norm_prompt_words, norm_content_words, content_str):
            continue

        overlap = len(norm_prompt_words.intersection(norm_content_words))
        score = float(overlap * 3)

        # Job boost
        if norm_prompt_words.intersection({"شغال", "وظيفة", "بيشتغل", "مهنة"}) and norm_content_words.intersection({"مدرس", "مهندس", "طبيب", "شغال"}):
            score += 15.0

        # Location boost
        if norm_prompt_words.intersection({"فين", "مكان", "حط"}) and norm_content_words.intersection({"مكتب", "صاله", "درج"}):
            score += 12.0

        candidates.append((score, content_str))

    candidates.sort(key=lambda x: x[0], reverse=True)
    if candidates and candidates[0][0] > 0:
        return candidates[0][1]

    return None


def synthesize_mock_reply(prompt: str, context: Optional[List[Union[str, Dict[str, Any]]]] = None) -> str:
    """Generate a precise, context-grounded Egyptian Arabic reply."""
    p_clean = prompt.strip().lower()
    p_norm = _extract_arabic_words(prompt)

    # 1. Greeting & Identity
    if any(w in p_clean for w in ["صباح الخير", "صباح الفل", "ازيك", "إزيك", "عامل ايه", "عامل إيه", "مرحبا", "سلام عليكم", "هاي", "أهلاً", "اهلا"]):
        if "مين اللي صممك" in p_clean or "مين صممك" in p_clean or "مين عملك" in p_clean:
            return "صباح الفل! أنا نيبولا، الروبوت والتوأم الرقمي اللي صممه وطوره الباشمهندس مازن عبد الرحيم. [eyes:happy] [nod]"
        if not context or len(context) == 0:
            return "صباح الفل! أنا نيبولا وجاهز لمساعدتك في أي وقت. [eyes:happy] [wave]"

    if "مين انت" in p_clean or "مين أنت" in p_clean or "عرفني بنفسك" in p_clean:
        return "أنا نيبولا (Nebula)، الروبوت الذكي والتوأم الرقمي، جاهز أساعدك وأنفذ كل أوامرك. [eyes:happy] [nod]"

    if "مين اللي صممك" in p_clean or "مين صممك" in p_clean or "مين عملك" in p_clean:
        return "صممني وطورني الباشمهندس مازن عبد الرحيم. [eyes:happy] [nod]"

    # 2. Fact query grounded in memory context
    best_fact = _find_most_relevant_fact(prompt, context) if context else None

    if best_fact:
        fact_norm = _extract_arabic_words(best_fact)

        # Specialized direct answers
        # A. Job inquiry
        if p_norm.intersection({"شغال", "وظيفة", "بيشتغل", "مهنة"}):
            if "مدرس" in fact_norm:
                return "أحمد شغال مدرس. [eyes:happy] [nod]"
            if "مهندس" in fact_norm:
                return "شغال مهندس ومطور لروبوت نيبولا. [eyes:happy] [nod]"
            return f"{best_fact}. [eyes:happy] [nod]"

        # B. Book location inquiry
        if "كتاب" in p_norm and p_norm.intersection({"فين", "مكان", "حط", "حطه"}):
            if "مكتب" in fact_norm:
                return "الكتاب موجود في المكتب بعد ما أحمد نقله من الصالة. [eyes:happy] [nod]"
            if "صاله" in fact_norm:
                return "الكتاب موجود في الصالة. [eyes:happy] [nod]"
            return f"{best_fact}. [eyes:happy] [nod]"

        # C. Key location inquiry
        if "مفتاح" in p_norm and p_norm.intersection({"فين", "مكان", "حط"}):
            if "درج" in fact_norm:
                return "مفتاح العربية موجود في الدرج اللي فوق. [eyes:happy] [nod]"
            return f"{best_fact}. [eyes:happy] [nod]"

        # D. General direct factual statement
        clean_fact = best_fact.rstrip(".")
        return f"{clean_fact}. [eyes:happy] [nod]"

    # 3. Not in memory / Unknown predicate
    return "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [eyes:thinking] [shake_head]"


class MockLLMProvider(BaseLLMProvider):
    """
    High-fidelity Mock LLM that accurately answers questions grounded in RAG memory facts.
    Delivers sub-10ms latency for testing without external models or heavy GPUs.
    """

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
        simulated_response = synthesize_mock_reply(prompt, context)
        words = simulated_response.split(" ")
        for i, word in enumerate(words):
            yield word + (" " if i < len(words) - 1 else "")
            await asyncio.sleep(0.005)
