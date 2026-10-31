"""
BM25 Okapi Retrieval Engine — tailored for Arabic (Egyptian Masri) and English.

Solves the Lexical/Keyword failure mode of pure Vector Embeddings:
- Accurately matches exact names, serial numbers, codes, dates, and domain jargon.
- Implements Okapi BM25 scoring with document length normalization (k1=1.5, b=0.75).
- Integrates Arabic prefix/suffix stemming and dialect normalization.
"""

import math
import re
from typing import List, Dict, Set, Tuple, Any, Optional

from app.utils.masri_normalizer import normalize_masri_orthography


class ArabicBM25Tokenizer:
    """Specialized tokenizer with Egyptian Masri normalization and morphological stemming."""

    STOPWORDS_AR: Set[str] = {
        "في", "من", "على", "إلى", "الى", "عن", "مع", "هذا", "هذه", "ذلك", "تلك",
        "هو", "هي", "هم", "هن", "انتم", "أنتم", "نحن", "أنا", "انا",
        "ان", "أن", "انها", "أنها", "انه", "أنه", "كان", "كانت", "يكون", "تكون",
        "ما", "ماذا", "متى", "اين", "أين", "كيف", "كم", "هل", "لماذا", "ايه", "إيه",
        "التي", "الذي", "الذين", "اللاتي", "كل", "بعض", "غير", "حيث", "ثم", "او", "أو",
        "لو", "إذا", "اذا", "يا", "بس", "علشان", "عشان", "عايز", "عايزة", "عاوز",
    }

    STOPWORDS_EN: Set[str] = {
        "a", "an", "the", "in", "on", "at", "for", "to", "of", "with", "by",
        "is", "are", "was", "were", "be", "been", "being",
        "and", "or", "but", "if", "then", "so", "that", "this", "these", "those",
        "it", "its", "you", "your", "he", "his", "she", "her", "they", "their",
    }

    @classmethod
    def tokenize(cls, text: str) -> List[str]:
        if not text:
            return []

        # 1. Masri Orthography normalization
        norm = normalize_masri_orthography(text).lower()
        norm = norm.replace("نيبيولا", "نيبولا").replace("nebula", "نيبولا")

        # 2. Extract words
        words = re.findall(r"[\w\d]+", norm)
        tokens: List[str] = []

        for w in words:
            if w in cls.STOPWORDS_AR or w in cls.STOPWORDS_EN:
                continue

            tokens.append(w)

            # Arabic Compound Prefix stemming (بال، وال، كال، فال، لل)
            base = w
            if len(base) > 4 and base.startswith(("بال", "وال", "كال", "فال")):
                tokens.append(base[1:])  # e.g. البايثون
                tokens.append(base[3:])  # e.g. بايثون
                base = base[3:]
            elif len(base) > 4 and base.startswith("لل"):
                tokens.append(base[2:])
                base = base[2:]
            elif len(base) > 3 and base.startswith("ال"):
                tokens.append(base[2:])
                base = base[2:]
            elif len(base) > 3 and base[0] in ("و", "ب", "ل", "ف", "ك"):
                tokens.append(base[1:])
                base = base[1:]

            # Arabic Suffix stemming (ات، ين، ون، ان، ية، ك، ي، نا، ها، هم، كم)
            for suffix in ("ات", "ين", "ون", "ية", "ان", "نا", "ها", "هم", "كم"):
                if len(base) > 4 and base.endswith(suffix):
                    tokens.append(base[:-len(suffix)])
                    break

        return tokens


class BM25Okapi:
    """
    Okapi BM25 Ranking Function.
    Calculates exact TF-IDF with document length normalization.
    """

    def __init__(self, corpus: List[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_lengths: List[int] = []
        self.avg_doc_len: float = 0.0
        self.doc_freqs: List[Dict[str, int]] = []
        self.idf: Dict[str, float] = {}

        if self.corpus_size > 0:
            self._fit(corpus)

    def _fit(self, corpus: List[str]) -> None:
        nd: Dict[str, int] = {}
        total_len = 0

        for doc in corpus:
            tokens = ArabicBM25Tokenizer.tokenize(doc)
            doc_len = len(tokens)
            self.doc_lengths.append(doc_len)
            total_len += doc_len

            frequencies: Dict[str, int] = {}
            for t in tokens:
                frequencies[t] = frequencies.get(t, 0) + 1
            self.doc_freqs.append(frequencies)

            for t in frequencies.keys():
                nd[t] = nd.get(t, 0) + 1

        self.avg_doc_len = total_len / self.corpus_size if self.corpus_size > 0 else 0.0

        # Calculate Robertson-Spärck Jones IDF with smoothing
        for term, freq in nd.items():
            self.idf[term] = math.log(
                (self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0
            )

    def get_scores(self, query: str) -> List[float]:
        """Compute BM25 scores for all documents in the corpus for the query."""
        if self.corpus_size == 0:
            return []

        q_tokens = ArabicBM25Tokenizer.tokenize(query)
        scores = [0.0] * self.corpus_size

        if not q_tokens or self.avg_doc_len == 0.0:
            return scores

        for q in q_tokens:
            q_idf = self.idf.get(q)
            if q_idf is None:
                continue

            for idx in range(self.corpus_size):
                tf = self.doc_freqs[idx].get(q, 0)
                if tf == 0:
                    continue

                doc_len = self.doc_lengths[idx]
                numerator = tf * (self.k1 + 1.0)
                denominator = tf + self.k1 * (1.0 - self.b + self.b * (doc_len / self.avg_doc_len))
                scores[idx] += q_idf * (numerator / denominator)

        # Normalize scores to 0.0 - 1.0 range
        max_s = max(scores) if scores else 0.0
        if max_s > 0:
            scores = [s / max_s for s in scores]

        return scores
