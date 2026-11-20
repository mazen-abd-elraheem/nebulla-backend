"""
Nebula Compass (بوصلة نيبولا) Decision Tree & Profiling Engine.
Manages question presentation, balanced 5-dimension selection, response scoring,
and archetype determination for the user's digital twin.
"""

from typing import Any, Dict, List, Optional
from app.services.onboarding.compass_question_bank import (
    CompassQuestion,
    get_all_questions,
    get_core_questions,
    get_balanced_questions,
    get_questions_by_dimension,
    get_question_by_id,
)

# Standard answer weight multipliers (5-point scale)
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


class NebulaCompassEngine:
    """Decision Tree and scoring engine for Nebula Compass (بوصلة نيبولا)."""

    @classmethod
    def get_questions(
        cls,
        mode: str = "balanced",
        dimension: Optional[str] = None,
        per_dimension: int = 2,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve questionnaire items:
        - mode='balanced' (Default): Picks 2 to 3 questions per dimension (10-15 questions total)
        - mode='quick': 15 core questions
        - mode='full': all 50 questions
        - dimension: filter by specific dimension
        """
        if dimension:
            questions = get_questions_by_dimension(dimension)
        elif mode == "balanced":
            # 2 to 3 questions per dimension (default 2 or 3)
            questions = get_balanced_questions(per_dimension=per_dimension)
        elif mode == "quick":
            questions = get_core_questions()
        elif mode == "full":
            questions = get_all_questions()
        else:
            # Fallback to balanced
            questions = get_balanced_questions(per_dimension=per_dimension)

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
        if wt > 1.2:
            traits.append("مطور شغوف بالتكنولوجيا والذكاء الاصطناعي")
        elif wt < -1.0:
            traits.append("شخصية إدارية وميدانية")

        if rt > 1.2:
            traits.append("إنتاجي ليلي بتركيز فائق")
        elif rt < -1.0:
            traits.append("صباحي النشاط ومنضبط المواعيد")

        if sc > 1.2:
            traits.append("مباشر ويفضل النبرة المصرية العفوية")
        elif sc < -1.0:
            traits.append("دبلوماسي ويفضل الأسلوب المهني الرسمي")

        if pf > 1.2:
            traits.append("يفضل بيئات العمل الهادئة والمستقرة")

        if ms > 1.2:
            traits.append("طموح ريادي وعقلية هندسية تحليلية")

        if not traits:
            return "مستكشف رقمي متوازن ومتعدد الاهتمامات"
        return " • ".join(traits)
