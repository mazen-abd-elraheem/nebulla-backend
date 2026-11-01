"""
RandomChallengeService — Level-2 anti-replay / anti-clone challenge
(benefits_section.docx §14.3 step 4).

The robot speaks a fresh random phrase («قول: تلاتة وأربعين قمر أزرق») and the
user must repeat it. A pre-recorded clip of the owner can't contain a phrase that
did not exist when it was recorded, and a pre-built VoiceTut clone must be driven
live. Per the doc this raises the bar, it does NOT make spoofing impossible —
which is why Level 3 adds an out-of-band confirmation.

Randomness comes from `secrets` (CSPRNG), never `random`.
"""

import difflib
import secrets
import time
from dataclasses import dataclass, field
from typing import Callable

from app.core.config import settings
from app.services.phone_action.textutil import fold, number_to_masri, prepare

_NOUNS = [
    "قمر", "نجمة", "سمكة", "شجرة", "كتاب", "عصفور", "جمل", "وردة",
    "مفتاح", "سحابة", "فراشة", "جبل", "قلم", "كوباية", "تفاحة", "مركب",
]
_COLORS = ["أزرق", "أحمر", "أخضر", "أصفر", "أبيض", "أسود", "بنفسجي", "برتقالي"]
# 21..99 excluding multiples of ten → 72 numbers × 16 nouns × 8 colours ≈ 9.2k phrases
_NUMBERS = [n for n in range(21, 100) if n % 10 != 0]


@dataclass
class Challenge:
    phrase: str
    issued_at: float
    expires_at: float
    attempts: int = 0
    max_attempts: int = 2
    _folded: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        self._folded = _canon(self.phrase)

    @property
    def spoken(self) -> str:
        return f"قول: {self.phrase}"


def _canon(text: str) -> str:
    """Canonical comparison form: folded, digits→words, filler «قول» removed."""
    _, norm = prepare(text)
    out = []
    for tok in norm.split():
        if tok.isdigit() and len(tok) <= 2:
            out.append(fold(number_to_masri(int(tok))))
        else:
            out.append(tok)
    if out and out[0] == "قول":
        out = out[1:]
    return " ".join(out)


class RandomChallengeService:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock

    def issue(self) -> Challenge:
        number = number_to_masri(secrets.choice(_NUMBERS))
        phrase = f"{number} {secrets.choice(_NOUNS)} {secrets.choice(_COLORS)}"
        now = self._clock()
        return Challenge(
            phrase=phrase,
            issued_at=now,
            expires_at=now + settings.CHALLENGE_TTL_SECONDS,
            max_attempts=settings.CHALLENGE_MAX_ATTEMPTS,
        )

    def is_expired(self, ch: Challenge) -> bool:
        return self._clock() >= ch.expires_at

    @staticmethod
    def text_matches(ch: Challenge, transcript: str) -> bool:
        """Does the STT transcript repeat the challenge phrase (tolerating STT noise)?"""
        got = _canon(transcript)
        if not got:
            return False
        ratio = difflib.SequenceMatcher(None, ch._folded, got).ratio()
        return ratio >= settings.CHALLENGE_TEXT_MATCH_RATIO
