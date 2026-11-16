"""
Akinator Decision Tree & Profiling Engine.
Manages question presentation, entropy-based ordering, and response scoring.
"""

from typing import Any, Dict, List, Optional
from app.services.onboarding.question_bank import (
    AkinatorQuestion,
    get_all_questions,
    get_core_questions,
    get_questions_by_dimension,
    get_question_by_id,
)

# Standard answer weight multipliers
ANSWER_WEIGHTS = {
    "نعم": 1.0,
    "yes": 1.0,
    "true": 1.0,
    "1": 1.0,
    "في الغالب نعم": 0.75,
    "mostly_yes": 0.75,
    "لا أعلم / محايد": 0.0,
    "neutral": 0.0,
    "don't know": 0.0,
    "في الغالب لا": -0.75,
    "mostly_no": -0.75,
    "لا": -1.0,
    "no": -1.0,
    "false": -1.0,
    "0": -1.0,
}


class AkinatorEngine:
    """Decision Tree and scoring engine for Onboarding Questions."""

    @classmethod
    def get_questions(
        cls,
        mode: str = "full",
        dimension: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve questionnaire items:
        - mode='quick': 15 core questions
        - mode='full': all 50 questions
        - dimension: filter by specific dimension
        """
        if dimension:
            questions = get_questions_by_dimension(dimension)
        elif mode == "quick":
            questions = get_core_questions()
        else:
            questions = get_all_questions()

        return [
            {
                "id": q.id,
                "index": q.index,
                "dimension": q.dimension,
                "text": q.text,
                "subtitle": q.subtitle,
                "is_core": q.is_core,
                "options": q.options,
            }
            for q in questions
        ]

    @classmethod
    def parse_answer_weight(cls, answer: Any) -> float:
        """Parse raw user answer into numeric weight between -1.0 and 1.0."""
        if answer is None:
            return 0.0
        val = str(answer).strip().lower()
        return ANSWER_WEIGHTS.get(val, 0.0)

    @classmethod
    def determine_archetype(cls, dimension_scores: Dict[str, float]) -> str:
        """
        Deduce user personality archetype based on dimension score polarities.
        """
        wt = dimension_scores.get("work_tech", 0.0)
        rt = dimension_scores.get("routine", 0.0)
        sc = dimension_scores.get("social", 0.0)
        pf = dimension_scores.get("preferences", 0.0)
        ms = dimension_scores.get("mindset", 0.0)

        traits = []
        if wt > 1.5:
            traits.append("مطور شغوف بالتكنولوجيا والذكاء الاصطناعي")
        elif wt < -1.0:
            traits.append("شخصية إدارية ميدانية")

        if rt > 1.5:
            traits.append("إنتاجي ليلي بتركيز فائق")
        elif rt < -1.0:
            traits.append("صباحي النشاط ومنضبط المواعيد")

        if sc > 1.5:
            traits.append("مباشر ويفضل النبرة المصرية العفوية")
        if ms > 1.5:
            traits.append("طموح ريادي وعقلية هندسية تحليلية")

        if not traits:
            return "مستكشف رقمي متوازن ومتعدد الاهتمامات"
        return " • ".join(traits)
