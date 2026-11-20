"""
Deterministic Fact Verification & Anti-Hallucination Guard.

Solves the Hallucination & Faithfulness Problem in RAG:
- Uses strict rule-based, entity-matching, and citation-grounding verification against the retrieved context.
- Detects fabricated sensitive data (phone numbers, passwords, fake IDs, ungrounded numbers).
- If an ungrounded claim is detected, it sanitizes and enforces the strict verified response.
"""

import re
from typing import List, Dict, Any, Tuple, Optional

from app.core.logger import get_logger
from app.utils.masri_normalizer import normalize_masri_orthography

logger = get_logger(__name__)


class FactVerifier:
    """
    Validates that every claim in the LLM's response is directly supported by the retrieved context.
    Eliminates hallucinations deterministically.
    """

    REFUSAL_AR = "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
    REFUSAL_EN = "I do not have this information recorded in my memory. [wave]"

    # Patterns for sensitive/private data often hallucinated
    SENSITIVE_PATTERNS = [
        re.compile(r"01[0125]\d{8}"),            # Egyptian phone numbers
        re.compile(r"\+20\d{10}"),                # International Egyptian numbers
        re.compile(r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b"),  # Credit card formats
        re.compile(r"(?:الباسورد|كلمة السر|الرقم السري|password|pin code)\s*[:=]?\s*[\w\d@#$%]+", re.IGNORECASE),
    ]

    SENSITIVE_INQUIRY_TERMS = [
        "هاتف", "تليفون", "موبايل", "محمول", "phone", "mobile",
        "سر", "سري", "سرية", "باسورد", "password", "pin",
        "حساب", "خزنة", "بنك", "فيزا", "بطاقة", "كارت", "bank", "credit",
        "عنوان", "غير مسجل", "غير مسجلة",
    ]

    QUESTION_STOPWORDS = {
        "فين", "اين", "أين", "ايه", "إيه", "ما", "ماذا", "مين", "من", "ليه", "لماذا",
        "ازاي", "إزاي", "كيف", "كام", "كم", "متى", "امتى", "إمتى", "هل", "هو", "هي",
        "هم", "هما", "عن", "في", "على", "علي", "مع", "من", "إلى", "الي", "بتاع",
        "بتاعة", "بتاعت", "بتاعتي", "بتاعك", "بتاعه", "بتاعها", "كان", "يكون", "يا",
        "لو", "سمحت", "من", "فضلك", "ممكن", "تقولي", "مكان", "مكانها", "مكانه",
        "where", "what", "who", "when", "why", "how", "is", "are", "the", "a", "an", "in", "on", "at"
    }

    FACTUAL_INQUIRY_SIGNALS = [
        "فين", "مكان", "شغال", "بيشتغل", "تخصص", "معاد", "ميعاد", "ساعة", "كام", "امتى", "إمتى", "متى",
        "رقم", "تليفون", "موبايل", "باسورد", "عنوان", "ساكن", "عايش", "مع مين", "بيحب", "بتحب",
        "بيسترزق", "بيسترزقوا", "أكل عيش", "اكل عيش", "مطرح", "كيفه", "مزاجه", "هواية", "هوايته",
        "where", "when", "who is", "what is", "work", "job", "location", "address"
    ]

    COLLOQUIAL_CONCEPT_BUNDLES: Dict[str, List[str]] = {
        "job": [
            "شغال", "شغالة", "بيشتغل", "بتشتغل", "شغل", "شغلانة", "وظيفة", "مهنة",
            "أكل عيش", "اكل عيش", "بيسترزق", "بيسترزقوا", "تخصص", "مجال", "مهندس", "دكتور",
            "طبيب", "محامي", "مدرس", "معلم", "طيار", "مبرمج", "محاسب", "ظابط", "ضابط",
            "صيدلي", "سواق", "رسام", "فنان", "عامل", "بياكل عيش", "بتاكل عيش"
        ],
        "location": [
            "فين", "مكان", "مطرح", "محطوط", "محطوطة", "موجود", "موجودة", "مركون",
            "مركونة", "سايب", "سايبها", "سايبه", "حاطط", "حاطة", "في", "على", "علي",
            "فوق", "تحت", "جوه", "داخل", "برا", "خارج", "دولاب", "درج", "مكتب", "ترابيزة"
        ],
        "hobby": [
            "بيحب", "بتحب", "بحب", "عاوز", "عايز", "غاوي", "غاوية", "كيفه", "كيفها",
            "مزاجه", "مزاجها", "هواية", "هوايته", "هوايتها", "بيعشق", "بتعشق", "بيمارس",
            "سباحة", "كورة", "قراءة", "قهوة"
        ],
        "schedule": [
            "معاد", "ميعاد", "توقيت", "امتى", "إمتى", "متى", "ساعة", "الساعة",
            "هيتقابلوا", "هيقابل", "مقابلة", "موعد", "مواعيد", "اتأجل", "خلوه"
        ],
        "residence": [
            "ساكن", "ساكنة", "عايش", "عايشة", "سكن", "عنوان", "عنوانه", "عنوانها",
            "بيت", "بيته", "شقة", "شقته", "منطقة", "حي", "مقيم", "يقيم"
        ],
    }

    @classmethod
    def is_sensitive_or_private_inquiry(cls, query: str) -> bool:
        """
        Determines whether the user's query is asking for private/sensitive personal facts,
        credentials, phone numbers, or passwords that require strict refusal if not in memory.
        """
        if not query:
            return False
        q_norm = normalize_masri_orthography(query).lower()
        return any(term in q_norm for term in cls.SENSITIVE_INQUIRY_TERMS)

    @classmethod
    def is_factual_personal_inquiry(cls, query: str) -> bool:
        """
        Determines whether the user's query is asking for a specific personal/factual detail
        (e.g. item location 'الكاب فين؟', job, schedule, phone number, address) which requires
        recorded memories to answer accurately.
        """
        if not query:
            return False
        q_norm = normalize_masri_orthography(query).lower()
        return any(term in q_norm for term in cls.FACTUAL_INQUIRY_SIGNALS) or cls.is_sensitive_or_private_inquiry(query)

    @classmethod
    def verify_and_sanitize(
        cls,
        query: str,
        response: str,
        retrieved_memories: List[str],
        is_greeting: bool = False,
        has_action: bool = False,
    ) -> str:
        """
        Validates the generated response against retrieved memories.
        Returns the sanitized, guaranteed grounded response.
        """
        if not response:
            return cls.REFUSAL_AR

        is_arabic = bool(re.search(r"[\u0600-\u06FF]", query or response))
        default_refusal = cls.REFUSAL_AR if is_arabic else cls.REFUSAL_EN

        # 1. If context was completely empty and this is not a greeting or action:
        if not retrieved_memories and not is_greeting and not has_action:
            from app.services.memory.query_decomposer import QueryDecomposer
            mentioned_names = QueryDecomposer.extract_mentioned_person_names(query)
            is_personal = cls.is_factual_personal_inquiry(query) or bool(mentioned_names)

            if is_personal:
                logger.info(f"FactVerifier: Factual personal inquiry '{query}' with empty context -> Enforcing refusal.")
                return default_refusal

            # For open-domain questions (general knowledge, coding, math), verify no hallucinated sensitive patterns:
            for pat in cls.SENSITIVE_PATTERNS:
                if pat.search(response):
                    logger.warning("FactVerifier: Open-domain response contains sensitive pattern -> Enforcing refusal.")
                    return default_refusal

            # If the response fabricated specific critical numbers without context:
            resp_numbers = set(re.findall(r"\b\d{3,}\b", response))
            if resp_numbers:
                logger.warning(f"FactVerifier: Open-domain response contains ungrounded critical numbers {resp_numbers} -> Enforcing refusal.")
                return default_refusal

            return response

        combined_context = " ".join(retrieved_memories)
        norm_context = normalize_masri_orthography(combined_context).lower()
        norm_response = normalize_masri_orthography(response).lower()

        # 2. Check for Hallucinated Sensitive Patterns (Phone numbers, passwords)
        for pat in cls.SENSITIVE_PATTERNS:
            found_in_resp = pat.search(response)
            if found_in_resp:
                val = found_in_resp.group(0)
                # If this sensitive value is NOT in the retrieved context, it's a hallucination!
                if val not in combined_context:
                    logger.warning(f"FactVerifier: Hallucinated sensitive pattern detected ('{val}'). Overriding with refusal.")
                    return default_refusal

        # 3. Check for ungrounded numbers or dates in response
        resp_numbers = set(re.findall(r"\b\d{2,}\b", response))
        ctx_numbers = set(re.findall(r"\b\d{2,}\b", combined_context))

        unsupported_numbers = resp_numbers - ctx_numbers
        # Filter out numbers that might be harmless (e.g. 1, 2 for list enumeration)
        unsupported_critical_numbers = [n for n in unsupported_numbers if len(n) >= 3 or n.startswith("01")]
        if unsupported_critical_numbers:
            logger.warning(
                f"FactVerifier: Response contains ungrounded critical numbers {unsupported_critical_numbers}. "
                f"Enforcing refusal."
            )
            return default_refusal

        # 4. Strict Grounding Verification against query and sub-intents (Atomic vs Compound)
        refusal_markers = [
            "مش مسجل", "غير مسجل", "مش مسجلة", "غير مسجلة", "معنديش", "لا أملك",
            "not recorded", "do not have", "don't have", "not in my memory", "not stored"
        ]

        from app.services.memory.query_decomposer import QueryDecomposer
        atomic_subs = QueryDecomposer.get_atomic_subqueries(query)

        if len(atomic_subs) > 1:
            # Multi-intent / Compound question verification
            missing_subs: List[str] = []
            covered_subs: List[str] = []

            for sq in atomic_subs:
                subj = QueryDecomposer.clean_subject(sq)
                subj_tokens = [
                    w for w in re.findall(r"[\w\d]+", normalize_masri_orthography(subj).lower())
                    if len(w) >= 2 and w not in cls.QUESTION_STOPWORDS
                ]
                direct_match = bool(subj_tokens and any(t in norm_context for t in subj_tokens))
                concept_match = False
                if not direct_match:
                    for bundle_name, terms in cls.COLLOQUIAL_CONCEPT_BUNDLES.items():
                        if any(t in sq.lower() for t in terms) and any(t in norm_context for t in terms):
                            concept_match = True
                            break

                sq_names = QueryDecomposer.extract_mentioned_person_names(sq)
                sq_names_grounded = True
                if sq_names:
                    sq_names_grounded = any(name in norm_context for name in sq_names)

                if (direct_match or concept_match) and sq_names_grounded:
                    covered_subs.append(subj)
                else:
                    missing_subs.append(subj)

            if not covered_subs and not is_greeting and not has_action:
                logger.info(f"FactVerifier: All sub-intents {missing_subs} absent from context -> Enforcing refusal.")
                return default_refusal

            if missing_subs:
                logger.info(f"FactVerifier: Compound query has missing sub-intents {missing_subs}. Sanitizing response.")
                response = cls._sanitize_compound_response(
                    response=response,
                    missing_subjects=missing_subs,
                    is_arabic=is_arabic,
                    refusal_markers=refusal_markers,
                )

            # Ensure complete coverage: if model omitted any covered entity, automatically complete it
            response = cls._complete_omitted_covered_facts(
                response=response,
                atomic_subs=atomic_subs,
                retrieved_memories=retrieved_memories,
                is_arabic=is_arabic,
            )
            return response
        else:
            # Atomic single-intent query verification
            has_refusal = any(m in norm_response for m in refusal_markers)
            q_words = [
                w for w in re.findall(r"[\w\d]+", normalize_masri_orthography(query).lower())
                if len(w) >= 2 and w not in cls.QUESTION_STOPWORDS
            ]
            q_stems: set[str] = set()
            for w in q_words:
                q_stems.add(w)
                if w.startswith("ال") and len(w) > 3:
                    q_stems.add(w[2:])

            from app.services.memory.query_decomposer import QueryDecomposer
            mentioned_names = QueryDecomposer.extract_mentioned_person_names(query)
            names_grounded = True
            if mentioned_names:
                names_grounded = any(name in norm_context for name in mentioned_names)

            # Strict Inquiry Aspect Grounding (Age, Job, Location, Hobby, Schedule, Residence, Clothing, Contact):
            # If the user asks about a specific aspect (e.g. age, job, residence), the context MUST contain that specific aspect.
            # Never allow substituting an answer for a different question (e.g. job for age, or watch location for job).
            if not has_refusal and not is_greeting and not has_action:
                inquiry_aspect = QueryDecomposer.get_inquiry_aspect(query)
                if inquiry_aspect:
                    has_aspect_in_ctx = any(QueryDecomposer.fact_has_aspect(mem, inquiry_aspect) for mem in retrieved_memories) or QueryDecomposer.fact_has_aspect(norm_context, inquiry_aspect)
                    if not has_aspect_in_ctx:
                        logger.info(f"FactVerifier: Query inquired aspect '{inquiry_aspect}', but context lacks this aspect -> Enforcing refusal.")
                        return default_refusal

                # Strict Subject Item Grounding:
                # If the query inquired about a specific subject item (e.g. قلم), the context AND response
                # MUST contain that requested item. NEVER permit answering about a watch when asked about a pen!
                target_p_name = QueryDecomposer.extract_target_persona_name(query)
                query_items = QueryDecomposer.extract_subject_items(query, target_p_name)
                if query_items:
                    has_item_in_ctx = False
                    for m in retrieved_memories:
                        m_tokens = set(re.findall(r"[\w\d]+", normalize_masri_orthography(m).lower()))
                        for w in list(m_tokens):
                            if w.startswith("ال") and len(w) > 3:
                                m_tokens.add(w[2:])
                        if query_items & m_tokens:
                            has_item_in_ctx = True
                            break
                    if not has_item_in_ctx:
                        logger.info(f"FactVerifier: Query inquired item(s) {query_items}, but context lacks this item -> Enforcing refusal.")
                        return default_refusal

                    # Verify that response itself actually mentions the queried item (unless past-tense inquiry with natural pronoun elision)
                    resp_words = set(re.findall(r"[\w\d]+", norm_response))
                    for w in list(resp_words):
                        if w.startswith("ال") and len(w) > 3:
                            resp_words.add(w[2:])
                    if not (query_items & resp_words) and not QueryDecomposer.is_past_inquiry(query):
                        logger.info(f"FactVerifier: Response substituted/omitted queried item {query_items} -> Enforcing refusal.")
                        return default_refusal

            if q_stems and not has_refusal:
                direct_overlap = any(s in norm_context for s in q_stems)
                concept_overlap = False
                if not direct_overlap:
                    # Check semantic concept bundles
                    for bundle_name, terms in cls.COLLOQUIAL_CONCEPT_BUNDLES.items():
                        q_has_bundle = any(any(t in s for t in terms) for s in q_stems) or any(t in query.lower() for t in terms)
                        if q_has_bundle:
                            ctx_has_bundle = any(t in norm_context for t in terms)
                            if ctx_has_bundle:
                                concept_overlap = True
                                break

                overlap_with_ctx = (direct_overlap or concept_overlap) and names_grounded
                if not overlap_with_ctx and not is_greeting and not has_action:
                    logger.info(f"FactVerifier: Query content terms {q_stems} (names_grounded={names_grounded}) not grounded in retrieved context and model did not refuse -> Enforcing refusal.")
                    return default_refusal

            # Prune any unsolicited secondary clauses for single-intent queries (only if not a multi-hop relational query)
            rel_info = QueryDecomposer.decompose_multihop_relational(query)
            if not rel_info:
                response = cls._prune_unsolicited_clauses(response, query)
                # Multi-persona completeness: If query did not specify a target persona, but retrieved memories
                # contain distinct personas (e.g. Mazen and Ahmed for 'الكراسة فين؟' or 'الساعة فين؟'), ensure all covered personas are included with natural annexation.
                if not QueryDecomposer.extract_target_persona_name(query) and len(retrieved_memories) > 1:
                    norm_r = normalize_masri_orthography(response).lower()
                    distinct_personas = []
                    for mem in retrieved_memories:
                        m_names = QueryDecomposer.extract_mentioned_person_names(mem)
                        if m_names:
                            distinct_personas.append((m_names, mem))

                    if len(distinct_personas) >= 2:
                        covered_count = sum(1 for m_names, _ in distinct_personas if any(n in norm_r for n in m_names))
                        if covered_count < len(distinct_personas):
                            logger.info(f"FactVerifier: Multi-persona query lacked explicit owner attribution ({covered_count}/{len(distinct_personas)}). Rebuilding formatted answer.")
                            gesture_m = re.search(r'(\s*(?:\[[\w:\-]+\]|[\U00010000-\U0010ffff]|[\u2600-\u27bf])+\s*)$', response)
                            trailing_g = gesture_m.group(1).strip() if gesture_m else "[happy]"
                            formatted_parts = [m.strip(" .،,") for _, m in distinct_personas]
                            rebuilt = "، و".join(formatted_parts) + "."
                            response = f"{rebuilt} {trailing_g}"
                    else:
                        for mem in retrieved_memories:
                            mem_names = QueryDecomposer.extract_mentioned_person_names(mem)
                            if mem_names and not any(n in norm_r for n in mem_names):
                                logger.info(f"FactVerifier: Multi-persona query omitted facts for {mem_names}. Completing with: {mem}")
                                gesture_m = re.search(r'(\s*(?:\[[\w:\-]+\]|[\U00010000-\U0010ffff]|[\u2600-\u27bf])+\s*)$', response)
                                trailing_g = gesture_m.group(1).strip() if gesture_m else ""
                                base_r = response[:gesture_m.start()].strip() if gesture_m else response.strip()
                                base_r = re.sub(r'[.,،!\sو]+$', '', base_r).strip()
                                clean_mem = mem.strip(" .،,")
                                response = f"{base_r}، و{clean_mem}." if base_r else f"{clean_mem}."
                                if trailing_g:
                                    response = f"{response} {trailing_g}"
                                norm_r = normalize_masri_orthography(response).lower()
            else:
                # Ensure downstream attribute is completed if omitted by the LLM
                downstream_attr = rel_info["downstream_attr"]
                downstream_mem = None
                for mem in retrieved_memories:
                    if QueryDecomposer.fact_has_aspect(mem, downstream_attr) or downstream_attr in mem:
                        downstream_mem = mem.strip(" .،,")
                        break
                if downstream_mem:
                    norm_r = normalize_masri_orthography(response).lower()
                    tokens = [w for w in re.findall(r"[\w\d]+", downstream_mem) if len(w) >= 3 and w not in ["صاحب", "احمد", "أحمد", "نوعها", "شغال"]]
                    is_covered = any(t in norm_r for t in tokens)
                    if not is_covered:
                        logger.info(f"FactVerifier: Multi-hop response omitted downstream attribute. Completing with: {downstream_mem}")
                        gesture_m = re.search(r'(\s*(?:\[[\w:\-]+\]|[\U00010000-\U0010ffff]|[\u2600-\u27bf])+\s*)$', response)
                        trailing_g = gesture_m.group(1).strip() if gesture_m else ""
                        base_r = response[:gesture_m.start()].strip() if gesture_m else response.strip()
                        base_r = re.sub(r'[.,،!\sو]+$', '', base_r).strip()
                        response = f"{base_r}، و{downstream_mem}." if base_r else f"{downstream_mem}."
                        if trailing_g:
                            response = f"{response} {trailing_g}"

        return response

    @classmethod
    def _sanitize_compound_response(
        cls,
        response: str,
        missing_subjects: List[str],
        is_arabic: bool,
        refusal_markers: List[str],
    ) -> str:
        """
        Sanitizes compound question responses by pruning ungrounded claims about missing sub-intents
        and appending explicit refusal clauses for them while preserving avatar emotion tags.
        """
        gesture_match = re.search(r'(\s*(?:\[[\w:\-]+\]|[\U00010000-\U0010ffff]|[\u2600-\u27bf])+\s*)$', response)
        trailing_gesture = gesture_match.group(1).strip() if gesture_match else ""
        base_resp = response[:gesture_match.start()].strip() if gesture_match else response.strip()

        clauses = re.split(r'([.،,\n]+|\s+و(?=\S)|\s+and\s+)', base_resp)
        clean_clauses: List[str] = []
        needed_refusals: List[str] = []

        norm_resp = normalize_masri_orthography(base_resp).lower()

        for subj in missing_subjects:
            norm_subj = normalize_masri_orthography(subj).lower()
            already_refused = (norm_subj in norm_resp) and any(rm in norm_resp for rm in refusal_markers)
            if not already_refused:
                needed_refusals.append(subj)

        i = 0
        while i < len(clauses):
            c = clauses[i]
            sep = clauses[i + 1] if i + 1 < len(clauses) else ""
            norm_c = normalize_masri_orthography(c).lower()

            is_hallucination = False
            for subj in missing_subjects:
                norm_subj = normalize_masri_orthography(subj).lower()
                subj_tokens = [
                    w for w in re.findall(r"[\w\d]+", norm_subj)
                    if len(w) >= 2 and w not in cls.QUESTION_STOPWORDS
                ]
                if subj_tokens and any(t in norm_c for t in subj_tokens):
                    if not any(rm in norm_c for rm in refusal_markers):
                        is_hallucination = True
                        break

            if not is_hallucination and c.strip():
                clean_clauses.append(c + sep)
            i += 2

        sanitized_base = "".join(clean_clauses).strip()
        sanitized_base = re.sub(r'[.,،!\sو]+$', '', sanitized_base).strip()

        if not sanitized_base and needed_refusals:
            return cls.REFUSAL_AR if is_arabic else cls.REFUSAL_EN

        refusal_clauses: List[str] = []
        for subj in needed_refusals:
            if is_arabic:
                refusal_clauses.append(f"لكن بخصوص {subj} فالمعلومة دي مش مسجلة عندي في الذاكرة حالياً")
            else:
                refusal_clauses.append(f"but regarding {subj}, I do not have this information recorded in my memory")

        if refusal_clauses:
            if is_arabic:
                combined = "، و".join(refusal_clauses)
                res = f"{sanitized_base}، {combined}." if sanitized_base else f"{combined}."
            else:
                combined = ", and ".join(refusal_clauses)
                res = f"{sanitized_base}, {combined}." if sanitized_base else f"{combined}."
        else:
            res = f"{sanitized_base}." if sanitized_base else ""

        if trailing_gesture:
            res = f"{res} {trailing_gesture}".strip()
        return res

    @classmethod
    def _complete_omitted_covered_facts(
        cls,
        response: str,
        atomic_subs: List[str],
        retrieved_memories: List[str],
        is_arabic: bool = True,
    ) -> str:
        """
        Guarantees complete coverage for multi-part questions:
        If the user asked about several entities and their facts are present in retrieved context,
        but the LLM omitted one or more of them from its response, this method automatically
        appends the missing verified facts from the retrieved memories.
        """
        if not response or not atomic_subs or not retrieved_memories:
            return response

        norm_resp = normalize_masri_orthography(response).lower()
        gesture_match = re.search(r'(\s*(?:\[[\w:\-]+\]|[\U00010000-\U0010ffff]|[\u2600-\u27bf])+\s*)$', response)
        trailing_gesture = gesture_match.group(1).strip() if gesture_match else ""
        base_resp = response[:gesture_match.start()].strip() if gesture_match else response.strip()
        base_resp = re.sub(r'[.,،!\sو]+$', '', base_resp).strip()

        from app.services.memory.query_decomposer import QueryDecomposer

        omitted_facts: List[str] = []
        for sq in atomic_subs:
            subj = QueryDecomposer.clean_subject(sq)
            norm_subj = normalize_masri_orthography(subj).lower()
            subj_tokens = [w for w in re.findall(r"[\w\d]+", norm_subj) if len(w) >= 2 and w not in cls.QUESTION_STOPWORDS]

            # Check if this subject is already discussed in the response
            is_mentioned = any(t in norm_resp for t in subj_tokens) if subj_tokens else (norm_subj in norm_resp)
            if not is_mentioned:
                # Find the matching memory from retrieved memories
                for mem in retrieved_memories:
                    norm_m = normalize_masri_orthography(mem).lower()
                    if subj_tokens and any(t in norm_m for t in subj_tokens):
                        clean_fact = mem.strip(" .،,")
                        if clean_fact not in omitted_facts:
                            omitted_facts.append(clean_fact)
                        break

        if omitted_facts:
            logger.info(f"FactVerifier: Automatically completed omitted facts for multi-part question: {omitted_facts}")
            if is_arabic:
                combined_omitted = "، و".join(omitted_facts)
                res = f"{base_resp}، و{combined_omitted}." if base_resp else f"{combined_omitted}."
            else:
                combined_omitted = ", and ".join(omitted_facts)
                res = f"{base_resp}, and {combined_omitted}." if base_resp else f"{combined_omitted}."
        else:
            res = f"{base_resp}." if base_resp else ""

        if trailing_gesture:
            res = f"{res} {trailing_gesture}".strip()
        return res

    @classmethod
    def _prune_unsolicited_clauses(cls, response: str, query: str) -> str:
        """
        For single-intent atomic queries, prunes any trailing or secondary clauses
        that discuss unrelated entities not requested in the query.
        """
        if not response:
            return response

        from app.services.memory.query_decomposer import QueryDecomposer
        if QueryDecomposer.is_past_inquiry(query):
            return response
        if len(QueryDecomposer.get_atomic_subqueries(query)) > 1:
            return response
        gesture_match = re.search(r'(\s*(?:\[[\w:\-]+\]|[\U00010000-\U0010ffff]|[\u2600-\u27bf])+\s*)$', response)
        trailing_gesture = gesture_match.group(1).strip() if gesture_match else ""
        base_resp = response[:gesture_match.start()].strip() if gesture_match else response.strip()

        from app.services.memory.query_decomposer import QueryDecomposer
        clean_subj = QueryDecomposer.clean_subject(query)
        norm_subj = normalize_masri_orthography(clean_subj).lower()
        subj_tokens = set(re.findall(r"[\w\d]{3,}", norm_subj))
        for w in list(subj_tokens):
            if w.startswith("ال") and len(w) > 3:
                subj_tokens.add(w[2:])

        # Split base_resp by major sentence/clause terminators
        raw_clauses = [c.strip() for c in re.split(r'[.،,\n]+|\s+و(?=[\u0600-\u06FF])', base_resp) if c.strip()]
        if len(raw_clauses) <= 1:
            return response

        kept_clauses: List[str] = []
        for c in raw_clauses:
            norm_c = normalize_masri_orthography(c).lower()
            c_tokens = set(re.findall(r"[\w\d]{3,}", norm_c))
            for w in list(c_tokens):
                if w.startswith("ال") and len(w) > 3:
                    c_tokens.add(w[2:])

            overlap = bool(subj_tokens & c_tokens)
            if not overlap:
                for bundle_name, terms in cls.COLLOQUIAL_CONCEPT_BUNDLES.items():
                    if any(t in norm_subj for t in terms) and any(t in norm_c for t in terms):
                        overlap = True
                        break

            if overlap or not kept_clauses:
                kept_clauses.append(c)

        if not kept_clauses:
            return response

        is_arabic = bool(re.search(r"[\u0600-\u06FF]", base_resp))
        joiner = "، و" if is_arabic else ", and "
        res = joiner.join(kept_clauses).strip()
        res = re.sub(r'[.,،!\sو]+$', '', res).strip()
        return f"{res}. {trailing_gesture}".strip() if trailing_gesture else f"{res}."


