"""
Cross-Encoder & Deep Alignment Re-ranker.

Solves the Poor Ranking & Noise Problem in RAG:
- Standard Bi-Encoder vector search retrieves candidate chunks using cosine similarity.
- The Reranker analyzes cross-token interactions between Query and Document (Cross-Attention or Deep Lexical Alignment).
- Filters out irrelevant or low-signal chunks, ensuring only the top-K highest-value chunks reach the LLM.
"""

import math
import re
from typing import List, Tuple, Dict, Any, Optional

from app.core.logger import get_logger
from app.utils.masri_normalizer import normalize_masri_orthography

logger = get_logger(__name__)


class CrossReranker:
    """
    Two-stage Re-ranker:
    1. Uses local neural Cross-Encoder model if available.
    2. Deep Alignment Cross-Scorer (exact phrase, positional proximity, keyword density) as zero-latency local fallback.
    """

    _neural_model = None
    _init_attempted = False

    @classmethod
    def _get_neural_model(cls):
        if cls._init_attempted:
            return cls._neural_model
        cls._init_attempted = True
        try:
            from sentence_transformers import CrossEncoder  # type: ignore[import]
            # Try to load local cached cross encoder or lightweight reranker
            model = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2", max_length=512)
            cls._neural_model = model
            logger.info("Loaded CrossEncoder model successfully for RAG reranking.")
        except Exception:
            cls._neural_model = None
        return cls._neural_model

    @classmethod
    def compute_alignment_score(cls, query: str, document: str) -> float:
        """
        Calculates cross-attention surrogate score:
        - Exact continuous sub-sequence matching (Phrase score).
        - Term proximity (distance between query terms in document).
        - Density & coverage of non-stopword tokens.
        """
        if not query or not document:
            return 0.0

        q_clean = normalize_masri_orthography(query).lower().strip()
        d_clean = normalize_masri_orthography(document).lower().strip()

        # 1. Exact phrase match
        if q_clean in d_clean:
            phrase_bonus = 0.4
        else:
            phrase_bonus = 0.0

        # 2. Tokenize and extract significant terms
        q_tokens = [w for w in re.findall(r"[\w\d]+", q_clean) if len(w) >= 2]
        d_tokens = [w for w in re.findall(r"[\w\d]+", d_clean) if len(w) >= 2]

        if not q_tokens or not d_tokens:
            return phrase_bonus

        matches: List[int] = []
        matched_tokens = set()

        for idx, dt in enumerate(d_tokens):
            for qt in q_tokens:
                if qt == dt or (len(qt) > 3 and qt in dt) or (len(dt) > 3 and dt in qt):
                    matches.append(idx)
                    matched_tokens.add(qt)

        coverage = len(matched_tokens) / len(set(q_tokens))
        if coverage == 0.0:
            return 0.0

        # 3. Term proximity (calculate dispersion of matches)
        proximity_score = 0.0
        if len(matches) > 1:
            sorted_m = sorted(matches)
            spans = [sorted_m[i + 1] - sorted_m[i] for i in range(len(sorted_m) - 1)]
            avg_span = sum(spans) / len(spans)
            # Smaller average span means matching words are clustered together in the same sentence
            proximity_score = max(0.0, 1.0 - (avg_span / max(len(d_tokens), 10)))

        # Composite score
        final_score = (coverage * 0.5) + (proximity_score * 0.25) + phrase_bonus
        return min(1.0, final_score)

    @classmethod
    def rerank(
        cls,
        query: str,
        candidates: List[Tuple[float, Any, str]],  # (initial_score, item, text)
        top_k: int = 5,
    ) -> List[Tuple[float, Any, str]]:
        """
        Rerank a list of candidates:
        Each candidate is a tuple (initial_score, item_object, text_content).
        Returns top_k sorted candidates with recalculated re-ranking scores.
        """
        if not candidates:
            return []

        neural = cls._get_neural_model()

        reranked: List[Tuple[float, Any, str]] = []

        if neural is not None:
            try:
                pairs = [[query, text] for _, _, text in candidates]
                scores = neural.predict(pairs)
                for (init_score, item, text), n_score in zip(candidates, scores):
                    # Combine initial retrieval score + neural cross-encoder score
                    combined = (float(n_score) * 0.7) + (init_score * 0.3)
                    reranked.append((combined, item, text))
            except Exception as e:
                logger.warning(f"Neural reranker prediction failed: {e}. Falling back to alignment cross-scorer.")
                reranked = []

        if not reranked:
            for init_score, item, text in candidates:
                align_score = cls.compute_alignment_score(query, text)
                # Combine original retrieval score with deep alignment score
                combined = (align_score * 0.6) + (init_score * 0.4)
                reranked.append((combined, item, text))

        # Sort descending by rerank score
        reranked.sort(key=lambda x: x[0], reverse=True)
        return reranked[:top_k]

