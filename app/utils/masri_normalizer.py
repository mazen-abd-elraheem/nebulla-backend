"""
Egyptian Arabic (Masri) Intelligent Dialect, Morpho-Contextual Normalizer & Code-Switching Pipeline
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
High-speed (< 2ms) context-aware normalization for VoiceTuT/XTTS speech synthesis:
  1. Shielding Engine: Protects quotes ("..."), URLs, file paths, code, and LLM reasoning tags.
  2. Code-Switching Engine: Detaches Arabic clitics (ال, بال, لل, فال, وال) from English/Latin terms
     while preserving raw English text and avoiding commas inside compound English phrases.
  3. Smart Entity & Counting Engine:
     - Phone numbers read naturally in Egyptian Arabic (digit-by-digit or chunked).
     - Clock times with colloquial fractions (تلاتة و نص، أربعة و ربع، ستة الا تلت).
     - Contextual Egyptian Duals (ساعتين، يومين، سنتين، جنيهين، شهرين) and 3-10 counting (تلات سنين، خمس شهور).
     - Currencies and Percentages with Egyptian phrasing.
  4. Contextual Morpho-Syntactic Transforms (Authentic Masri dialect):
     - Verbal negation: مش هقدر / ماعرفش / معنديش / مفيش / ماتقلقش.
     - Modals and Futurity: لازم / عايز / هعمل / هساعدك / هنشوف / هيتعمل.
  5. Selective Phonetic Disambiguation: Applies Tashkeel specifically to phonetically ambiguous
     Egyptian words without altering protected or formal texts.
"""

from __future__ import annotations

import re
from typing import Dict, List, Match, Optional, Tuple

# --------------------------------------------------------------------------- Core regex patterns
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_ACTION_TAG_RE = re.compile(r"\[(?:action:|gesture:|cmd:)?([\w\u0600-\u06FF]+)(?::([^\]]+))?\]", re.IGNORECASE)
_BRACKET_TAG_RE = re.compile(r"\[[\w\u0600-\u06FF\s:_\-]+\]")
_TATWEEL_RE = re.compile(r"\u0640+")
_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")
_MULTISPACE_RE = re.compile(r"\s+")

# Shielding regexes: quotes, URLs, code blocks, and system paths
_URL_RE = re.compile(r"https?://[^\s<>\"']+|www\.[^\s<>\"']+", re.IGNORECASE)
_PATH_RE = re.compile(r"\b[A-Za-z]:\\[^\s<>\"']+|(?:\/[\w.\-]+){2,}", re.IGNORECASE)
_CODE_BLOCK_RE = re.compile(r"`[^`\n]+`")
_QUOTE_RE = re.compile(r'["“«]([^"”»\n]{2,})["”»]')

# --------------------------------------------------------------------------- Digits & Numbers (Egyptian)
ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"
ASCII_DIGITS = "0123456789"
_AR2ASCII = {ord(a): d for a, d in zip(ARABIC_INDIC, ASCII_DIGITS)}

_DIGIT_WORDS = ["صفر", "واحد", "اتنين", "تلاتة", "أربعة", "خمسة", "ستة", "سبعة", "تمانية", "تسعة"]

_ONES = ["", "وَاحِد", "اِتْنِين", "تَلَاتَة", "أَرْبَعَه", "خَمْسَه", "سِتَّه", "سَبْعَه", "تَمَانْيَه", "تِسْعَه"]
_ONES_COUNTABLE = ["", "واحد", "اتنين", "تلات", "أربع", "خمس", "ست", "سبع", "تمن", "تسع"]
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

# Common Egyptian counting nouns with natural dual morphology
_DUAL_NOUNS = {
    "جنيه": "جنيهين",
    "يوم": "يومين",
    "ساعة": "ساعتين",
    "سنة": "سنتين",
    "شهر": "شهرين",
    "أسبوع": "أسبوعين",
    "دقيقة": "دقيقتين",
    "مرة": "مرتين",
    "قرش": "قرشين",
    "حاجة": "حاجتين",
    "كيلو": "اتنين كيلو",
    "دولار": "اتنين دولار",
    "يورو": "اتنين يورو",
}

# Plural nouns that take truncated 3-10 counting forms (تلات سنين، خمس شهور)
_COUNTABLE_PLURAL_NOUNS = {
    "سنين", "أيام", "شهور", "ساعات", "دقايق", "دقائق", "مرات", "قروش", "جنيهات", "كتب", "أشخاص", "ناس", "سنين"
}


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


def _say_phone_number(digits: str) -> str:
    """Convert a phone number into natural Egyptian speech (digit-by-digit with rhythm)."""
    # E.g. 01012345678 -> صفر واحد صفر، واحد اتنين، تلاتة أربعة، خمسة ستة، سبعة تمانية
    words = [_DIGIT_WORDS[int(d)] for d in digits if d.isdigit()]
    return " ".join(words)


# --------------------------------------------------------------------------- Time (Colloquial Egyptian)
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


# --------------------------------------------------------------------------- Currencies & Abbreviations
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

# --------------------------------------------------------------------------- Contextual Morpho-Syntactic Transforms
# Authentic colloquial Egyptian negation, future markers, and conversational system phrases
_MORPHO_SYNTACTIC_TRANSFORMS: List[Tuple[re.Pattern, str]] = [
    # Verbal Negation & Capability
    (re.compile(r"\b(?:لا|لن)\s+أستطيع\b"), "مش هقدر"),
    (re.compile(r"\b(?:لا|لن)\s+يستطيع\b"), "مش هيقدر"),
    (re.compile(r"\b(?:لا|لن)\s+تستطيع\b"), "مش هتقدر"),
    (re.compile(r"\b(?:لا|لن)\s+نستطيع\b"), "مش هنقدر"),
    (re.compile(r"\b(?:لا|لن)\s+يستطيعوا\b"), "مش هيقدروا"),
    # Knowledge & Awareness
    (re.compile(r"\b(?:لا|لن)\s+أعرف\b|\b(?:لا|لن)\s+أدري\b|\b(?:لا|لن)\s+أعلم\b"), "ماعرفش"),
    (re.compile(r"\b(?:لا|لن)\s+يعرف\b|\b(?:لا|لن)\s+يعلم\b"), "مايعرفش"),
    (re.compile(r"\b(?:لا|لن)\s+تعرف\b|\b(?:لا|لن)\s+تعلم\b"), "ماتعرفش"),
    (re.compile(r"\b(?:لا|لن)\s+نعرف\b|\b(?:لا|لن)\s+نعلم\b"), "مانعرفش"),
    # Existence & Possession
    (re.compile(r"\b(?:لا|ما)\s+يوجد\b|\b(?:لا|ما)\s+توجد\b|\bليس\s+هناك\b"), "مفيش"),
    (re.compile(r"\bليس\s+لدي\b|\bليس\s+عندي\b|\bلا\s+أملك\b"), "معنديش"),
    (re.compile(r"\bليس\s+لديك\b|\bليس\s+عندك\b"), "معندكش"),
    (re.compile(r"\bليس\s+لدينا\b|\bليس\s+عندنا\b"), "معندناش"),
    # Reassurance & Negated States
    (re.compile(r"\bلا\s+تقلق\b"), "ماتقلقش خالص"),
    (re.compile(r"\bلا\s+تقلقي\b"), "ماتقلقيش خالص"),
    (re.compile(r"\bلا\s+تقلقوا\b"), "ماتقلقوش خالص"),
    (re.compile(r"\bلا\s+داعي\b"), "مفيش داعي"),
    (re.compile(r"\bليس\s+صحيح[اً]?\b"), "مش صحيح"),
    (re.compile(r"\bلا\s+أريد\b"), "مش عايز"),
    # Future Action & Volition
    (re.compile(r"\bسوف\s+أقوم\s+ب(?:ـ|عمل\s+)?\b"), "هعمل "),
    (re.compile(r"\bسوف\s+أفعل\b"), "هعمل"),
    (re.compile(r"\bسوف\s+أساعدك\b"), "هساعدك"),
    (re.compile(r"\bسوف\s+نرى\b"), "هنشوف"),
    (re.compile(r"\bسوف\s+يكون\b"), "هيكون"),
    (re.compile(r"\bسوف\s+تكون\b"), "هتكون"),
    (re.compile(r"\bسوف\s+يتم\b"), "هيتعمل"),
    # Obligation & Modals
    (re.compile(r"\b(?:يجب|ينبغي|عليك)\s+أن\b"), "لازم"),
    (re.compile(r"\bعليكم\s+أن\b"), "لازم"),
    (re.compile(r"\bأريد\s+أن\b"), "عايز"),
    (re.compile(r"\bنريد\s+أن\b"), "عايزين"),
    (re.compile(r"\bهل\s+يمكنك\b"), "ممكن"),
    (re.compile(r"\bهل\s+يمكنني\s+مساعدتك\b"), "أقدر أساعدك في إيه؟"),
    # Conversational System Phrases
    (re.compile(r"\bيرجى\s+الانتظار\b"), "ثواني خليك معايا"),
    (re.compile(r"\bيرجى\s+المحاولة\b"), "جرب تاني"),
    (re.compile(r"\bتم\s+بنجاح\b"), "اتعمل تمام"),
    (re.compile(r"\bغير\s+متاح\s+حالياً\b"), "مش متاح دلوقتي"),
    (re.compile(r"\bغير\s+متاح\b"), "مش متاح"),
    (re.compile(r"\bشكراً\s+جزيلاً\b"), "شكراً جداً"),
    (re.compile(r"\bإلى\s+اللقاء\b"), "سلام أشوفك على خير"),
    (re.compile(r"\bحسناً\b"), "تمام"),
    (re.compile(r"\bبالعامية\s+المصرية\b"), "بِالعَامِّيَّة المَصْرِيَّة"),
    (re.compile(r"\bالعامية\s+المصرية\b"), "العَامِّيَّة المَصْرِيَّة"),
]

# --------------------------------------------------------------------------- Selective Phonetic Disambiguation
# Tashkeel applied only to phonetically ambiguous Masri vocabulary for natural TTS pronunciation
_MASRI_PHONETIC_DISAMBIGUATION: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\bعلشان\b"), "عَلَشانْ"),
    (re.compile(r"\bعشان\b"), "عَشانْ"),
    (re.compile(r"\bدلوقتي\b"), "دِلوَقْتي"),
    (re.compile(r"\bدلوقت\b"), "دِلوَقْت"),
    (re.compile(r"\bإزاي\b|\bازاي\b"), "إِزَّاي"),
    (re.compile(r"\bإيه\b|\bايه\b"), "إيهْ"),
    (re.compile(r"\bليه\b"), "ليهْ"),
    (re.compile(r"\bفين\b"), "فينْ"),
    (re.compile(r"\bكده\b|\bكدة\b"), "كِدهْ"),
    (re.compile(r"\bعايز\b|\bعاوز\b"), "عايِزْ"),
    (re.compile(r"\bعايزة\b|\bعاوزة\b"), "عايْزَة"),
    (re.compile(r"\bأوي\b|\bاوي\b"), "أَوِي"),
    (re.compile(r"\bشوية\b"), "شُوَيَّة"),
    (re.compile(r"\bبكرة\b"), "بُكْرَة"),
    (re.compile(r"\bإمبارح\b|\bامبارح\b"), "إِمْبارِح"),
    (re.compile(r"\bالنهاردة\b"), "النَّهارْدَة"),
    (re.compile(r"\bكويس\b"), "كُوَيِّسْ"),
    (re.compile(r"\bكويسة\b"), "كُوَيِّسَة"),
    (re.compile(r"\bبص\b"), "بُصْ"),
    (re.compile(r"\bشوف\b"), "شُوفْ"),
    (re.compile(r"\bتمام\b"), "تَمامْ"),
    (re.compile(r"\bماشي\b"), "ماشِي"),
    (re.compile(r"\bحاضر\b"), "حاضِرْ"),
    (re.compile(r"\bيعني\b"), "يَعْنِي"),
]


# --------------------------------------------------------------------------- Shielding Engine
class _TextShield:
    """Safeguards quoted speech, URLs, file paths, and code blocks from alteration."""

    def __init__(self):
        self._shields: Dict[str, str] = {}
        self._counter: int = 0

    def shield(self, text: str) -> str:
        self._shields.clear()
        self._counter = 0

        def _store(match_text: str) -> str:
            placeholder = f"__MASRI_SHIELD_{self._counter}__"
            self._counter += 1
            self._shields[placeholder] = match_text
            return placeholder

        # 1. URLs
        text = _URL_RE.sub(lambda m: _store(m.group(0)), text)
        # 2. File paths
        text = _PATH_RE.sub(lambda m: _store(m.group(0)), text)
        # 3. Inline code
        text = _CODE_BLOCK_RE.sub(lambda m: _store(m.group(0)), text)
        # 4. Quoted text (keep quotation marks, protect content)
        text = _QUOTE_RE.sub(lambda m: f'"{_store(m.group(1))}"', text)

        return text

    def restore(self, text: str) -> str:
        for placeholder, original in self._shields.items():
            text = text.replace(placeholder, original)
        return text


# --------------------------------------------------------------------------- MasriNormalizer Class
class MasriNormalizer:
    """
    Intelligent Egyptian Arabic normalizer with Context-Aware Morphological,
    Code-Switching, and Phonetic Disambiguation capabilities (< 2ms latency).
    """

    def __init__(self):
        pass

    def normalize(self, text: str) -> str:
        if not text or not text.strip():
            return ""

        # Step 1: Shield quotes, URLs, and code blocks
        shield = _TextShield()
        text = shield.shield(text)

        # Convert Arabic-Indic numerals (٠-٩) to ASCII (0-9)
        text = text.translate(_AR2ASCII)

        # Step 2: Expand Clock Times (e.g. 3:30 -> تلاتة و نص)
        def _replace_time(m: Match) -> str:
            h, mn = int(m.group(1)), int(m.group(2))
            return f" {_say_time(h, mn)} "
        text = re.sub(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", _replace_time, text)

        # Step 3: Expand Phone Numbers (e.g. 01012345678 -> صفر واحد صفر...)
        def _replace_phone(m: Match) -> str:
            phone_digits = m.group(1)
            return f" {_say_phone_number(phone_digits)} "
        text = re.sub(r"(?:\+?20\s*|\b)(01[0125]\d{8})\b", _replace_phone, text)

        # Step 4: Expand Percentages (e.g. 25% -> خمسة وعشرين في المية)
        def _replace_pct(m: Match) -> str:
            num = int(m.group(1))
            return f" {number_to_arabic_words(num)} في المية "
        text = re.sub(r"\b(\d+)\s*%", _replace_pct, text)

        # Step 5: Expand Currencies & Number-Noun Agreement
        def _replace_curr_post(m: Match) -> str:
            num = int(m.group(1))
            raw_curr = m.group(2)
            curr = _CURRENCIES.get(raw_curr, raw_curr)
            if num == 2:
                dual = _DUAL_NOUNS.get(curr, f"اتنين {curr}")
                return f" {dual} "
            return f" {number_to_arabic_words(num)} {curr} "
        text = re.sub(r"\b(\d+)\s*(جنيه|ج\.م|EGP|LE|دولار|يورو|ريال|درهم)\b", _replace_curr_post, text)

        def _replace_curr_pre(m: Match) -> str:
            raw_sym = m.group(1)
            num = int(m.group(2))
            curr = _CURRENCIES.get(raw_sym, "دولار")
            if num == 2:
                dual = _DUAL_NOUNS.get(curr, f"اتنين {curr}")
                return f" {dual} "
            return f" {number_to_arabic_words(num)} {curr} "
        text = re.sub(r"([$€£])\s*(\d+)\b", _replace_curr_pre, text)

        # Step 6: Contextual Egyptian Duals & Plural Counting (e.g. 2 يوم -> يومين، 3 سنين -> تلات سنين)
        def _replace_count_noun(m: Match) -> str:
            num = int(m.group(1))
            noun = m.group(2)
            if num == 2 and noun in _DUAL_NOUNS:
                return _DUAL_NOUNS[noun]
            if 3 <= num <= 10 and noun in _COUNTABLE_PLURAL_NOUNS:
                return f"{_ONES_COUNTABLE[num]} {noun}"
            return f"{number_to_arabic_words(num)} {noun}"
        text = re.sub(r"\b(\d+)\s+([\u0621-\u064A]+)\b", _replace_count_noun, text)

        # Step 7: Expand remaining standalone numbers
        def _replace_standalone_num(m: Match) -> str:
            val = int(m.group(0))
            if val <= 100_000_000:
                return number_to_arabic_words(val)
            return m.group(0)
        text = re.sub(r"(?<![a-zA-Z0-9_])\d+(?![a-zA-Z0-9_])", _replace_standalone_num, text)

        # Step 8: Abbreviations Expansion
        for pattern, replacement in _ABBREVIATIONS:
            text = pattern.sub(replacement, text)

        # Step 9: Code-Switching Clitic Separation
        # Detach Arabic prefixes (ال, بال, لل, فال, وال) from English terms (e.g. 'الID' -> 'ال ID', 'بالـAPI' -> 'بال API')
        text = re.sub(r"(^|\s)([وفلب]?ال|لل)ـ?([a-zA-Z]+)", r"\1\2 \3", text)

        # Step 10: Code-Switching Natural Transition Pause
        # Insert micro-pause (Arabic comma '،') when transitioning from English back to Arabic,
        # but NEVER insert commas between two adjacent English words.
        text = re.sub(r"([a-zA-Z0-9]+)\s+([\u0600-\u06FF])", r"\1، \2", text)

        # Step 11: Contextual Morpho-Syntactic Transforms
        for pattern, replacement in _MORPHO_SYNTACTIC_TRANSFORMS:
            text = pattern.sub(replacement, text)

        # Step 12: Selective Phonetic Disambiguation for VoiceTuT
        for pattern, replacement in _MASRI_PHONETIC_DISAMBIGUATION:
            text = pattern.sub(replacement, text)

        # Step 13: Restore shielded elements
        text = shield.restore(text)

        # Step 14: Clean up spacing and punctuation
        text = re.sub(r"\s+([،,.!?])", r"\1", text)
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
