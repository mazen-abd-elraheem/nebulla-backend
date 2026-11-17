"""
Chat Memory Extractor & Ingestion Engine.

Solves the Conversational Memory Problem:
- Detects explicit and conversational memory storage requests in chat (Arabic & English).
- Extracts clean, normalized facts without filler words or conversational markers.
- Bridges the chat endpoint directly to RAG VectorStore and long-term memory.
"""

import re
from typing import Optional, Tuple


class ChatMemoryExtractor:
    """
    Detects when a user asks to remember, save, or store information in chat.
    Extracts the core factual knowledge and generates a grounded response.
    """

    # Primary prefix patterns for explicit memory instructions
    # Matches patterns like: "احفظ عندك ان ...", "افتكر ان ...", "سجل عندك ان ...", "remember that ..."
    TRIGGER_PATTERNS = [
        # 1. احفظ / إحفظ
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:احفظ|إحفظ)(?:\s+(?:عندك|معاك))?(?:\s+(?:في\s+الذاكرة|في\s+ذاكرتك))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
            re.IGNORECASE,
        ),
        # 2. افتكر / إفتكر / خليك فاكر / متنساش
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:افتكر|إفتكر|خليك\s+فاكر|متنساش|ماتنساش|اوعى\s+تنسى|إوعى\s+تنسى)(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
            re.IGNORECASE,
        ),
        # 3. سجل / خزن
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:سجل|خزن)(?:\s+(?:عندك|معاك))?(?:\s+(?:في\s+الذاكرة|في\s+ذاكرتك))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
            re.IGNORECASE,
        ),
        # 4. ضيف للذاكرة / حط في الذاكرة
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:ضيف|حط)(?:\s+(?:في|إلى|الي)\s+الذاكرة)?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
            re.IGNORECASE,
        ),
        # 5. معلومة ليك: / معلومة جديدة: / معلومة عن فلان:
        re.compile(
            r"^(?:معلومة|معلومه)(?:\s+(?:جديدة|جديده|مهمة|مهمه|عني|عن\s+[\w\s]+))?\s*[:\-]\s*(.+)$",
            re.IGNORECASE,
        ),
        # 6. English: Remember that / Save that / Store that / Note that
        re.compile(
            r"^(?:please\s+)?(?:could\s+you\s+)?(?:remember|save|store|record|note|keep\s+in\s+mind)(?:\s+(?:that|this))?\s*[:\-]?\s+(.+)$",
            re.IGNORECASE,
        ),
    ]

    # Filler prefixes to strip from beginning of extracted fact
    CLEANUP_PREFIXES = [
        re.compile(r"^(?:إن|ان|أن|بأن|انو|انه|إنو|إنه)\s+", re.IGNORECASE),
        re.compile(r"^(?:هو|هي|هما|هم)\s+", re.IGNORECASE),
    ]

    @classmethod
    def extract_fact(
        cls,
        message: str,
        user_name: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """
        Analyzes the message. If it is an explicit command to save a memory, returns:
            (clean_fact, confirmation_reply)
        Otherwise returns None.
        """
        if not message or not message.strip():
            return None

        clean_msg = message.strip()

        # Reject pure questions even if they contain keywords
        # e.g., "أنت فاكر إن أحمد دكتور؟" or "هل أنت حافظ إن...؟"
        question_marks = ("؟", "?")
        if clean_msg.endswith(question_marks) and any(clean_msg.startswith(q) for q in ["هل", "هو", "انت", "أنت", "فاكر", "حافظ"]):
            return None

        matched_raw_fact: Optional[str] = None
        for pattern in cls.TRIGGER_PATTERNS:
            m = pattern.match(clean_msg)
            if m:
                matched_raw_fact = m.group(1).strip()
                break

        if not matched_raw_fact:
            return None

        # Clean punctuation and quotes from the extracted fact
        fact = matched_raw_fact.strip(" '\"`()[]{}،,.:;-~؟!?")
        for pref in cls.CLEANUP_PREFIXES:
            fact = pref.sub("", fact).strip()

        # Check for 1st-person pronouns and normalize
        # e.g. "اني شغال دكتور" -> "المستخدم شغال دكتور"
        actor = user_name.strip() if user_name and user_name.strip() else "المستخدم"

        # "اني / إني" at start
        fact = re.sub(r"^(?:إني|اني)\s+", f"{actor} ", fact, flags=re.IGNORECASE)
        # "أنا / انا" at start
        fact = re.sub(r"^(?:أنا|انا)\s+", f"{actor} ", fact, flags=re.IGNORECASE)

        if not fact or len(fact) < 3:
            return None

        # Format pleasant confirmation reply in Masri
        confirmation = f"تمام، حفظت في الذاكرة: {fact}. [eyes:happy] [nod]"

        return fact, confirmation
