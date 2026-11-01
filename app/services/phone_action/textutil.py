"""
Arabic (Egyptian) text helpers for the phone-action pipeline.

`fold()` is deliberately LENGTH-PRESERVING: every character maps to exactly one
character. That lets the planner match on the folded text and then slice the
*original* (diacritic-stripped) text at the same indices — so a message like
«ابعت لأحمد إني جاي متأخر» keeps the user's own spelling in the outgoing text.
"""

import re
from typing import List, Optional

_MARKS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")

_CHARMAP = {
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
    # Arabic-Indic and Persian digits → ASCII
    **{chr(0x0660 + i): str(i) for i in range(10)},
    **{chr(0x06F0 + i): str(i) for i in range(10)},
    # Punctuation → space (keeps indices aligned)
    "،": " ", "؟": " ", "؛": " ", "?": " ", "!": " ", ".": " ", ",": " ",
    ";": " ", ":": " ", "«": " ", "»": " ", '"': " ", "'": " ", "(": " ", ")": " ",
    "\u200f": " ", "\u200e": " ",
}
_TRANS = str.maketrans(_CHARMAP)


def strip_marks(text: str) -> str:
    """Remove tashkeel / tatweel (changes length — apply to BOTH light & norm)."""
    return _MARKS.sub("", text or "")


def fold(text: str) -> str:
    """Length-preserving fold: alef/ya/ta-marbuta unification, ASCII digits, no punctuation."""
    out = text.translate(_TRANS)
    # ASCII-only lowercase keeps the one-char-per-char invariant
    return "".join(c.lower() if c.isascii() else c for c in out)


def prepare(text: str) -> tuple[str, str]:
    """
    Return (light, norm) — same length, both trimmed identically.
    `light` is the marks-stripped original; `norm` is the folded matcher form.
    """
    light = strip_marks(text)
    norm = fold(light)
    lead = len(norm) - len(norm.lstrip())
    trail = len(norm) - len(norm.rstrip())
    end = len(norm) - trail if trail else len(norm)
    return light[lead:end], norm[lead:end]


def sanitize_free_text(text: str, max_len: int) -> str:
    """Strip control characters and collapse whitespace; bound the length."""
    cleaned = re.sub(r"[\x00-\x1f\x7f\u202a-\u202e\u2066-\u2069]", " ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_len]


def sanitize_destination(text: str, max_len: int = 80) -> str:
    """Maps/search query: also drop markup / URL-structure characters."""
    cleaned = re.sub(r"[<>{}\[\]\\|^`]", " ", sanitize_free_text(text, max_len * 2))
    return re.sub(r"\s+", " ", cleaned).strip()[:max_len]


# ── yes / no ─────────────────────────────────────────────────────────────────

_YES = {
    "ايوه", "ايوا", "ايوة", "اه", "اها", "آه", "ماشي", "تمام", "اوكي", "اوك",
    "اكيد", "طبعا", "ok", "okay", "yes", "yeah", "اتصل", "ابعت", "كلمها", "كلمه",
    "ياريت", "طيب",
}
_ACK_YES = {"خدته", "خدتو", "اخدته", "اخدتها", "خدتها", "خلصت", "خلصته", "اخدت", "خدت"}
_NO = {
    "لا", "لاا", "لأ", "لاء", "بلاش", "الغي", "الغ", "الغاء", "كنسل", "cancel", "no",
    "سيبك", "وقف", "استني", "استنى", "ثواني", "لحظه", "مش", "بطل", "خلاص",
}
_FILLER = {"يا", "توام", "روبوت", "نيبولا", "توت", "لو", "سمحت", "ممكن"}


def _tokens(text: str) -> List[str]:
    _, norm = prepare(text)
    return [t for t in norm.split() if t]


def is_no(text: str) -> bool:
    toks = _tokens(text)
    return bool(toks) and any(t in _NO for t in toks)


def is_yes(text: str, *, allow_ack: bool = False) -> bool:
    """
    A *clean* affirmative: short utterance, contains a yes-word, no no-word.
    Anything ambiguous is NOT a yes (fail closed).
    """
    toks = [t for t in _tokens(text) if t not in _FILLER]
    if not toks or len(toks) > 4:
        return False
    if any(t in _NO for t in toks):
        return False
    yes_words = _YES | (_ACK_YES if allow_ack else set())
    return any(t in yes_words for t in toks)


# ── numbers in Egyptian Arabic words (used by challenge + reminder times) ────

_UNITS = ["", "واحد", "اتنين", "تلاتة", "اربعة", "خمسة", "ستة", "سبعة", "تمانية", "تسعة"]
_TENS = ["", "عشرة", "عشرين", "تلاتين", "اربعين", "خمسين", "ستين", "سبعين", "تمانين", "تسعين"]
_TEENS = {
    10: "عشرة", 11: "احداشر", 12: "اتناشر", 13: "تلاتاشر", 14: "اربعتاشر",
    15: "خمستاشر", 16: "ستاشر", 17: "سبعتاشر", 18: "تمنتاشر", 19: "تسعتاشر",
}


def number_to_masri(n: int) -> str:
    """0..99 → Egyptian Arabic words (e.g. 43 → «تلاتة واربعين»)."""
    if n == 0:
        return "صفر"
    if 1 <= n <= 9:
        return _UNITS[n]
    if 10 <= n <= 19:
        return _TEENS[n]
    t, u = divmod(n, 10)
    if u == 0:
        return _TENS[t]
    return f"{_UNITS[u]} و{_TENS[t]}"


# word → hour value for reminder times (folded forms)
HOUR_WORDS = {
    "واحده": 1, "واحد": 1, "اتنين": 2, "تنين": 2, "تلاته": 3, "اربعه": 4,
    "خمسه": 5, "سته": 6, "سبعه": 7, "تمانيه": 8, "تسعه": 9, "عشره": 10,
    "احداشر": 11, "حداشر": 11, "اتناشر": 12,
}


def parse_int(token: str) -> Optional[int]:
    token = token.strip()
    if token.isdigit():
        return int(token)
    return HOUR_WORDS.get(token)
