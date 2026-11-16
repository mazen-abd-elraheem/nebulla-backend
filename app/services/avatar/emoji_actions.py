"""Canonical Face-Emoji Action Protocol for driving Avatar expression, lip movement & cloned voice.

Maps rich Unicode face emojis (😊 😂 😍 😢 😮 😡 🤔 😉 😴 😐 👋 👍) AND legacy
LLM bracket tags ([happy], [wave], [sad], ...) into structured avatar metadata
used across:
- VoiceTut TTS speech cleaning (emojis are stripped so they are never read aloud)
- WebSocket real-time avatar messages (`t="avatar_action"` & `t="eyes"`)
- REST Chat responses (`face_emoji`, `expression`, `avatar_action`)
- GAGAvatar / UniFace expression rendering & Flutter synchronized lip movement
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# Ordered canonical specification for primary expressions
FACE_EMOJI_ACTIONS: Dict[str, Dict[str, Any]] = {
    "neutral": {
        "face_emoji": "😐",
        "expression": "neutral",
        "ws_mood": "neutral",
        "mouth_preset": "neutral",
        "speak_mouth": True,
        "label_ar": "طبيعي",
        "robot_gesture": "[neutral]",
        "flame_params": {"exp0": 0.0, "exp1": 0.0, "jaw": 0.0, "blink": 0.0},
    },
    "happy": {
        "face_emoji": "😊",
        "expression": "happy",
        "ws_mood": "happy",
        "mouth_preset": "smile",
        "speak_mouth": True,
        "label_ar": "مبسوط",
        "robot_gesture": "[happy]",
        "flame_params": {"exp0": 1.6, "exp1": 0.4, "jaw": 0.15, "blink": 0.1},
    },
    "laugh": {
        "face_emoji": "😂",
        "expression": "laugh",
        "ws_mood": "happy",
        "mouth_preset": "open_laugh",
        "speak_mouth": True,
        "label_ar": "بيضحك",
        "robot_gesture": "[happy]",
        "flame_params": {"exp0": 2.4, "exp1": 0.9, "jaw": 0.55, "blink": 0.35},
    },
    "love": {
        "face_emoji": "😍",
        "expression": "love",
        "ws_mood": "love",
        "mouth_preset": "smile_soft",
        "speak_mouth": True,
        "label_ar": "محب / دافئ",
        "robot_gesture": "[love]",
        "flame_params": {"exp0": 1.8, "exp1": 0.6, "jaw": 0.10, "blink": 0.2},
    },
    "sad": {
        "face_emoji": "😢",
        "expression": "sad",
        "ws_mood": "sad",
        "mouth_preset": "frown",
        "speak_mouth": True,
        "label_ar": "زعلان",
        "robot_gesture": "[sad]",
        "flame_params": {"exp0": -1.3, "exp1": -0.7, "jaw": 0.05, "blink": 0.25},
    },
    "surprised": {
        "face_emoji": "😮",
        "expression": "surprised",
        "ws_mood": "surprised",
        "mouth_preset": "open_o",
        "speak_mouth": True,
        "label_ar": "متفاجئ",
        "robot_gesture": "[surprised]",
        "flame_params": {"exp0": 0.3, "exp1": 1.9, "jaw": 0.65, "blink": 0.0},
    },
    "angry": {
        "face_emoji": "😡",
        "expression": "angry",
        "ws_mood": "angry",
        "mouth_preset": "tense",
        "speak_mouth": True,
        "label_ar": "متعصب",
        "robot_gesture": "[angry]",
        "flame_params": {"exp0": -1.6, "exp1": -1.4, "jaw": 0.20, "blink": 0.0},
    },
    "thinking": {
        "face_emoji": "🤔",
        "expression": "thinking",
        "ws_mood": "thinking",
        "mouth_preset": "pout",
        "speak_mouth": True,
        "label_ar": "بيفكر",
        "robot_gesture": "[thinking]",
        "flame_params": {"exp0": 0.2, "exp1": -0.6, "jaw": 0.0, "blink": 0.15},
    },
    "wink": {
        "face_emoji": "😉",
        "expression": "wink",
        "ws_mood": "happy",
        "mouth_preset": "smirk",
        "speak_mouth": True,
        "label_ar": "غمزة ودودة",
        "robot_gesture": "[wink]",
        "flame_params": {"exp0": 1.2, "exp1": 0.3, "jaw": 0.08, "blink": 0.5},
    },
    "sleepy": {
        "face_emoji": "😴",
        "expression": "sleepy",
        "ws_mood": "sleepy",
        "mouth_preset": "relaxed",
        "speak_mouth": True,
        "label_ar": "نعسان / هادي",
        "robot_gesture": "[sleepy]",
        "flame_params": {"exp0": -0.2, "exp1": -0.5, "jaw": 0.05, "blink": 0.85},
    },
    "wave": {
        "face_emoji": "👋",
        "expression": "wave",
        "ws_mood": "wave",
        "mouth_preset": "smile",
        "speak_mouth": True,
        "label_ar": "ترحيب",
        "robot_gesture": "[wave]",
        "flame_params": {"exp0": 1.4, "exp1": 0.5, "jaw": 0.12, "blink": 0.1},
    },
    "like": {
        "face_emoji": "👍",
        "expression": "like",
        "ws_mood": "like",
        "mouth_preset": "smile",
        "speak_mouth": True,
        "label_ar": "موافق / تمام",
        "robot_gesture": "[like]",
        "flame_params": {"exp0": 1.3, "exp1": 0.3, "jaw": 0.10, "blink": 0.1},
    },
}

# Unicode emoji -> canonical expression key
_EMOJI_TO_EXPRESSION: Dict[str, str] = {
    "😐": "neutral", "😶": "neutral", "🙂": "neutral",
    "😊": "happy", "😃": "happy", "😄": "happy", "😁": "happy", "🤗": "happy",
    "😂": "laugh", "🤣": "laugh", "😆": "laugh",
    "😍": "love", "🥰": "love", "❤️": "love", "❤": "love", "💕": "love", "😘": "love", "💖": "love",
    "😢": "sad", "😭": "sad", "😞": "sad", "😔": "sad", "😟": "sad",
    "😮": "surprised", "😲": "surprised", "😱": "surprised", "🤯": "surprised",
    "😡": "angry", "😠": "angry", "🤬": "angry",
    "🤔": "thinking", "🧐": "thinking", "🤨": "thinking",
    "😉": "wink", "😜": "wink", "😏": "wink",
    "😴": "sleepy", "😪": "sleepy", "🥱": "sleepy",
    "👋": "wave", "🙌": "wave",
    "👍": "like", "👌": "like", "👏": "like",
}

_TAG_TO_EXPRESSION: Dict[str, str] = {
    "happy": "happy", "فرحان": "happy", "smile": "happy", "joy": "happy", "سعيد": "happy",
    "laugh": "laugh", "ضحك": "laugh",
    "sad": "sad", "حزين": "sad",
    "surprised": "surprised", "متفاجئ": "surprised", "shocked": "surprised",
    "wave": "wave", "لوح": "wave", "سلام": "wave", "باي": "wave", "greet": "wave",
    "like": "like", "اعجاب": "like", "تمام": "like", "عاش": "like", "ممتاز": "like",
    "love": "love", "حب": "love", "قلب": "love",
    "angry": "angry", "غاضب": "angry", "زعلان_جدا": "angry",
    "thinking": "thinking", "تفكير": "thinking",
    "wink": "wink", "غمزة": "wink",
    "sleepy": "sleepy", "نعسان": "sleepy",
    "neutral": "neutral", "طبيعي": "neutral",
}

_BRACKET_TAG_RE = re.compile(r"\[[^\]]+\]")

# Broad Unicode emoji/pictograph pattern that leaves Arabic/Latin/digits/punctuation intact.
_UNICODE_EMOJI_RE = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"  # supplemental symbols & pictographs (🤔 🥰 🤣 etc.)
    "\U0001FA00-\U0001FAFF"  # chess/extended-A
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002700-\U000027BF"  # dingbats (❤️ etc.)
    "\U0001F3FB-\U0001F3FF"  # skin tone modifiers
    "\u200d"                 # zero-width joiner
    "\ufe0e\ufe0f"           # variation selectors
    "]+",
    flags=re.UNICODE,
)


def strip_emojis_for_speech(text: str) -> str:
    """Remove Unicode emojis and variation selectors while preserving spoken Arabic/English text."""
    if not text:
        return ""
    cleaned = _UNICODE_EMOJI_RE.sub(" ", text)
    # Collapse repeated spaces left by stripped emojis while keeping newlines tidy
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip()


def resolve_expression_spec(key_or_emoji: Optional[str]) -> Dict[str, Any]:
    """Resolve an expression name or Unicode emoji to its canonical action spec."""
    if not key_or_emoji:
        return dict(FACE_EMOJI_ACTIONS["neutral"])
    raw = str(key_or_emoji).strip()
    if raw in _EMOJI_TO_EXPRESSION:
        expr = _EMOJI_TO_EXPRESSION[raw]
        return dict(FACE_EMOJI_ACTIONS[expr])
    low = raw.lower().strip("[]")
    if low in FACE_EMOJI_ACTIONS:
        return dict(FACE_EMOJI_ACTIONS[low])
    if low in _TAG_TO_EXPRESSION:
        return dict(FACE_EMOJI_ACTIONS[_TAG_TO_EXPRESSION[low]])
    return dict(FACE_EMOJI_ACTIONS["neutral"])


def extract_emoji_and_emotion(text: str, voice_mode: str = "cloned") -> Dict[str, Any]:
    """
    Parse face emoji or legacy emotion tag from an LLM response and build a unified avatar action payload.

    Priority preserves backward compatibility with existing pipeline tests:
    1. Legacy bracket tags `[happy]`, `[sad]`, `[surprised]`, `[wave]`, `[like]`, ...
    2. Explicit Unicode face emojis (`😊`, `😂`, `😍`, `😢`, `😮`, `😡`, `🤔`, `😉`, `😴`, `😐`, `👋`, `👍`)
    3. Arabic / English emotion keywords fallback (`فرحان`, `حزين`, ...)
    """
    if not text:
        spec = dict(FACE_EMOJI_ACTIONS["neutral"])
        spec["voice_mode"] = voice_mode
        return spec

    resolved_expr: Optional[str] = None
    matched_emoji: Optional[str] = None

    # First check explicit Unicode emojis in appearance order (capture emoji icon even if tag also exists)
    earliest_idx: Optional[int] = None
    for em_char, expr_name in _EMOJI_TO_EXPRESSION.items():
        pos = text.find(em_char)
        if pos != -1 and (earliest_idx is None or pos < earliest_idx):
            earliest_idx = pos
            matched_emoji = em_char
            resolved_expr = expr_name

    # Check legacy bracket tags (if present, bracket tag sets primary expression for existing tests)
    for tag_match in _BRACKET_TAG_RE.findall(text):
        t_clean = tag_match.strip("[]").lower()
        # Handle "[action:wave]" or plain "[happy]"
        if ":" in t_clean:
            _, t_clean = t_clean.split(":", 1)
        if t_clean in _TAG_TO_EXPRESSION:
            resolved_expr = _TAG_TO_EXPRESSION[t_clean]
            break

    # Fallback keyword matching when neither emoji nor tag was emitted
    if resolved_expr is None:
        text_lower = text.lower()
        if any(w in text_lower for w in ["happy", "فرحان", "مبسوط"]):
            resolved_expr = "happy"
        elif any(w in text_lower for w in ["sad", "حزين", "زعلان"]):
            resolved_expr = "sad"
        elif any(w in text_lower for w in ["surprised", "متفاجئ", "مصدوم"]):
            resolved_expr = "surprised"
        elif any(w in text_lower for w in ["wave", "سلام", "باي"]):
            resolved_expr = "wave"
        elif any(w in text_lower for w in ["like", "عاش"]):
            resolved_expr = "like"
        else:
            resolved_expr = "neutral"

    spec = dict(FACE_EMOJI_ACTIONS.get(resolved_expr, FACE_EMOJI_ACTIONS["neutral"]))
    if matched_emoji and _EMOJI_TO_EXPRESSION.get(matched_emoji) == spec["expression"]:
        spec["face_emoji"] = matched_emoji
    spec["voice_mode"] = voice_mode
    return spec


def list_emoji_action_catalog() -> List[Dict[str, Any]]:
    """Return all supported face-emoji avatar actions for API / UI discovery."""
    return [dict(v) for v in FACE_EMOJI_ACTIONS.values()]

