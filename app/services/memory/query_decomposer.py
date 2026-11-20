"""
Query Decomposition & Multi-Hop Query Processor.

Solves the Multi-Hop Reasoning Problem in RAG:
- Single-turn RAG fails on composite or comparative questions (e.g., "What is X and who made it?").
- Decomposes complex queries into atomic search steps.
- Gathers context for each sub-intent to ensure complete information retrieval.
"""

import re
from typing import List, Set, Optional

from app.utils.masri_normalizer import normalize_masri_orthography


class QueryDecomposer:
    """Decomposes compound or multi-hop user queries into atomic sub-queries."""

    _DYNAMIC_ENTITIES_CACHE: Set[str] = set()

    SPLIT_PATTERNS_AR = [
        r"\s+(?:وكمان|وكذلك|بالإضافة إلى|بالاضافة الى|وعلاوة على ذلك)\s+",
        r"\s+(?:مقارنة بـ|مقارنة مع|وقارن بين|وقارن مع)\s+",
        r"\s+(?:وفي نفس الوقت|ويا ريت تقولي عن|واحكيلي عن|وإيه كمان عن)\s+",
        r"[،,\?؟]\s*و\s*",
        r"\s+و\s*(?=[^\s]+(?:\s+[^\s]+){0,4}\s*(?:ايه|إيه|مين|فين|ازاي|إزاي|كام|متى|ليه|شغال|بيشتغل|مكان)\b)",
        r"\s+و(?=إيه|مين|فين|ازاي|كام|متى|ليه|هل)\b",
    ]

    SPLIT_PATTERNS_EN = [
        r"\s+(?:and also|as well as|in addition to|furthermore)\s+",
        r"\s+(?:compare with|compared to|versus|vs\.?)\s+",
        r"[,;\?]\s*and\s*",
        r"\s+and\s+(?=what|who|where|how|when|why|is|are|can)\b",
    ]

    @classmethod
    def decompose(cls, query: str) -> List[str]:
        """
        Decomposes a query into 1 or more focused sub-queries.
        Returns a list of distinct sub-queries. If query is atomic, returns [query].
        """
        if not query or not query.strip():
            return []

        clean_q = query.strip()
        sub_queries: List[str] = []

        # Check Arabic patterns
        is_split = False
        for pat in cls.SPLIT_PATTERNS_AR:
            parts = re.split(pat, clean_q, flags=re.IGNORECASE)
            if len(parts) > 1:
                for p in parts:
                    p_str = cls.clean_vocative(p.strip().rstrip("؟?.,،"))
                    if len(p_str) >= 2 and p_str not in sub_queries:
                        sub_queries.append(p_str)
                is_split = True
                break

        # Check English patterns if not split
        if not is_split:
            for pat in cls.SPLIT_PATTERNS_EN:
                parts = re.split(pat, clean_q, flags=re.IGNORECASE)
                if len(parts) > 1:
                    for p in parts:
                        p_str = cls.clean_vocative(p.strip().rstrip("؟?.,،"))
                        if len(p_str) >= 2 and p_str not in sub_queries:
                            sub_queries.append(p_str)
                    is_split = True
                    break

        # Handle multiple questions separated by question marks
        if not is_split and ("؟" in clean_q or "?" in clean_q):
            parts = re.split(r"[؟\?]+", clean_q)
            valid_parts = [p.strip() for p in parts if len(p.strip()) >= 4]
            if len(valid_parts) > 1:
                sub_queries = valid_parts
                is_split = True

        if not sub_queries:
            sub_queries = [clean_q]

        # Always include the original query as the primary anchor
        if clean_q not in sub_queries:
            sub_queries.insert(0, clean_q)

        return sub_queries

    @classmethod
    def clean_vocative(cls, text: str) -> str:
        """
        Strips vocative addresses like 'يا أحمد', 'ي احمد', 'يا مازن', 'يا نيبولا'.
        """
        if not text:
            return ""
        s = re.sub(
            r'\b(?:يا|ي)\s+(?:احمد|أحمد|مازن|توت|نيبولا|فندم|باشا|صاحبي|سيدي)\b',
            ' ',
            text,
            flags=re.IGNORECASE,
        )
        return re.sub(r'\s+', ' ', s).strip()

    @classmethod
    def get_atomic_subqueries(cls, query: str) -> List[str]:
        """
        Returns atomic sub-queries if composite; if atomic, returns [query].
        Unlike decompose(), does NOT include the composite original query.
        """
        subs = cls.decompose(query)
        if not subs:
            return []
        clean_q = query.strip()
        atomic = [s for s in subs if s.strip() != clean_q]
        return atomic if atomic else [clean_q]

    @classmethod
    def clean_subject(cls, sq: str) -> str:
        """
        Extracts the core entity or subject from an atomic sub-query by removing
        vocatives, interrogative pronouns, conjunctions, and punctuation.
        """
        s = cls.clean_vocative(sq.strip())
        s = re.sub(r'^(?:و|كمان|وكذلك|يا|طب|طيب|and|also|as well as)\s+', '', s.strip(), flags=re.IGNORECASE)
        s = re.sub(
            r'\s*\b(?:فين|ايه|إيه|مين|كام|متى|امتى|إمتى|ازاي|إزاي|ليه|هل|شغال ايه|بيشتغل ايه|مكانها فين|مكانه فين|مكان فين|where|what|who|when|why|how|is|are)\b\s*',
            ' ',
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(
            r'\s*\b(?:كان|كانت|يكون|تكون|كانوا|قبل كده|قبل كدة|زمان|سابقا|سابقاً|حاليا|حالياً|دلوقتي)\b\s*',
            ' ',
            s,
            flags=re.IGNORECASE,
        )
        s = re.sub(r'[؟\?.,،!\s]+$', '', s).strip()
        return s if s else sq.strip()

    @classmethod
    def is_location_query(cls, text: str) -> bool:
        """
        Detects if query is an inquiry about physical location (فين، مكان، أين...).
        """
        if not text:
            return False
        clean = text.lower()
        patterns = [
            r"\b(?:فين|فينها|فينه|أين|اين|مكان|مكانها|مكانه)\b",
            r"\b(?:محطوط|محطوطة|محطوطين|موجود|موجودة|موجودين|شايل|شايلة|سايب|سايبة)\b",
            r"\bwhere\b",
        ]
        return any(re.search(pat, clean) for pat in patterns)

    @classmethod
    def is_temporal_query(cls, text: str) -> bool:
        """
        Detects if query is an inquiry about time or appointment (امتى، الساعة كام، معاد...).
        """
        if not text:
            return False
        clean = text.lower()
        patterns = [
            r"\b(?:امتى|إمتى|متى|توقيت|معاد|ميعاد|موعد)\b",
            r"الساعة\s+كام\b",
            r"\b(?:when|what\s+time)\b",
        ]
        return any(re.search(pat, clean) for pat in patterns)

    @classmethod
    def is_past_inquiry(cls, text: str) -> bool:
        """
        Detects if query is an inquiry about past/previous states or locations
        (e.g., 'كراسة أحمد كانت فين قبل كده؟', 'كانت فين كراسة أحمد؟', 'مكانها القديم ايه؟').
        """
        if not text:
            return False
        clean = normalize_masri_orthography(text).lower()
        patterns = [
            r"\b(?:كانت|كان|كانو|كانوا)\b.*?\b(?:فين|اين|أين)\b",
            r"\b(?:فين|اين|أين)\b.*?\b(?:كانت|كان|كانو|كانوا)\b",
            r"\b(?:قبل\s+كده|قبل\s+كدا|زمان|سابقا|سابقاً|القديم|القديمة|القديمه)\b",
            r"\b(?:في\s+الأول|في\s+الاول|أول\s+مكان|اول\s+مكان|قبل\s+ما\s+تتنقل)\b",
            r"\b(?:used\s+to\s+be|was\s+before|previous\s+location|previously)\b",
        ]
        return any(re.search(pat, clean) for pat in patterns)

    @classmethod
    def is_temporal_fact(cls, text: str) -> bool:
        """
        Detects if a memory content is a temporal appointment or schedule fact
        (e.g., 'معاد احمد اتأجل وخلوه الساعة 5') and NOT a physical object location.
        """
        if not text:
            return False
        clean = text.lower()
        temporal_signals = [
            r"\b(?:معاد|ميعاد|موعد|اتأجل|تأجل|خلوه|خلّوه)\b",
            r"الساعة\s+\d+",
            r"\b(?:موعده|ميعاده|معاده)\b",
        ]
        has_temporal = any(re.search(pat, clean) for pat in temporal_signals)
        if not has_temporal:
            return False
        location_signals = [
            r"\b(?:في\s+الدرج|على\s+المكتب|في\s+الصالة|في\s+الأوضة|في\s+المطبخ|على\s+الرف|في\s+الدولاب|على\s+الترابيزة)\b"
        ]
        has_physical_loc = any(re.search(pat, clean) for pat in location_signals)
        return has_temporal and not has_physical_loc

    @classmethod
    def is_location_fact(cls, text: str) -> bool:
        """
        Detects if a memory content specifies a physical location or position.
        """
        if not text:
            return False
        clean = normalize_masri_orthography(text).lower()
        clean = clean.replace("علي", "على").replace("أ", "ا").replace("إ", "ا")

        # Explicit location participles and keywords
        if re.search(r"\b(?:محطوط|محطوطة|محطوطين|موجود|موجودة|موجودين|شايل|شايلة|سايب|سايبة|متعلق|متعلقة|مرمي|مرمية|مركون|مركونة|مكان|مكانها|مكانه)\b", clean):
            return True

        # Prepositions of place: على, فوق, تحت, جوه, داخل, برا, خارج, جنب, بجانب, عند, ورا, قدام, بين
        temporal_exclusions = r"(?:سنة|عام|شهر|اسبوع|يوم|الساعة|ساعة|الصبح|الظهر|العصر|المغرب|العشا|الليل|الصيف|الشتا|الخريف|الربيع|\d{4})"
        if re.search(rf"\b(?:على|فوق|تحت|جوه|داخل|برا|خارج|جنب|بجانب|عند|ورا|قدام|بين)\s+(?!{temporal_exclusions}\b)[\u0600-\u06FF\w]+", clean):
            return True

        # 'في' followed by place noun (excluding pure temporal expressions and abstract work domains)
        if re.search(rf"\bفي\s+(?!{temporal_exclusions}\b)[\u0600-\u06FF\w]+", clean):
            if not re.search(r"\bفي\s+(?:مجال|هندسة|برمجة|طب|تعليم|ادارة|تسويق|شركة|كلية|جامعة|عام|سنة|مشاريع)\b", clean):
                return True

        return False

    @classmethod
    def extract_subject_items(cls, query: str, target_persona: Optional[str] = None) -> Set[str]:
        """
        Extracts core object/subject item stems inquired in the query
        (e.g., 'قلم احمد فين' -> {'قلم'}, 'ساعة مازن فين' -> {'ساعة'}, 'الساعة فين' -> {'ساعة'}).
        Excludes interrogatives, prepositions, and persona names.
        """
        if not query:
            return set()
        clean = normalize_masri_orthography(query).lower()
        stopwords = {
            "فين", "اين", "أين", "ايه", "إيه", "ما", "ماذا", "مين", "من", "ليه", "لماذا",
            "ازاي", "إزاي", "كيف", "كام", "متى", "امتى", "هل", "مكان", "مكانها", "مكانه",
            "عايز", "عاوز", "اعرف", "قولي", "قلي", "بتاع", "بتاعة", "بتاعت", "تبع", "عند",
            "في", "على", "علي", "هو", "هي", "هم", "كان", "كانت", "يكون", "يا", "مع", "معاه",
            "نوعها", "نوعه", "ماركة", "ماركته",
            # Time & state modifiers
            "قبل", "بعد", "كده", "زمان", "سابقا", "سابقاً", "سابق", "حاليا", "حالياً", "دلوقتي",
            "الاول", "الأول", "القديم", "الجديد"
        }
        if target_persona:
            norm_p = normalize_masri_orthography(target_persona).lower()
            stopwords.add(norm_p)
            stopwords.add(norm_p.replace("أ", "ا"))
        stopwords.update({"احمد", "أحمد", "مازن", "توت"})

        tokens = [w for w in re.findall(r"[\w\d]+", clean) if len(w) >= 2 and w not in stopwords]
        stems: Set[str] = set()
        for w in tokens:
            stems.add(w)
            if w.startswith("ال") and len(w) > 3:
                stems.add(w[2:])
        return stems

    @classmethod
    def is_job_query(cls, text: str) -> bool:
        """
        Detects if query is an inquiry about job, profession, work or occupation (شغال ايه، وظيفته، مهنته، بيسترزق منين...).
        """
        if not text:
            return False
        clean = text.lower()
        job_words = [
            "شغال", "شغاله", "شغالين", "بيشتغل", "بتشتغل", "بيشتغلو",
            "شغل", "شغله", "شغلها", "وظيفة", "وظيفتها", "وظيفته", "مهنة", "مهنته", "تخصص", "تخصصه",
            "بيسترزق", "بيسترزقوا", "أكل عيش", "اكل عيش", "أكل عيشه", "اكل عيشه"
        ]
        pat = rf'(?:^|[\s\b،,\.])(?:[وفلبك]?(?:ال)?)?(?:' + '|'.join(job_words) + rf')(?:ه|ة|ين|ون|ات|ي|ية|ك|كم|هم|ها)?(?:$|[\s\b،,\.\?!؟])'
        return bool(re.search(pat, clean)) or bool(re.search(r"\b(?:work|job|occupation|career)\b", clean))

    @classmethod
    def decompose_multihop_relational(cls, query: str) -> Optional[dict]:
        """
        Detects 2-hop relational inquiries e.g.:
        Structure A: 'عربية صاحب أحمد نوعها ايه؟' or 'شغل أخو مازن ايه؟'
        Structure B: 'صاحب احمد عربيتة ايه؟' or 'صاحب احمد عربيته ايه؟' or 'اخو مازن شغله ايه؟'
        Returns dict with step 1 query and downstream target attribute template.
        """
        if not query:
            return None
        
        # Structure A: Attribute before Relation (e.g. عربية صاحب احمد)
        pat1 = r'\b(?P<attr>عربية|عربيه|شغل|وظيفة|وظيفه|مكان|تليفون|موبايل|مفتاح|ساعة|ساعه|سن|عنوان|بيت)\s+(?P<rel>صاحب|صديق|أخو|اخو|أخت|اخت|والد|ابن|بنت|عم|خال)\s+(?P<person>[\w\d]+)'
        m1 = re.search(pat1, query)
        if m1:
            attr = m1.group("attr").strip()
            rel = m1.group("rel").strip()
            person = m1.group("person").strip()
            return {
                "step1_query": f"{rel} {person}",
                "downstream_attr": attr,
                "origin_person": person,
                "rel": rel,
            }

        # Structure B: Relation before Attribute (e.g. صاحب احمد عربيته / عربيتة ايه)
        pat2 = r'\b(?P<rel>صاحب|صديق|أخو|اخو|أخت|اخت|والد|ابن|بنت|عم|خال)\s+(?P<person>[\w\d]+)\s+(?P<attr_rel>عربيت[ههة]|عربية|عربيه|شغل[ههة]|شغل|وظيفت[ههة]|وظيفة|مكان[ههة]|مكان|تليفون[ههة]|موبايل[ههة]|مفتاح[ههة]|ساعت[ههة]|ساعة|ساعه|سن[ههة]|عنوان[ههة]|بيت[ههة])'
        m2 = re.search(pat2, query)
        if m2:
            rel = m2.group("rel").strip()
            person = m2.group("person").strip()
            raw_attr = m2.group("attr_rel").strip()
            attr_map = {
                "عربيت": "عربية", "عربيه": "عربية", "عربية": "عربية",
                "شغل": "شغل", "وظيفت": "وظيفة", "وظيفة": "وظيفة",
                "مكان": "مكان", "تليفون": "تليفون", "موبايل": "موبايل",
                "مفتاح": "مفتاح", "ساعت": "ساعة", "ساعة": "ساعة",
                "ساعه": "ساعة", "سن": "سن", "عنوان": "عنوان", "بيت": "بيت"
            }
            clean_attr = re.sub(r'[ههة]$', '', raw_attr)
            attr = attr_map.get(clean_attr, clean_attr)
            return {
                "step1_query": f"{rel} {person}",
                "downstream_attr": attr,
                "origin_person": person,
                "rel": rel,
            }

        return None

    @classmethod
    def get_inquiry_aspect(cls, query: str) -> Optional[str]:
        """
        Determines the target semantic aspect/attribute being asked about in the query:
        - 'age': سن، عمر، كام سنة، مواليد
        - 'job': شغال، بيشتغل، وظيفة، مهنة، أكل عيش، بيسترزق، تخصص
        - 'hobby': بيحب ايه، هواية، غاوي، كيفه، مزاجه، بيعشق
        - 'location': فين، مكان، مطرح، محطوط، مركون
        - 'schedule': معاد، ميعاد، موعد، توقيت، امتى، الساعة كام
        - 'residence': ساكن، عايش، عنوان، بيت، شقة
        - 'clothing': لابس، لون، تيشيرت، بنطلون
        - 'contact': رقم، تليفون، موبايل، ايميل
        Returns the aspect name, or None if general/unspecified.
        """
        if not query:
            return None
        q = normalize_masri_orthography(query).lower()
        q = q.replace("سنه", "سنة")

        if re.search(r"\b(?:عمر|عمره|عمرها|كام\s+سنة|عنده\s+كام|عندها\s+كام|سنة\s+كام|مواليد\s+كام|اتولد\s+سنة|تاريخ\s+ميلاد)\b", q):
            return "age"
        if cls.is_job_query(query):
            return "job"
        if cls.is_location_query(query):
            return "location"
        if cls.is_hobby_query(query):
            return "hobby"
        if cls.is_temporal_query(query):
            return "schedule"
        if re.search(r"\b(?:ساكن|عايش|سكن|عنوان|عنوانه|عنوانها|مقيم|يقيم|بيته\s+فين|شقته\s+فين)\b", q):
            return "residence"
        if re.search(r"\b(?:لابس|لبسه|لابسة|لون|طوله|شكله)\b", q):
            return "clothing"
        if re.search(r"\b(?:رقم|تليفون|موبايل|هاتف|فون|ايميل|إيميل)\b", q):
            return "contact"
        return None

    @classmethod
    def fact_has_aspect(cls, text: str, aspect: str) -> bool:
        """
        Checks whether a memory fact satisfies a specific inquiry aspect.
        """
        if not text or not aspect:
            return False
        clean = normalize_masri_orthography(text).lower()
        clean = clean.replace("سنه", "سنة").replace("علي", "على")

        if aspect == "age":
            return bool(re.search(r"\b(?:\d+\s+سنة|عمر|مواليد|سنة\s+\d{4}|اتولد)\b", clean))
        if aspect == "job":
            return cls.is_job_fact(text)
        if aspect == "location":
            return cls.is_location_fact(text)
        if aspect == "hobby":
            return cls.is_hobby_fact(text)
        if aspect == "schedule":
            return cls.is_temporal_fact(text)
        if aspect == "residence":
            return bool(re.search(r"\b(?:ساكن\s+في|عايش\s+في|عنوان|مقيم\s+في|يقيم\s+في|بيته\s+في)\b", clean))
        if aspect == "clothing":
            return bool(re.search(r"\b(?:لابس|لبس|لون|احمر|ازرق|اسود|ابيض|اخضر|اصفر)\b", clean))
        if aspect == "contact":
            return bool(re.search(r"\b(?:01\d{9}|رقم|تليفون|موبايل|ايميل)\b", clean))
        return True

    @classmethod
    def discover_entities(cls, text: str) -> Set[str]:
        """
        Open-Vocabulary Entity Discovery:
        Dynamically extracts new person names from grammatical and conversational cues
        (vocatives, prepositions, possessives, titles, action subjects).
        """
        if not text:
            return set()
        clean = text.strip()
        stop_nouns = {
            "ايه", "إيه", "مين", "فين", "ليه", "ازاي", "كام", "متى", "امتى", "هل",
            "الدرج", "المكتب", "الصالة", "الصاله", "البيت", "الشغل", "الشارع", "الفرن",
            "الساعة", "الساعه", "المفتاح", "البنطلون", "الفراخ", "العربية", "العربيه",
            "الكتاب", "الشنطة", "الشنطه", "المحفظة", "المحفظه", "الكاب", "النظارة", "النظاره",
            "صاحب", "صديق", "أخو", "اخو", "أخت", "اخت", "عم", "خال", "والد", "ابن", "بنت"
        }

        discovered: Set[str] = set()

        # 1. Subject before action verb (e.g. 'زياد شغال ايه', 'مريم بتحب ايه')
        subj_m = re.search(
            r'(?:^|[\s،,])([^\s؟?,!.]+)\s+(?:شغال|شغالة|شغاله|بيشتغل|بتشتغل|بيسترزق|بيسترزقوا|بياكل\s+عيش|بتاكل\s+عيش|أكل\s+عيشه|اكل\s+عيشه|أكل\s+عيشها|اكل\s+عيشها|شغله|شغلها|وظيفته|وظيفتها|بيحب|بتحب|هوايته|هوايتها|ساكن|ساكنة|ساكنه)\b',
            clean
        )
        if subj_m:
            c = subj_m.group(1).strip()
            if len(c) >= 3 and c not in stop_nouns and not c.startswith("ال"):
                discovered.add(c)

        # 2. Vocatives (يا فلان / ي فلان)
        for m in re.finditer(r'\b(?:يا|ي)\s+([^\s؟?,!.]+)', clean):
            c = m.group(1).strip()
            if len(c) >= 3 and c not in stop_nouns and not c.startswith("ال"):
                discovered.add(c)

        # 3. Kinship & relations (صاحب فلان، أخو فلان، عم فلان)
        for m in re.finditer(r'\b(?:صاحب|صديق|أخو|اخو|أخت|اخت|والد|ابن|بنت|عم|خال|زوج|مدير)\s+([^\s؟?,!.]+)', clean):
            c = m.group(1).strip()
            if len(c) >= 3 and c not in stop_nouns and not c.startswith("ال"):
                discovered.add(c)

        # 4. Titles (الباشمهندس فلان، الدكتور فلان، الأستاذ فلان)
        for m in re.finditer(r'\b(?:الباشمهندس|المهندس|الدكتور|الدكتورة|الأستاذ|الاستاذ|الأستاذة|الاستاذه|الشيخ|الكابتن|المعلم)\s+([^\s؟?,!.]+)', clean):
            c = m.group(1).strip()
            if len(c) >= 3 and c not in stop_nouns and not c.startswith("ال"):
                discovered.add(c)

        # 5. Possessives / Annexation (بتاع فلان، عند فلان، مع فلان، ساعة فلان، قلم فلان، كراسة فلان)
        item_cues = [
            "بتاع", "بتاعة", "بتاعت", "عند", "مع", "لـ",
            "ساعة", "ساعه", "عربية", "عربيه", "شغل", "وظيفة", "وظيفه", "مكتب", "تليفون", "موبايل",
            "قلم", "كراسة", "كراسه", "كتاب", "شنطة", "شنطه", "مفتاح", "كاب", "نظارة", "نظاره",
            "لابتوب", "كمبيوتر", "شاحن", "محفظة", "محفظه", "سرير", "دولاب", "كرسي", "ورقة", "ورقه",
            "بيت", "عنوان", "شقة", "شقه", "فلوس", "رقم"
        ]
        items_pattern = r'\b(?:' + '|'.join(item_cues) + r')\s+([^\s؟?,!.]+)'
        for m in re.finditer(items_pattern, clean):
            c = m.group(1).strip()
            if len(c) >= 3 and c not in stop_nouns and not c.startswith("ال"):
                discovered.add(c)

        # Cache dynamically discovered names for subsequent turns
        for name in discovered:
            cls._DYNAMIC_ENTITIES_CACHE.add(cls._norm(name))

        return discovered

    @classmethod
    def is_hobby_query(cls, text: str) -> bool:
        """
        Detects if query is an inquiry about hobbies or what a person likes (بيحب ايه، بيحب لعب ايه، هوايته...).
        """
        if not text:
            return False
        clean = text.lower()
        patterns = [
            r"\b(?:بيحب|بتحب|بيحبو|بيحبوا|هواية|هوايته|هوايتها|بيعشق|بيمارس|لعب ايه|بيحب ايه)\b",
            r"\b(?:hobby|hobbies|likes|prefers)\b",
        ]
        return any(re.search(pat, clean) for pat in patterns)

    @classmethod
    def is_job_fact(cls, text: str) -> bool:
        """
        Detects if a memory content describes a profession, job, or occupation,
        accounting for Arabic conjunctions and prefixes (المهندس، ومطور، كطبيب...).
        """
        if not text:
            return False
        clean = text.lower()
        job_roots = [
            "مهندس", "مطور", "مبرمج", "دكتور", "طبيب", "محامي", "محاسب", "سواق",
            "مدرس", "معلم", "لاعب", "شغال", "بيشتغل", "بتشتغل", "يعمل", "تعمل",
            "وظيفة", "تخصص", "طالب", "يدرس", "مهنة"
        ]
        pat = rf'(?:^|[\s\b،,\.])(?:[وفلبك]?(?:ال)?)?(?:' + '|'.join(job_roots) + rf')(?:ه|ة|ين|ون|ات|ي|ية)?(?:$|[\s\b،,\.\?!؟])'
        return bool(re.search(pat, clean))

    @classmethod
    def is_hobby_fact(cls, text: str) -> bool:
        """
        Detects if a memory content describes a hobby/interest (and not a job).
        """
        if not text:
            return False
        clean = text.lower()
        has_hobby_word = bool(re.search(r"\b(?:بيحب|بتحب|بيحبو|بيحبوا|هواية|هوايته|هوايتها|بيعشق|بيمارس)\b", clean))
        has_job_word = cls.is_job_fact(text)
        return has_hobby_word and not has_job_word

    @classmethod
    def _norm(cls, n: str) -> str:
        """Normalizes Arabic text for robust fuzzy name and root matching."""
        if not n:
            return ""
        s = n.strip()
        s = re.sub(r"[أإآ]", "ا", s)
        s = re.sub(r"ة", "ه", s)
        s = re.sub(r"ى", "ي", s)
        return s

    @classmethod
    def extract_mentioned_person_names(cls, text: str, extra_names: Optional[List[str]] = None) -> Set[str]:
        """
        Extracts known and dynamically discovered person names mentioned in text.
        """
        if not text:
            return set()
        cls.discover_entities(text)
        norm_text = cls._norm(text)
        known = {
            "احمد", "مازن", "ايمن", "عمر", "طارق", "محمد", "محمود",
            "ساره", "نور", "خالد", "يوسف", "حسن", "حسين", "كريم", "مصطفي", "ابراهيم", "توت"
        }
        known.update(cls._DYNAMIC_ENTITIES_CACHE)
        if extra_names:
            for en in extra_names:
                if en and en.strip():
                    known.add(cls._norm(en))
        words = re.findall(r"[\u0600-\u06FF]+", norm_text)
        return {w for w in words if w in known and w != "علي"}

    @classmethod
    def extract_target_persona_name(cls, query: str, known_personas: Optional[List[str]] = None) -> Optional[str]:
        """
        Extracts explicitly targeted persona if the query targets a specific person's item or addresses them:
        e.g., 'ساعة أحمد فين', 'الساعة فين عند أحمد', 'الساعة بتاعت مازن فين', 'يا أحمد الساعة فين'.
        Supports open-vocabulary dynamically discovered entities.
        Returns the matching persona name, or None if the query is general.
        """
        if not query:
            return None
        cls.discover_entities(query)
        names = list(known_personas or ["أحمد", "احمد", "مازن", "توت"])
        for dyn in cls._DYNAMIC_ENTITIES_CACHE:
            if dyn not in names:
                names.append(dyn)

        # Multi-persona inquiries (e.g. 'ساعة أحمد وساعة مازن') do not target a single persona
        mentioned = cls.extract_mentioned_person_names(query, names)
        if len(mentioned) > 1:
            return None

        norm_known = {cls._norm(k): k for k in names if k}
        norm_query = cls._norm(query)

        # 1. Vocative: يا أحمد / ي احمد / يا زياد
        voc_match = re.search(r'\b(?:يا|ي)\s+([^\s؟?,!.]+)', query)
        if voc_match:
            cand = voc_match.group(1).strip()
            if cls._norm(cand) in norm_known:
                return norm_known[cls._norm(cand)]

        # 2. Prepositional: عند أحمد / بتاعت أحمد / بتاع مازن
        prep_match = re.search(r'\b(?:عند|بتاع|بتاعة|بتاعت|تبع)\s+([^\s؟?,!.]+)', query)
        if prep_match:
            cand = prep_match.group(1).strip()
            if cls._norm(cand) in norm_known:
                return norm_known[cls._norm(cand)]

        # 3. Possessive / Annexation (e.g. كراسة أحمد / الكراسة أحمد / قلم مازن / القلم مازن / عربية زياد)
        poss_match = re.search(r'\b(?:ال)?([^\s]+)\s+([^\s؟?,!.]+)', query)
        if poss_match:
            noun_cand = poss_match.group(1).strip()
            name_cand = poss_match.group(2).strip()
            if cls._norm(name_cand) in norm_known and cls._norm(noun_cand) not in {"يا", "ي", "عند", "بتاع", "بتاعة", "بتاعت", "مع", "في", "على", "مين", "فين", "ايه", "ليه", "ازاي"}:
                return norm_known[cls._norm(name_cand)]

        # 4. Direct word boundary match against known names (normalized)
        for k in names:
            if not k:
                continue
            norm_k = cls._norm(k)
            if re.search(rf'(?:^|[\s\b]){re.escape(norm_k)}(?:$|[\s\b،,\.!\?؟])', norm_query):
                return norm_known.get(norm_k, k)

        return None



