"""
Egyptian Arabic (Masri) Dialect & Phonetic Normalizer + Code-Switching Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Preprocesses text for VoiceTut-TTS speech synthesis:
  1. Full Egyptian Arabic normalization for numbers, currencies, dates, times, and abbreviations.
  2. Solves Masri + English code-switching token collision:
     - Separates Arabic definite article prefixes (ال, الـ, بالـ, للـ) from English words ("الID" -> "ال ID").
     - Inserts breath/pause marks (comma "،") after inline English words before Arabic phrases.
  3. Replaces stiff Fusha system phrases with colloquial Masri or adds explicit Tashkeel ("بِالعَامِّيَّة المَصْرِيَّة").
  4. Preserves Egyptian phonetic contractions (علشان, دلوقتي, إزاي, كده, عاوز).
  5. Strips LLM thinking tags (<think>...</think>) and action commands before voice synthesis.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- regex patterns
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_ACTION_TAG_RE = re.compile(r"\[(?:action:|gesture:|cmd:)?([\w\u0600-\u06FF]+)(?::([^\]]+))?\]", re.IGNORECASE)
_BRACKET_TAG_RE = re.compile(r"\[[\w\u0600-\u06FF\s:_\-]+\]")
_TATWEEL_RE = re.compile(r"\u0640+")
_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")
_MULTISPACE_RE = re.compile(r"\s+")

# --------------------------------------------------------------------------- digits & numbers (Egyptian)
ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"
ASCII_DIGITS = "0123456789"
_AR2ASCII = {ord(a): d for a, d in zip(ARABIC_INDIC, ASCII_DIGITS)}

_ONES = ["", "وَاحِد", "اِتْنِين", "تَلَاتَة", "أَرْبَعَه", "خَمْسَه", "سِتَّه", "سَبْعَه", "تَمَانْيَه", "تِسْعَه"]
_TEENS = [
    "عَشَرَه", "حِدَاشَر", "اِتْنَاشَر", "تَلاتَّاشّر", "أَرْبَعْتَاشَر", "خَمَسْتَاشَر",
    "سِتَّاشَر", "سَبَعْتَاشَر", "تَمَنْتَاشَر", "تِسَعْتَاشَر"
]
_TENS = ["", "عَشَرَه", "عِشْرين", "تلاتين", "أَرْبِعين", "خَمْسِين", "سِتِّين", "سَبْعين", "تَمانين", "تِسعين"]
_HUNDREDS = [
    "", "مِية", "مِتِين", "تُلْتُمِية", "رُبْعُمِية", "خُمْسُمِية",
    "سُتُّمِية", "سُبْعُمِية", "تُمْنُمِية", "تُسْعُمِية"
]
_SCALES = [(1_000_000_000, "مليار"), (1_000_000, "مليون"), (1_000, "ألف")]


def _three_digits_to_words(n: int) -> str:
    """0..999 -> Egyptian Arabic words."""
    parts: List[str] = []
    h, rem = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if rem:
        if rem < 10:
            parts.append(_ONES[rem])
        elif rem < 20:
            parts.append(_TEENS[rem - 10])
        else:
            t, o = divmod(rem, 10)
            parts.append((_ONES[o] + " و" + _TENS[t]) if o else _TENS[t])
    return " و".join(parts)


def number_to_arabic_words(n: int) -> str:
    """Convert an integer to colloquial Egyptian Arabic words."""
    if n == 0:
        return "صفر"
    if n < 0:
        return "سالب " + number_to_arabic_words(-n)
    words: List[str] = []
    for value, name in _SCALES:
        if n >= value:
            count, n = divmod(n, value)
            if count == 1:
                words.append(name)
            elif count == 2:
                words.append(name + "ين" if name == "ألف" else "اتنين " + name)
            elif count <= 10:
                words.append(_three_digits_to_words(count) + " " + ("آلاف" if name == "ألف" else name))
            else:
                words.append(_three_digits_to_words(count) + " " + name)
    if n:
        words.append(_three_digits_to_words(n))
    return " و".join(w for w in words if w)


# --------------------------------------------------------------------------- time (colloquial Egyptian)
_HOUR_FEM = {
    1: "وَاحْدَه", 2: "اتنين", 3: "تَلَاتَة", 4: "أَرْبَعَه", 5: "خَمْسَه", 6: "سِتَّه",
    7: "سَبْعَه", 8: "تَمَانْيَه", 9: "تِسْعَه", 10: "عَشَرَه", 11: "حِدَاشَر", 12: "اِتْنَاشَر",
}
_MIN_FRACTION = {5: "خَمْسَه", 10: "عَشَرَه", 15: "رُبع", 20: "تِلْت", 30: "نُصّ"}


def _say_time(h: int, mn: int) -> str:
    """Read clock times naturally in Egyptian Arabic (e.g. 3:30 -> تلاتة و نص)."""
    h_adj = h % 12
    if h_adj == 0:
        h_adj = 12
    hour = _HOUR_FEM.get(h_adj, "تلاتة")
    if mn == 0:
        return hour
    if mn in _MIN_FRACTION:
        return f"{hour} و {_MIN_FRACTION[mn]}"
    if mn == 25:
        return f"{hour} و نُصّ اِلَّا خَمْسَه"
    if mn == 35:
        return f"{hour} و نُصّ و خَمْسَه"
    if mn > 30:
        nxt = _HOUR_FEM.get((h_adj % 12) + 1, "واحدة")
        rem = 60 - mn
        frac = _MIN_FRACTION.get(rem, number_to_arabic_words(rem))
        return f"{nxt} الا {frac}"
    return f"{hour} و {number_to_arabic_words(mn)} دقيقة"


# --------------------------------------------------------------------------- currencies & abbreviations
_CURRENCIES = {
    "ج.م": "جنيه", "جنيه": "جنيه", "EGP": "جنيه", "LE": "جنيه", "£": "جنيه",
    "$": "دولار", "USD": "دولار", "€": "يورو", "EUR": "يورو",
    "ر.س": "ريال", "SAR": "ريال", "د.إ": "درهم", "AED": "درهم",
}

_ABBREVIATIONS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bد\.\s*"), "دكتور "),
    (re.compile(r"\bأ\.\s*"), "أستاذ "),
    (re.compile(r"\bم\.\s*"), "مهندس "),
    (re.compile(r"\bج\.م\.?\b"), "جنيه مصري"),
    (re.compile(r"\bكجم\b"), "كيلو جرام"),
    (re.compile(r"\bكم\b"), "كيلومتر"),
    (re.compile(r"\bسم\b"), "سنتيمتر"),
    (re.compile(r"\bإلخ\b|\bالخ\b"), "إلى آخره"),
]

# --------------------------------------------------------------------------- Masri replacements
_MASRI_PHONETIC_REPLACEMENTS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bعلشان\b", re.IGNORECASE), "عَلَشانْ"),
    (re.compile(r"\bعشان\b", re.IGNORECASE), "عَشانْ"),
    (re.compile(r"\bدلوقتي\b", re.IGNORECASE), "دِلوَقْتي"),
    (re.compile(r"\bدلوقت\b", re.IGNORECASE), "دِلوَقْت"),
    (re.compile(r"\bإزاي\b|\bازاي\b", re.IGNORECASE), "إِزَّاي"),
    (re.compile(r"\bإيه\b|\bايه\b", re.IGNORECASE), "إيهْ"),
    (re.compile(r"\bليه\b", re.IGNORECASE), "ليهْ"),
    (re.compile(r"\bفين\b", re.IGNORECASE), "فينْ"),
    (re.compile(r"\bكده\b|\bكدة\b", re.IGNORECASE), "كِدهْ"),
    (re.compile(r"\bعايز\b|\bعاوز\b", re.IGNORECASE), "عايِزْ"),
    (re.compile(r"\bعايزة\b|\bعاوزة\b", re.IGNORECASE), "عايْزَة"),
    (re.compile(r"\bأوي\b|\bاوي\b", re.IGNORECASE), "قَوِي"),
    (re.compile(r"\bشوية\b", re.IGNORECASE), "شُوَيَّة"),
    (re.compile(r"\bبكرة\b", re.IGNORECASE), "بُكْرَة"),
    (re.compile(r"\bإمبارح\b|\bامبارح\b", re.IGNORECASE), "إِمْبارِح"),
    (re.compile(r"\bالنهاردة\b", re.IGNORECASE), "النَّهارْدَة"),
    (re.compile(r"\bكويس\b", re.IGNORECASE), "كُوَيِّسْ"),
    (re.compile(r"\bكويسة\b", re.IGNORECASE), "كُوَيِّسَة"),
    (re.compile(r"\bبص\b", re.IGNORECASE), "بُصْ"),
    (re.compile(r"\bشوف\b", re.IGNORECASE), "شُوفْ"),
    (re.compile(r"\bتمام\b", re.IGNORECASE), "تَمامْ"),
    (re.compile(r"\bماشي\b", re.IGNORECASE), "ماشِي"),
    (re.compile(r"\bحاضر\b", re.IGNORECASE), "حاضِرْ"),
    (re.compile(r"\bيعني\b", re.IGNORECASE), "يَعْنِي"),
]

# Stiff formal Fusha system phrases replaced with natural Egyptian colloquial speech or explicit Tashkeel
_FORMAL_TO_MASRI_REPLACEMENTS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bبالعامية المصرية\b", re.IGNORECASE), "بِالعَامِّيَّة المَصْرِيَّة"),
    (re.compile(r"\bالعامية المصرية\b", re.IGNORECASE), "العَامِّيَّة المَصْرِيَّة"),
    (re.compile(r"\bيرجى الانتظار\b", re.IGNORECASE), "ثواني خليك معايا"),
    (re.compile(r"\bيرجى المحاولة\b", re.IGNORECASE), "جرب تاني"),
    (re.compile(r"\bتم بنجاح\b", re.IGNORECASE), "اتعمل تمام"),
    (re.compile(r"\bغير متاح حالياً\b", re.IGNORECASE), "مش متاح دلوقتي"),
    (re.compile(r"\bغير متاح\b", re.IGNORECASE), "مش متاح"),
    (re.compile(r"\bلا تقلق\b", re.IGNORECASE), "ماتقلقش خالص"),
    (re.compile(r"\bشكراً جزيلاً\b", re.IGNORECASE), "شكراً جداً"),
    (re.compile(r"\bإلى اللقاء\b", re.IGNORECASE), "سلام أشوفك على خير"),
    (re.compile(r"\bهل يمكنني مساعدتك\b", re.IGNORECASE), "أقدر أساعدك في إيه؟"),
    (re.compile(r"\bحسناً\b", re.IGNORECASE), "تمام"),
]


class MasriNormalizer:
    """Colloquial Egyptian text normalizer with code-switching and code-mixing enhancements."""

    def __init__(self):
        pass

    def normalize(self, text: str) -> str:
        if not text or not text.strip():
            return ""

        # Convert Arabic-Indic numerals (٠-٩) to ASCII (0-9)
        text = text.translate(_AR2ASCII)

        # Step 1: Expand clock times (e.g. 3:30 -> تلاتة و نص)
        def _replace_time(m):
            h, mn = int(m.group(1)), int(m.group(2))
            return f" {_say_time(h, mn)} "
        text = re.sub(r"\b(\d{1,2}):(\d{2})\b", _replace_time, text)

        # Step 2: Expand percentages (e.g. 25% -> خمسة وعشرين في المية)
        def _replace_pct(m):
            num = int(m.group(1))
            return f" {number_to_arabic_words(num)} في المية "
        text = re.sub(r"\b(\d+)\s*%", _replace_pct, text)

        # Step 3: Expand currencies (e.g. 250 جنيه, $50)
        def _replace_curr_post(m):
            num = int(m.group(1))
            curr = _CURRENCIES.get(m.group(2), m.group(2))
            return f" {number_to_arabic_words(num)} {curr} "
        text = re.sub(r"\b(\d+)\s*(جنيه|ج\.م|EGP|LE|دولار|يورو)\b", _replace_curr_post, text)

        def _replace_curr_pre(m):
            curr = _CURRENCIES.get(m.group(1), "دولار")
            num = int(m.group(2))
            return f" {number_to_arabic_words(num)} {curr} "
        text = re.sub(r"([$€£])\s*(\d+)\b", _replace_curr_pre, text)

        # Step 4: Expand remaining standalone numbers
        def _replace_num(m):
            val = int(m.group(0))
            if val <= 100_000_000:
                return number_to_arabic_words(val)
            return m.group(0)
        text = re.sub(r"(?<![a-zA-Z0-9_])\d+(?![a-zA-Z0-9_])", _replace_num, text)

        # Step 5: Expand abbreviations
        for pattern, replacement in _ABBREVIATIONS:
            text = pattern.sub(replacement, text)

        # Step 6: Code-Switching Token Separation
        # Insert a space between Arabic prefixes (ال, الـ, بالـ, للـ, فالـ, والـ) and English words
        # E.g., 'الID' or 'الـID' -> 'ال ID', 'بالـAPI' -> 'بال API', 'للـsystem' -> 'لل system'
        text = re.sub(r"(^|\s)([وفلب]?ال|لل)ـ?([a-zA-Z]+)", r"\1\2 \3", text)

        # Step 7: Code-Switching Transition Pause
        # Insert micro-pause (Arabic comma '،') when transitioning from Latin/English back to Arabic
        # E.g., 'meeting بكرة' -> 'meeting، بكرة', 'API شغال' -> 'API، شغال'
        text = re.sub(r"([a-zA-Z0-9]+)\s+([\u0600-\u06FF])", r"\1، \2", text)

        # Step 8: Formal Fusha -> Natural Colloquial Masri replacements
        for pattern, replacement in _FORMAL_TO_MASRI_REPLACEMENTS:
            text = pattern.sub(replacement, text)

        # Step 9: Egyptian phonetic enhancements
        for pattern, replacement in _MASRI_PHONETIC_REPLACEMENTS:
            text = pattern.sub(replacement, text)

        # Step 10: Clean up spacing
        text = _MULTISPACE_RE.sub(" ", text).strip()
        return text


_NORMALIZER = MasriNormalizer()


def normalize_masri_orthography(text: str) -> str:
    """Normalizes Arabic orthographic variants for lexical matching."""
    if not text:
        return ""
    text = _TATWEEL_RE.sub("", text)
    text = _DIACRITICS_RE.sub("", text)
    text = re.sub(r"[أإآٱ]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    return _MULTISPACE_RE.sub(" ", text).strip().lower()


def clean_llm_output_for_speech(text: str) -> str:
    """
    Extracts speech-ready text from LLM response:
    - Removes internal chain-of-thought (<think>...</think>)
    - Removes gesture and action markers ([action:nod], [happy], etc.)
    - Removes corrupted unicode glyphs (e.g. random CJK)
    - Applies complete Egyptian Arabic Normalization & Code-Switching pipeline
    """
    if not text:
        return ""

    # 1. Strip thinking tags
    cleaned = _THINK_RE.sub("", text)

    # 2. Strip action and gesture bracket tags
    cleaned = _BRACKET_TAG_RE.sub("", cleaned)

    # 3. Strip stray non-Arabic, non-Latin, non-punctuation symbols (e.g. CJK chars)
    cleaned = re.sub(r"[\u4e00-\u9fff]", "", cleaned)

    # 4. Apply Masri normalization + code-switching pipeline
    cleaned = _NORMALIZER.normalize(cleaned)

    return cleaned


def extract_thoughts_and_actions(text: str) -> Tuple[str, List[Dict[str, str]], str]:
    """
    Parses LLM output into:
      1. thought: Internal reasoning from <think>...</think>
      2. actions: List of action dicts [{"action": "nod", "param": ""}]
      3. speech: Clean speech text for TTS
    """
    thought = ""
    think_match = _THINK_RE.search(text)
    if think_match:
        thought = think_match.group(0).replace("<think>", "").replace("</think>", "").strip()

    actions: List[Dict[str, str]] = []
    for match in _ACTION_TAG_RE.finditer(text):
        action_name = match.group(1).lower()
        param = match.group(2) or ""
        actions.append({"action": action_name, "param": param.strip()})

    speech = clean_llm_output_for_speech(text)
    return thought, actions, speech
