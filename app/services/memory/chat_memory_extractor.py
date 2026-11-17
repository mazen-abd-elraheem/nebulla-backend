"""
Chat Memory Extractor & Ingestion Engine.

Solves the Conversational Memory Problem:
- Detects explicit and conversational memory storage, update, and deletion requests in chat (Arabic & English).
- Extracts clean, normalized facts without filler words or conversational markers.
- Classifies scope into Shared (personality_id = None) for general household/real-world facts vs Persona-specific.
- Bridges the chat endpoint directly to RAG VectorStore and long-term memory.
"""

import re
from typing import Optional, Tuple, Dict, Any

from app.utils.masri_normalizer import normalize_masri_orthography


class ChatMemoryExtractor:
    """
    Detects when a user asks to remember, save, update, or delete information in chat.
    Extracts the core factual knowledge, target entities, and generates grounded responses.
    """

    DELETE_PATTERNS = [
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:امسح|إمسح|احذف|إحذف|شيل)(?:\s+(?:من\s+الذاكرة|من\s+ذاكرتك))?(?:\s+(?:معلومة|معلومه|حاجة|حاجه))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:انسى|إنسى|متفتكرش|ماتفتكرش|اوعى\s+تفتكر|إوعى\s+تفتكر)(?:\s+(?:معلومة|معلومه))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:please\s+)?(?:could\s+you\s+)?(?:delete|remove|forget|erase)(?:\s+(?:from\s+memory))?(?:\s+(?:that|the\s+memory\s+about))?\s*[:\-]?\s+(.+)$",
            re.IGNORECASE,
        ),
    ]

    UPDATE_PATTERNS = [
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:عدل|صلح|غير|بدل|حدث|حدّث)(?:\s+(?:عندك|معاك))?(?:\s+(?:في\s+الذاكرة|في\s+ذاكرتك))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s*[:\-]?\s*(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:please\s+)?(?:could\s+you\s+)?(?:update|correct|change|modify)(?:\s+(?:in\s+memory))?\s*[:\-]?\s+(.+)$",
            re.IGNORECASE,
        ),
    ]

    SAVE_PATTERNS = [
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:احفظ|إحفظ)(?:\s+(?:عندك|معاك|(?:عند|مع|لـ)\s+(?:احمد|مازن|توت|نيبولا)))?(?:\s+(?:في\s+الذاكرة|في\s+ذاكرتك))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:افتكر|إفتكر|خليك\s+فاكر|متنساش|ماتنساش|اوعى\s+تنسى|إوعى\s+تنسى)(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:سجل|خزن)(?:\s+(?:عندك|معاك|(?:عند|مع|لـ)\s+(?:احمد|مازن|توت|نيبولا)))?(?:\s+(?:في\s+الذاكرة|في\s+ذاكرتك))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:ضيف|حط)(?:\s+(?:في|إلى|الي)\s+الذاكرة)?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:معلومة|معلومه)(?:\s+(?:جديدة|جديده|مهمة|مهمه|عني|عن\s+[\w\s]+))?\s*[:\-]\s*(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:please\s+)?(?:could\s+you\s+)?(?:remember|save|store|record|note|keep\s+in\s+mind)(?:\s+(?:that|this))?\s*[:\-]?\s+(.+)$",
            re.IGNORECASE,
        ),
    ]

    CLEANUP_PREFIXES = [
        re.compile(r"^(?:عند|في\s+ذاكرة|مع|لـ)\s+(?:احمد|مازن|توت|نيبولا)\s*(?:ان|إن|أن|انو|انه|بأن)?\s*", re.IGNORECASE),
        re.compile(r"^(?:في\s+ذاكرتك\s+بس|عندك\s+انت\s+بس|عندك\s+بس|بيني\s+وبينك\s+بس|بيني\s+وبينك|في\s+سرك|خاصة\s+بيك\s+انت\s+بس|خاصة\s+بيك\s+بس|خاصة\s+بيك)\s+(?:ان|إن|أن)?\s*", re.IGNORECASE),
        re.compile(r"^(?:بس|انت\s+بس|ليك\s+انت\s+بس|عندك\s+بس)\s+(?:ان|إن|أن)?\s*", re.IGNORECASE),
        re.compile(r"^(?:يا\s+(?:احمد|مازن|توت|نيبولا))\s+(?:ان|إن|أن)?\s*", re.IGNORECASE),
        re.compile(r"^(?:إن|ان|أن|بأن|انو|انه|إنو|إنه)\s+", re.IGNORECASE),
        re.compile(r"^(?:معلومة|معلومه)\s+(?:ان|إن|أن)\s+", re.IGNORECASE),
        re.compile(r"^(?:هو|هي|هما|هم)\s+", re.IGNORECASE),
    ]

    @classmethod
    def clean_fact(cls, raw: str, user_name: Optional[str] = None) -> str:
        """Cleans conversational prefixes, quotes, and normalizes 1st person pronouns."""
        fact = raw.strip(" '\"`()[]{}،,.:;-~؟!?")
        for pref in cls.CLEANUP_PREFIXES:
            fact = pref.sub("", fact).strip()
        actor = user_name.strip() if user_name and user_name.strip() else "المستخدم"
        fact = re.sub(r"^(?:إني|اني)\s+", f"{actor} ", fact, flags=re.IGNORECASE)
        fact = re.sub(r"^(?:أنا|انا)\s+", f"{actor} ", fact, flags=re.IGNORECASE)
        return fact.strip()

    @classmethod
    def normalize_canonical_fact(cls, text: str) -> str:
        """
        Transforms conversational command phrasing into clean, canonical declarative facts.
        Examples:
            - "وظيفة مصعب خليه طيار" -> "مصعب شغال طيار"
            - "شغل احمد خليه مهندس برمجيات" -> "احمد شغال مهندس برمجيات"
            - "وظيفة طارق لـ مهندس ديكور" -> "طارق شغال مهندس ديكور"
            - "مكان المفاتيح خليها على الترابيزة" -> "المفاتيح على الترابيزة"
            - "مكان الكاب في الدولاب" -> "الكاب في الدولاب"
            - "عنوان احمد خليه في المعادي" -> "احمد ساكن في المعادي"
            - "سكن عمر في التجمع" -> "عمر ساكن في التجمع"
        """
        t = text.strip()

        # 1. Job / Profession patterns
        m_job = re.search(
            r"^(?:وظيفة|شغل|شغلانة|مهنة)\s+(?P<subj>[\w\s]+?)\s+(?:خليه|خليها|خليهم|خلّيه|خلّيها|لـ|إلى|الي|يكون|تكون|يبقى|تبقي|هو|هي|انو|انه)\s+(?P<val>[\w\s]+)$",
            t,
            re.IGNORECASE,
        )
        if m_job:
            subj = m_job.group("subj").strip()
            val = m_job.group("val").strip()
            val = re.sub(r"^(?:شغال|شغالة|بيشتغل|بتشتغل)\s+", "", val).strip()
            return f"{subj} شغال {val}"

        m_job_khal = re.search(
            r"^(?:خلي|خلّي)\s+(?P<subj>[\w\s]+?)\s+(?:شغال|شغالة|بيشتغل|بتشتغل)?\s*(?P<val>[\w\s]+)$",
            t,
            re.IGNORECASE,
        )
        if m_job_khal:
            subj = m_job_khal.group("subj").strip()
            val = m_job_khal.group("val").strip()
            first_word = val.split()[0] if val.split() else ""
            if val and first_word not in ["في", "على", "علي", "فوق", "تحت", "جوه", "داخل", "برا"]:
                return f"{subj} شغال {val}"

        # 2. Location patterns
        m_loc = re.search(
            r"^(?:مكان)\s+(?P<subj>[\w\s]+?)\s+(?:خليه|خليها|خليهم|خلّيه|خلّيها|لـ|إلى|الي|يكون|تكون|يبقى|تبقي|هو|هي|انو|انه)?\s*(?P<prep>في|على|علي|فوق|تحت|جوه|داخل|برا|خارج|عند|بجانب|جنب)\s+(?P<val>[\w\s]+)$",
            t,
            re.IGNORECASE,
        )
        if m_loc:
            subj = m_loc.group("subj").strip()
            prep = m_loc.group("prep").strip()
            val = m_loc.group("val").strip()
            return f"{subj} {prep} {val}"

        m_loc_khal = re.search(
            r"^(?:خلي|خلّي)\s+(?P<subj>[\w\s]+?)\s+(?P<prep>في|على|علي|فوق|تحت|جوه|داخل|برا|خارج|عند|بجانب|جنب)\s+(?P<val>[\w\s]+)$",
            t,
            re.IGNORECASE,
        )
        if m_loc_khal:
            subj = m_loc_khal.group("subj").strip()
            prep = m_loc_khal.group("prep").strip()
            val = m_loc_khal.group("val").strip()
            return f"{subj} {prep} {val}"

        # 3. Residence / Address patterns
        m_res = re.search(
            r"^(?:عنوان|سكن|بيت)\s+(?P<subj>[\w\s]+?)\s+(?:خليه|خليها|خليهم|خلّيه|خلّيها|لـ|إلى|الي|يكون|تكون|يبقى|تبقي|هو|هي)?\s*(?:في|بـ)?\s*(?P<val>[\w\s]+)$",
            t,
            re.IGNORECASE,
        )
        if m_res:
            subj = m_res.group("subj").strip()
            val = m_res.group("val").strip()
            val = re.sub(r"^(?:في|بـ)\s+", "", val).strip()
            return f"{subj} ساكن في {val}"

        # 4. Age patterns
        m_age = re.search(
            r"^(?:عمر|سن)\s+(?P<subj>[\w\s]+?)\s+(?:خليه|خليها|خليهم|خلّيه|خلّيها|لـ|إلى|الي|هو|هي)?\s*(?P<val>\d+)(?:\s+سنة|\s+سنه)?$",
            t,
            re.IGNORECASE,
        )
        if m_age:
            subj = m_age.group("subj").strip()
            val = m_age.group("val").strip()
            return f"عمر {subj} {val} سنة"

        # General cleanup: strip isolated command verbs like 'خليه / خليها / خليهم'
        cleaned = re.sub(r"\s+(?:خليه|خليها|خليهم|خلّيه|خلّيها)\s+", " ", t).strip()
        cleaned = re.sub(r"^(?:خليه|خليها|خليهم|خلّيه|خلّيها)\s+", "", cleaned).strip()
        return cleaned

    @classmethod
    def is_shared_fact(cls, text: str) -> bool:
        """
        Determines whether the fact is general real-world / household information
        that should be shared across all personalities (personality_id = None),
        or if it is strictly persona-specific.
        """
        norm = normalize_masri_orthography(text).lower()
        persona_cues = [
            "شخصيتك", "صوتك", "يا مازن", "يا نيبولا", "يا احمد", "انت روبوت", "انت كـ", "انت مين", "توأم رقمي",
            "عندك انت بس", "عندك بس", "في ذاكرتك بس", "خاصة بيك", "خاص بيك", "خاصة بيك انت",
            "ليك انت بس", "لك انت بس", "في سرك", "بيننا بس", "بيني وبينك", "في ذاكرة احمد بس",
            "في ذاكرة مازن بس",
        ]
        return not any(c in norm for c in persona_cues)

    @classmethod
    def process_message(
        cls,
        message: str,
        user_name: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Parses explicit memory commands in chat.
        Returns a dict with action details:
            - action: "save" | "update" | "delete"
            - fact / new_fact / target
            - is_shared (for save/update)
            - reply (friendly grounded response)
        Returns None if not an explicit memory command.
        """
        if not message or not message.strip():
            return None

        clean_msg = message.strip()
        question_marks = ("؟", "?")
        if clean_msg.endswith(question_marks) and any(clean_msg.startswith(q) for q in ["هل", "هو", "انت", "أنت", "فاكر", "حافظ"]):
            return None

        # 1. Check Delete Action
        for pat in cls.DELETE_PATTERNS:
            m = pat.match(clean_msg)
            if m:
                target = cls.clean_fact(m.group(1), user_name)
                canonical_target = cls.normalize_canonical_fact(target)
                from app.services.memory.query_decomposer import QueryDecomposer
                search_target = QueryDecomposer.clean_subject(canonical_target) or canonical_target
                if len(canonical_target) >= 2:
                    return {
                        "action": "delete",
                        "target": search_target,
                        "raw_target": target,
                        "reply": "تمام، مسحت المعلومة دي من الذاكرة بنجاح. [eyes:happy] [nod]",
                    }

        # 2. Check Update Action
        for pat in cls.UPDATE_PATTERNS:
            m = pat.match(clean_msg)
            if m:
                raw_update = cls.clean_fact(m.group(1), user_name)
                # Strip negative comparative suffix e.g. "مش في الدرج"
                clean_new = re.sub(r"\s+مش\s+[\w\s]+$", "", raw_update).strip()
                canonical_new = cls.normalize_canonical_fact(clean_new)
                if len(canonical_new) >= 3:
                    # Extract target subject to look for
                    from app.services.memory.query_decomposer import QueryDecomposer
                    target_subj = QueryDecomposer.clean_subject(canonical_new) or canonical_new
                    return {
                        "action": "update",
                        "raw": raw_update,
                        "new_fact": canonical_new,
                        "target": target_subj,
                        "is_shared": cls.is_shared_fact(clean_msg),
                        "reply": f"تمام، عدلت المعلومة في الذاكرة: {canonical_new}. [eyes:happy] [nod]",
                    }

        # 3. Check Save Action
        for pat in cls.SAVE_PATTERNS:
            m = pat.match(clean_msg)
            if m:
                # Detect target persona if explicitly requested e.g. "عند احمد", "في ذاكرة مازن"
                target_p_match = re.search(
                    r"(?:عند|في\s+ذاكرة|مع|لـ)\s+(?P<p>احمد|مازن|توت|نيبولا)",
                    clean_msg,
                    re.IGNORECASE,
                )
                target_persona = target_p_match.group("p") if target_p_match else None

                raw_fact = m.group(1)
                fact = cls.clean_fact(raw_fact, user_name)

                # If fact starts with pronoun 'انو / انه / هو', resolve to persona name
                if target_persona:
                    fact = re.sub(r"^(?:انو|إنو|انه|إنه|هو)\s+", f"{target_persona} ", fact, flags=re.IGNORECASE).strip()

                canonical_fact = cls.normalize_canonical_fact(fact)
                if len(canonical_fact) >= 3:
                    is_shared = False if target_persona else cls.is_shared_fact(clean_msg)
                    reply_dest = f" في ذاكرة {target_persona}" if target_persona else " في الذاكرة"
                    return {
                        "action": "save",
                        "fact": canonical_fact,
                        "target_persona": target_persona,
                        "is_shared": is_shared,
                        "reply": f"تمام، حفظت{reply_dest}: {canonical_fact}. [eyes:happy] [nod]",
                    }

        return None

    @classmethod
    def extract_fact(
        cls,
        message: str,
        user_name: Optional[str] = None,
    ) -> Optional[Tuple[str, str]]:
        """Backwards compatibility helper."""
        res = cls.process_message(message, user_name)
        if res and res.get("action") == "save":
            return res["fact"], res["reply"]
        return None
