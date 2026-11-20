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
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:امسح|إمسح|احذف|إحذف|شيل)(?:\s+(?:من\s+(?:عند|ذاكرة|ذاكرتك)\s+(?P<p1>[\w\u0621-\u064A]+)))?(?:\s+(?:عند\s+(?P<p2>[\w\u0621-\u064A]+)))?(?:\s+(?:من\s+الذاكرة|من\s+ذاكرتك))?(?:\s+(?:معلومة|معلومه|حاجة|حاجه))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s+(.+)$",
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
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:عدل|عدلت|غير|غيرت|بدل|بدلت|صلح|صلحت|حدث|حدّث)?(?:\s+(?:عندك|معاك|(?:عند|مع|لـ|في\s+ذاكرة)\s+(?P<p>[\w\u0621-\u064A]+)))?\s*(?:مكان\s+)?(?P<subj>[\w\s]+?)\s+(?:بقت|بقى|بقت\s+دلوقتي|بقى\s+دلوقتي|اتنقلت|اتنقل|خليتها|خليته|سبتها|سيبته|حطيتها|حطيته)\s+(?P<prep>على|علي|في|فوق|تحت|جوه|داخل|برا|خارج|عند|جنب|بجانب)\s+(?P<val>[\w\s]+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:أنا\s+|انا\s+)?(?:نقلت|حطيت|شيلت|وديت)\s+(?P<subj>[\w\s]+?)\s+(?:و\s*(?:حطيتها|حطيته|سبتها|سيبته|خليتها|خليته)\s+)?(?P<prep>على|علي|في|فوق|تحت|جوه|داخل|برا|خارج|عند|جنب|بجانب)\s+(?P<val>[\w\s]+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:أنا\s+|انا\s+)?(?:غيرت|بدلت|عدلت)\s+(?:مكان\s+)?(?P<subj>[\w\s]+?)\s+(?:و\s*(?:خليتها|خليته|حطيتها|حطيته|سبتها|سيبته)\s+)?(?P<prep>على|علي|في|فوق|تحت|جوه|داخل|برا|خارج|عند|جنب|بجانب)\s+(?P<val>[\w\s]+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:عدل|عدلت|صلح|صلحت|غير|غيرت|بدل|بدلت|حدث|حدّث|حدثت)(?:\s+(?:عندك|معاك|(?:عند|مع|لـ|في\s+ذاكرة)\s+[\w\u0621-\u064A]+))?(?:\s+(?:في\s+الذاكرة|في\s+ذاكرتك))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s*[:\-]?\s*(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:please\s+)?(?:could\s+you\s+)?(?:update|correct|change|modify)(?:\s+(?:in\s+memory))?\s*[:\-]?\s+(.+)$",
            re.IGNORECASE,
        ),
    ]

    SAVE_PATTERNS = [
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:احفظ|إحفظ)(?:\s+(?:عندك|معاك|(?:عند|مع|لـ|في\s+ذاكرة)\s+[\w\u0621-\u064A]+))?(?:\s+(?:في\s+الذاكرة|في\s+ذاكرتك))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s*[:\-]?\s*(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:افتكر|إفتكر|خليك\s+فاكر|متنساش|ماتنساش|اوعى\s+تنسى|إوعى\s+تنسى)(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s*[:\-]?\s*(.+)$",
            re.IGNORECASE,
        ),
        re.compile(
            r"^(?:يا\s+[\w\s]+\s+)?(?:لو\s+سمحت\s+|من\s+فضلك\s+)?(?:عايزك\s+|عاوزك\s+|ممكن\s+)?(?:سجل|خزن)(?:\s+(?:عندك|معاك|(?:عند|مع|لـ|في\s+ذاكرة)\s+[\w\u0621-\u064A]+))?(?:\s+(?:في\s+الذاكرة|في\s+ذاكرتك))?(?:\s+(?:إن|ان|أن|بأن|انو|انه))?\s*[:\-]?\s*(.+)$",
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
        re.compile(r"^(?:عند|في\s+ذاكرة|مع|لـ)\s+[\w\u0621-\u064A]+\s*(?:ان|إن|أن|انو|انه|بأن)?\s*", re.IGNORECASE),
        re.compile(r"^(?:في\s+ذاكرتك\s+بس|عندك\s+انت\s+بس|عندك\s+بس|بيني\s+وبينك\s+بس|بيني\s+وبينك|في\s+سرك|خاصة\s+بيك\s+انت\s+بس|خاصة\s+بيك\s+بس|خاصة\s+بيك)\s+(?:ان|إن|أن)?\s*", re.IGNORECASE),
        re.compile(r"^(?:بس|انت\s+بس|ليك\s+انت\s+بس|عندك\s+بس)\s+(?:ان|إن|أن)?\s*", re.IGNORECASE),
        re.compile(r"^(?:يا\s+[\w\u0621-\u064A]+)\s+(?:ان|إن|أن)?\s*", re.IGNORECASE),
        re.compile(r"^(?:إن|ان|أن|بأن|انو|انه|إنو|إنه)\s+", re.IGNORECASE),
        re.compile(r"^(?:معلومة|معلومه)\s+(?:ان|إن|أن|عن)?\s*", re.IGNORECASE),
        re.compile(r"^(?:عن)\s+", re.IGNORECASE),
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

    HUMAN_ATTRIBUTE_PATTERNS = [
        re.compile(
            r"(?:^|[\s\b،,\.])(?:[وفلبك]?(?:ال)?)?(?:شغال|شغالة|بيشتغل|بتشتغل|وظيفة|مهنة|تخصص|مجال|أكل عيش|اكل عيش|بيسترزق|مهندس|دكتور|طبيب|محامي|مدرس|معلم|طيار|مبرمج|محاسب|ضابط|ظابط|صيدلي|طالب|باحث|كاتب|مترجم|مدير|فنان|رسام|سواق|نجار|سباك|كهربائي|عامل)(?:ه|ة|ين|ون|ات|ي|ية)?(?:$|[\s\b،,\.\?!؟])",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:^|[\s\b،,\.])(?:[وفلبك]?(?:ال)?)?(?:بيحب|بتحب|بحب|عاوز|عايز|غاوي|غاوية|هواية|هوايته|هوايتها|بيكره|بتكره|بيفضل|بتفضل|بيعشق|بتعشق|بيمارس)(?:$|[\s\b،,\.\?!؟])",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?:^|[\s\b،,\.])(?:[وفلبك]?(?:ال)?)?(?:عمر|سنة|سنه|مواليد|تاريخ ميلاد|عايش في|ساكن في|بيته في|عنوانه)(?:$|[\s\b،,\.\?!؟])",
            re.IGNORECASE,
        ),
    ]

    @classmethod
    def is_human_attribute(cls, text: str) -> bool:
        """
        Determines whether the fact describes a personal human attribute
        (job, profession, hobby, age, residence, etc.) rather than a general
        household object or shared world fact.
        """
        if not text:
            return False
        return any(pat.search(text) for pat in cls.HUMAN_ATTRIBUTE_PATTERNS)

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
    def resolve_possessive_pronoun(cls, text: str, persona: Optional[str]) -> str:
        """
        Resolves possessive pronoun and definite noun references in facts when a target persona is specified:
        - 'الكراسه علي السرير' + 'مازن' -> 'كراسة مازن علي السرير'
        - 'الشنطة جنب الباب' + 'مازن' -> 'شنطة مازن جنب الباب'
        - 'كراسته على المكتب' + 'أحمد' -> 'كراسة أحمد على المكتب'
        - 'شنطته جنب الباب' + 'مازن' -> 'شنطة مازن جنب الباب'
        - 'قلمه في الدرج' + 'أحمد' -> 'قلم أحمد في الدرج'
        - 'كتابه على الرف' + 'أحمد' -> 'كتاب أحمد على الرف'
        """
        if not persona or not text:
            return text
        clean_p = persona.strip()

        # Case A: Definite noun e.g. 'الكراسه علي السرير' -> 'كراسة مازن علي السرير'
        m_def = re.match(r"^ال(\w+?)\s+(على|علي|في|فوق|تحت|جوه|داخل|برا|خارج|عند|جنب|بجانب)\s+(.+)$", text)
        if m_def:
            noun = m_def.group(1)
            if noun.endswith(('ه', 'ة')):
                noun = noun[:-1] + 'ة'
            prep = m_def.group(2)
            val = m_def.group(3)
            return f"{noun} {clean_p} {prep} {val}"

        # Case B: Feminine noun + pronoun suffix e.g. 'كراسته على المكتب' -> 'كراسة أحمد على المكتب'
        m_fem = re.match(r"^(\w+)(?:ته|ـته)\s+(على|علي|في|فوق|تحت|جوه|داخل|برا|خارج|عند|جنب|بجانب)\s+(.+)$", text)
        if m_fem:
            noun = m_fem.group(1) + 'ة'
            prep = m_fem.group(2)
            val = m_fem.group(3)
            return f"{noun} {clean_p} {prep} {val}"

        # Case C: Masculine noun + pronoun suffix e.g. 'قلمه في الدرج' -> 'قلم أحمد في الدرج'
        m_masc = re.match(r"^([^\s]+?)(?:ه|ـه)\s+(على|علي|في|فوق|تحت|جوه|داخل|برا|خارج|عند|جنب|بجانب)\s+(.+)$", text)
        if m_masc:
            noun = m_masc.group(1)
            feminine_stems = {'كراس', 'شنط', 'ساع', 'ترابيز', 'عربيت', 'اوض', 'شقت', 'ورق', 'نظار', 'ازاز', 'علب'}
            if noun not in feminine_stems and not noun.startswith('ال'):
                prep = m_masc.group(2)
                val = m_masc.group(3)
                return f"{noun} {clean_p} {prep} {val}"

        return text

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

        from app.services.memory.query_decomposer import QueryDecomposer

        # 1. Check Delete Action
        for pat in cls.DELETE_PATTERNS:
            m = pat.match(clean_msg)
            if m:
                gd = m.groupdict() if hasattr(m, "groupdict") else {}
                target_p = gd.get("p1") or gd.get("p2")
                if target_p in ("الذاكرة", "ذاكرتك"):
                    target_p = None
                if not target_p:
                    tp_m = re.search(r"(?:من\s+(?:عند|ذاكرة|ذاكرتك)|عند|في\s+ذاكرة|لـ)\s+(?P<p>[\w\u0621-\u064A]+)", clean_msg)
                    if tp_m and tp_m.group("p") not in ("الذاكرة", "ذاكرتك"):
                        target_p = tp_m.group("p")

                raw_target = m.groups()[-1].strip()
                target = cls.clean_fact(raw_target, user_name)
                target = re.sub(r"\s+من\s+(?:الذاكرة|ذاكرتك)$", "", target).strip()
                if not target_p:
                    target_p = QueryDecomposer.extract_target_persona_name(target)
                canonical_target = cls.normalize_canonical_fact(target)
                search_target = QueryDecomposer.clean_subject(canonical_target) or canonical_target
                if len(canonical_target) >= 2:
                    return {
                        "action": "delete",
                        "target": search_target,
                        "target_persona": target_p,
                        "raw_target": target,
                        "reply": "تمام، مسحت المعلومة دي من الذاكرة بنجاح. [eyes:happy] [nod]",
                    }

        # 2. Check Update Action
        for pat in cls.UPDATE_PATTERNS:
            m = pat.match(clean_msg)
            if m:
                gd = m.groupdict()
                if gd.get("subj") and gd.get("prep") and gd.get("val"):
                    subj_clean = gd["subj"].strip()
                    prep_clean = gd["prep"].strip()
                    val_clean = gd["val"].strip()
                    target_pname = gd.get("p")
                    if target_pname in ("الذاكرة", "ذاكرتك"):
                        target_pname = None
                    if not target_pname:
                        target_pname = QueryDecomposer.extract_target_persona_name(subj_clean) or QueryDecomposer.extract_target_persona_name(clean_msg)

                    full_test = f"{subj_clean} {prep_clean} {val_clean}"
                    if target_pname:
                        full_resolved = cls.resolve_possessive_pronoun(full_test, target_pname)
                        if full_resolved != full_test:
                            subj_m = re.search(r"^(.+?)\s+(?:على|علي|في|فوق|تحت|جوه|داخل|برا|خارج|عند|جنب|بجانب)\s+", full_resolved)
                            subj_clean = subj_m.group(1).strip() if subj_m else subj_clean
                        elif target_pname not in subj_clean:
                            if subj_clean.startswith("ال") and len(subj_clean) > 3:
                                base_item = subj_clean[2:]
                                if base_item.endswith(('ه', 'ة')):
                                    base_item = base_item[:-1] + 'ة'
                                subj_clean = f"{base_item} {target_pname}"

                    canonical_new = f"{subj_clean} {prep_clean} {val_clean}"
                    target_subj = subj_clean
                    return {
                        "action": "update",
                        "raw": canonical_new,
                        "new_fact": canonical_new,
                        "target": target_subj,
                        "target_persona": target_pname,
                        "is_shared": cls.is_shared_fact(clean_msg) and not bool(target_pname),
                        "reply": f"تمام، عدلت المعلومة في الذاكرة: {canonical_new}. [eyes:happy] [nod]",
                    }
                else:
                    raw_update = cls.clean_fact(m.groups()[-1], user_name)
                    clean_new = re.sub(r"\s+مش\s+[\w\s]+$", "", raw_update).strip()
                    target_pname = None
                    tp_m = re.search(r"(?:عند|مع|في\s+ذاكرة|لـ)\s+(?P<p>[\w\u0621-\u064A]+)", clean_msg)
                    if tp_m and tp_m.group("p") not in ("الذاكرة", "ذاكرتك"):
                        target_pname = tp_m.group("p")
                    if not target_pname:
                        target_pname = QueryDecomposer.extract_target_persona_name(clean_new) or QueryDecomposer.extract_target_persona_name(clean_msg)

                    canonical_new = cls.normalize_canonical_fact(clean_new)
                    canonical_new = cls.resolve_possessive_pronoun(canonical_new, target_pname)
                    if len(canonical_new) >= 3:
                        subj_m = re.search(r"^(.+?)\s+(?:على|علي|في|فوق|تحت|جوه|داخل|برا|خارج|عند|جنب|بجانب|شغال|شغالة|ساكن|ساكنة)\s+", canonical_new)
                        target_subj = subj_m.group(1).strip() if subj_m else (QueryDecomposer.clean_subject(canonical_new) or canonical_new)
                        return {
                            "action": "update",
                            "raw": raw_update,
                            "new_fact": canonical_new,
                            "target": target_subj,
                            "target_persona": target_pname,
                            "is_shared": cls.is_shared_fact(clean_msg) and not bool(target_pname),
                            "reply": f"تمام، عدلت المعلومة في الذاكرة: {canonical_new}. [eyes:happy] [nod]",
                        }

        # 3. Check Save Action
        for pat in cls.SAVE_PATTERNS:
            m = pat.match(clean_msg)
            if m:
                target_p_match = re.search(
                    r"(?:عند|في\s+ذاكرة|مع|لـ)\s+(?P<p>[\w\u0621-\u064A]+)",
                    clean_msg,
                    re.IGNORECASE,
                )
                target_persona = target_p_match.group("p") if target_p_match and target_p_match.group("p") not in ("الذاكرة", "ذاكرتك") else None

                raw_fact = m.groups()[-1]
                fact = cls.clean_fact(raw_fact, user_name)

                if target_persona:
                    fact = re.sub(r"^(?:انو|إنو|انه|إنه|هو)\s+", f"{target_persona} ", fact, flags=re.IGNORECASE).strip()

                if not target_persona:
                    target_persona = QueryDecomposer.extract_target_persona_name(fact)

                canonical_fact = cls.normalize_canonical_fact(fact)
                canonical_fact = cls.resolve_possessive_pronoun(canonical_fact, target_persona)
                if len(canonical_fact) >= 3:
                    mentioned_names = QueryDecomposer.extract_mentioned_person_names(canonical_fact)

                    system_personas = ["احمد", "أحمد", "مازن", "توت", "نيبولا"]
                    system_target = None
                    for p in system_personas:
                        if p in mentioned_names or canonical_fact.startswith(p):
                            system_target = "احمد" if ("أحمد" in p or "احمد" in p) else p
                            break

                    if not target_persona and system_target:
                        target_persona = system_target

                    norm_system = {QueryDecomposer._norm(p) for p in system_personas}
                    external_names = {n for n in mentioned_names if QueryDecomposer._norm(n) not in norm_system}
                    first_w = canonical_fact.split()[0] if canonical_fact.split() else ""
                    norm_first = QueryDecomposer._norm(first_w)
                    if norm_first in QueryDecomposer._DYNAMIC_ENTITIES_CACHE and norm_first not in norm_system:
                        external_names.add(first_w)

                    has_external_person = bool(external_names)

                    if target_persona:
                        is_shared = False
                    elif has_external_person:
                        is_shared = True
                    elif cls.is_human_attribute(canonical_fact):
                        is_shared = False
                    else:
                        is_shared = cls.is_shared_fact(clean_msg)

                    reply_dest = f" في ذاكرة {target_persona}" if target_persona else (" في ذاكرتك" if not is_shared else " في الذاكرة")
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
