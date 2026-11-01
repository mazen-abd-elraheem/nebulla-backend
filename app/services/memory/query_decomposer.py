"""
Query Decomposition & Multi-Hop Query Processor.

Solves the Multi-Hop Reasoning Problem in RAG:
- Single-turn RAG fails on composite or comparative questions (e.g., "What is X and who made it?").
- Decomposes complex queries into atomic search steps.
- Gathers context for each sub-intent to ensure complete information retrieval.
"""

import re
from typing import List, Set


class QueryDecomposer:
    """Decomposes compound or multi-hop user queries into atomic sub-queries."""

    SPLIT_PATTERNS_AR = [
        r"\s+(?:وكمان|وكذلك|بالإضافة إلى|بالاضافة الى|وعلاوة على ذلك)\s+",
        r"\s+(?:مقارنة بـ|مقارنة مع|وقارن بين|وقارن مع)\s+",
        r"\s+(?:وفي نفس الوقت|ويا ريت تقولي عن|واحكيلي عن|وإيه كمان عن)\s+",
        r"[،,\?؟]\s*و\s*",
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
                    p_str = p.strip().rstrip("؟?.,،")
                    if len(p_str) >= 4 and p_str not in sub_queries:
                        sub_queries.append(p_str)
                is_split = True
                break

        # Check English patterns if not split
        if not is_split:
            for pat in cls.SPLIT_PATTERNS_EN:
                parts = re.split(pat, clean_q, flags=re.IGNORECASE)
                if len(parts) > 1:
                    for p in parts:
                        p_str = p.strip().rstrip("؟?.,،")
                        if len(p_str) >= 4 and p_str not in sub_queries:
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

