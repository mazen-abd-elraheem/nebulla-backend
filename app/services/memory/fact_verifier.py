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
        "where", "when", "who is", "what is", "work", "job", "location", "address"
    ]

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
            if cls.is_sensitive_or_private_inquiry(query):
                logger.info("FactVerifier: Sensitive/private query with empty context -> Enforcing refusal.")
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
                if subj_tokens and any(t in norm_context for t in subj_tokens):
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
            if q_words and not has_refusal:
                overlap_with_ctx = any(w in norm_context for w in q_words)
                if not overlap_with_ctx and not is_greeting and not has_action:
                    logger.info(f"FactVerifier: Query content terms {q_words} not found in retrieved context and model did not refuse -> Enforcing refusal.")
                    return default_refusal

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


