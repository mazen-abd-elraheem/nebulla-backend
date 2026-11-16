"""
Hybrid Memory Extractor for Onboarding Questionnaire.
Transforms Akinator-style answers into structured, high-value long-term RAG memories.
Supports both deterministic Rule-Based Extraction and LLM Synthesis.
"""

from typing import Any, Dict, List, Optional
from app.core.logger import get_logger
from app.services.onboarding.question_bank import get_question_by_id, QUESTION_BANK
from app.services.onboarding.akinator_engine import AkinatorEngine

logger = get_logger(__name__)


class MemoryExtractor:
    """Extracts factual Egyptian/Arabic memories from questionnaire answers."""

    @classmethod
    def extract_via_rules(cls, answers: Dict[str, Any]) -> tuple[List[str], Dict[str, float]]:
        """
        Deterministic rule-based extraction.
        Evaluates answers against question bank rules and calculates dimension scores.
        """
        extracted_facts: List[str] = []
        dimension_scores: Dict[str, float] = {
            "work_tech": 0.0,
            "routine": 0.0,
            "social": 0.0,
            "preferences": 0.0,
            "mindset": 0.0,
        }

        # Index questions by ID and index for robust matching
        by_id = {q.id: q for q in QUESTION_BANK}
        by_index = {q.index: q for q in QUESTION_BANK}

        for key, raw_val in answers.items():
            # Resolve question
            q = by_id.get(str(key))
            if not q:
                # Try integer key
                try:
                    q = by_index.get(int(key))
                except (ValueError, TypeError):
                    pass

            if not q:
                continue

            weight = AkinatorEngine.parse_answer_weight(raw_val)
            if q.dimension in dimension_scores:
                dimension_scores[q.dimension] += weight

            # Affirmative fact ("نعم" / "في الغالب نعم")
            if weight >= 0.70 and q.affirmative_fact:
                if q.affirmative_fact not in extracted_facts:
                    extracted_facts.append(q.affirmative_fact)

            # Negative fact ("لا" / "في الغالب لا")
            elif weight <= -0.70 and q.negative_fact:
                if q.negative_fact not in extracted_facts:
                    extracted_facts.append(q.negative_fact)

        return extracted_facts, dimension_scores

    @classmethod
    async def extract_via_llm(
        cls,
        answers: Dict[str, Any],
        user_name: str,
        rule_facts: List[str],
    ) -> List[str]:
        """
        Deep LLM contextual synthesis.
        Takes user answers and rule facts, and prompts the LLM to synthesize cohesive summary memories.
        """
        if not rule_facts:
            return []

        prompt = (
            f"بصفتك الذكاء الاصطناعي المركزي للروبوت نيبولا، قام المستخدم '{user_name}' بالإجابة على استبيان التخصيص.\n"
            f"إليك الحقائق الأولية المستخلصة من إجاباته:\n"
            + "\n".join(f"- {f}" for f in rule_facts[:15])
            + f"\n\nالمطلوب: صغ 2 إلى 4 ذكريات ملخصة مركزة وشاملة بلهجة مصرية راقية تسجل شخصية {user_name} وعاداته في الذاكرة طويلة المدى، كل ذكرى في سطر منفصل يبدأ بـ *."
        )

        try:
            from app.providers.llm.factory import get_llm_provider
            from app.core.config import settings

            provider = get_llm_provider(settings.LLM_PROVIDER)
            response = await provider.generate(prompt=prompt, context=[])
            lines = [line.strip().lstrip("*-• ").strip() for line in response.split("\n") if line.strip()]
            synthesized = [l for l in lines if len(l) >= 10 and not l.startswith("بصفتك") and not l.startswith("إليك")]
            return synthesized[:4]
        except Exception as e:
            logger.warning(f"LLM memory extraction notice (fallback to rule facts): {e}")
            return []

    @classmethod
    async def hybrid_extract(
        cls,
        answers: Dict[str, Any],
        user_name: str = "المستخدم",
        use_llm: bool = True,
    ) -> Dict[str, Any]:
        """
        Run hybrid extraction:
        1. Deterministic rules -> base facts (sub-10ms).
        2. LLM synthesis -> cohesive summary memories.
        3. Determine personality archetype.
        """
        rule_facts, dim_scores = cls.extract_via_rules(answers)
        archetype = AkinatorEngine.determine_archetype(dim_scores)

        # Base user identity anchor
        all_memories: List[str] = [
            f"بروفايل {user_name}: {archetype}.",
        ]
        all_memories.extend(rule_facts)

        if use_llm and len(rule_facts) >= 3:
            llm_facts = await cls.extract_via_llm(answers, user_name, rule_facts)
            for lf in llm_facts:
                if lf not in all_memories:
                    all_memories.append(lf)

        return {
            "user_name": user_name,
            "archetype": archetype,
            "dimension_scores": dim_scores,
            "memories_count": len(all_memories),
            "memories": all_memories,
        }
