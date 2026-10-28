"""
Egyptian Arabic (Masri) Dialect & Phonetic Normalizer
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Preprocesses text for TTS synthesis and LLM processing to:
  1. Eliminate non-Egyptian foreign/formal accents.
  2. Handle Egyptian colloquial contractions and vocabulary (علشان, دلوقتي, مش, إيه, فين, إزاي, كده).
  3. Normalize Arabic characters (alefs, yaas, teh marbutas, tatweels).
  4. Preserve and sanitize English code-switching ("عندي meeting بكرة").
  5. Strip thinking tags (<think>...</think>) and action commands before voice synthesis.
"""

import re
from typing import Tuple, List, Dict

# Regex patterns
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_ACTION_TAG_RE = re.compile(r"\[(?:action:|gesture:|cmd:)?([\w\u0600-\u06FF]+)(?::([^\]]+))?\]", re.IGNORECASE)
_BRACKET_TAG_RE = re.compile(r"\[[\w\u0600-\u06FF\s:_\-]+\]")
_TATWEEL_RE = re.compile(r"\u0640+")
_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")
_MULTISPACE_RE = re.compile(r"\s+")

# Common Egyptian colloquial contractions and phonetic optimizations
# Maps standard or informal spellings to phonetically natural Egyptian pronunciation for TTS
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
    (re.compile(r"\bأوي\b|\bاوي\b", re.IGNORECASE), "قَوِي"),  # in Cairo dialect often voiced softly
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

# Map Egyptian numbers in text to Arabic words for natural speech
_NUMBERS_MAP: Dict[str, str] = {
    "0": "صفر",
    "1": "واحد",
    "2": "اتنين",
    "3": "تلاتة",
    "4": "أربعة",
    "5": "خمسة",
    "6": "ستة",
    "7": "سبعة",
    "8": "تمانية",
    "9": "تسعة",
    "10": "عشرة",
}


def normalize_masri_orthography(text: str) -> str:
    """
    Normalizes Arabic orthographic variants (alefs, yaa/alef maksura, heh/teh marbuta)
    for high-precision semantic & lexical matching in RAG and search.
    """
    if not text:
        return ""
    # Strip tatweel and diacritics
    text = _TATWEEL_RE.sub("", text)
    text = _DIACRITICS_RE.sub("", text)

    # Normalize Alef variants: أ, إ, آ, ٱ -> ا
    text = re.sub(r"[أإآٱ]", "ا", text)
    # Normalize Yaa and Alef Maksura: ى -> ي
    text = re.sub(r"ى", "ي", text)
    # Normalize Teh Marbuta: ة -> ه (for colloquial consistency)
    text = re.sub(r"ة", "ه", text)

    return _MULTISPACE_RE.sub(" ", text).strip().lower()


def clean_llm_output_for_speech(text: str) -> str:
    """
    Extracts speech-ready text from LLM response:
    - Removes internal chain-of-thought (<think>...</think>)
    - Removes gesture and action markers ([action:nod], [happy], etc.)
    - Removes corrupted unicode glyphs (e.g. random CJK)
    - Applies Masri phonetic enhancement
    """
    if not text:
        return ""

    # 1. Strip thinking tags
    cleaned = _THINK_RE.sub("", text)

    # 2. Strip action and gesture bracket tags
    cleaned = _BRACKET_TAG_RE.sub("", cleaned)

    # 3. Strip stray non-Arabic, non-Latin, non-punctuation symbols (e.g. CJK chars)
    cleaned = re.sub(r"[\u4e00-\u9fff]", "", cleaned)

    # 4. Convert standalone digits to Egyptian Arabic words
    for digit, word in _NUMBERS_MAP.items():
        cleaned = re.sub(r"\b" + digit + r"\b", word, cleaned)

    # 5. Apply Egyptian phonetic enhancements
    for pattern, replacement in _MASRI_PHONETIC_REPLACEMENTS:
        cleaned = pattern.sub(replacement, cleaned)

    # 6. Normalize spaces
    cleaned = _MULTISPACE_RE.sub(" ", cleaned).strip()
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
