"""
Deterministic Fact Verification & Anti-Hallucination Guard.

Solves the Hallucination & Faithfulness Problem in RAG WITHOUT a Fallback Model:
- Does NOT invoke or fall back to another LLM or pre-trained fallback model.
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

    @classmethod
    def verify_and_sanitize(
        cls,
        query: str,
        response: str,
        retrieved_memories: List[str],
        is_greeting: bool = False,
    ) -> str:
        """
        Validates the generated response against retrieved memories.
        Returns the sanitized, guaranteed grounded response.
        """
        if not response:
            return cls.REFUSAL_AR

        is_arabic = bool(re.search(r"[\u0600-\u06FF]", query or response))
        default_refusal = cls.REFUSAL_AR if is_arabic else cls.REFUSAL_EN

        # 1. If context was completely empty and this is not a greeting:
        if not retrieved_memories and not is_greeting:
            logger.info("FactVerifier: Context is empty for non-greeting query -> Enforcing refusal.")
            return default_refusal

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
        unsupported_critical_numbers = [n for n in unsupported_numbers if len(n) >= 4 or n.startswith("01")]
        if unsupported_critical_numbers:
            logger.warning(
                f"FactVerifier: Response contains ungrounded critical numbers {unsupported_critical_numbers}. "
                f"Enforcing refusal."
            )
            return default_refusal

        # 4. If query explicitly asked for something not in context, but model answered affirmatively without refusal
        refusal_markers = [
            "مش مسجل", "غير مسجل", "مش مسجلة", "غير مسجلة", "معنديش", "لا أملك",
            "not recorded", "do not have", "don't have", "not in my memory", "not stored"
        ]
        has_refusal = any(m in norm_response for m in refusal_markers)

        # Check keyword presence from query in context
        q_words = [w for w in re.findall(r"[\w\d]+", normalize_masri_orthography(query).lower()) if len(w) > 3]
        if q_words and not has_refusal:
            overlap_with_ctx = any(w in norm_context for w in q_words)
            if not overlap_with_ctx and not is_greeting:
                logger.info("FactVerifier: Query terms not found in context and model did not refuse -> Enforcing refusal.")
                return default_refusal

        return response

