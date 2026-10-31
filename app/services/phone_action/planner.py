"""
ActionPlanner — turns a user's transcript into a structured phone-action intent
(benefits_section.docx §14.5, step 2).

SECURITY DESIGN
  * The planner is a DETERMINISTIC rule matcher over the user's own STT
    transcript. It never consults the LLM and never reads LLM output, so a
    model hallucination or prompt-injection can not originate a phone action.
  * The planner only *describes* what the user asked for. It does not decide
    whether it is allowed — that is ActionGuard's job.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from app.services.phone_action.textutil import (
    HOUR_WORDS,
    parse_int,
    prepare,
    sanitize_destination,
    sanitize_free_text,
)

# Intent kinds
CALL = "call"
MSG = "msg"
APP_OPEN = "app_open"
READ_NOTIFICATIONS = "read_notifications"
REMINDER = "reminder"
SENSITIVE = "sensitive"   # payments / memory wipe / add user / change permissions (Level 3)

# App vocabulary: folded spoken name (without «ال») → phone-side app id
_APP_NAMES: Dict[str, str] = {
    "خرايط": "maps", "خريطه": "maps", "خرائط": "maps", "ماب": "maps", "ماپ": "maps",
    "جوجل ماب": "maps", "جوجل مابس": "maps", "مابس": "maps",
    "واتساب": "whatsapp", "واتس اب": "whatsapp", "واتس": "whatsapp",
    "يوتيوب": "youtube",
    "سبوتيفاي": "spotify",
    "كاميرا": "camera",
    "تيليجرام": "telegram", "تليجرام": "telegram",
}

# Media requests → generic audio app with a hint (Level 0 per §14.2)
_MEDIA_HINTS: Dict[str, str] = {
    "قران": "quran", "قرآن": "quran", "اذان": "adhan",
    "اغنيه": "song", "اغاني": "song", "اغنية": "song", "موسيقي": "song", "موسيقى": "song",
    "بودكاست": "podcast",
}

_FILLER_PREFIX = re.compile(
    r"^(?:(?:يا\s+)?(?:توام|روبوت|نيبولا|توت)\s+)?(?:(?:لو\s+سمحت|ممكن|من\s+فضلك|عايز|عاوز)\s+)*"
)

_SENSITIVE_PATTERNS = [
    (re.compile(r"^(?:امسح|احذف|فضي)\s+(?:كل\s+)?(?:ال)?(?:ذاكره|ذكريات|حاجه|بيانات)"), "memory_wipe"),
    (re.compile(r"^(?:فرمت|ريسيت|اعاده\s+ضبط)"), "memory_wipe"),
    (re.compile(r"^(?:ادفع|(?:حول|حولي)\s+(?:\d+|فلوس|مبلغ|المبلغ))"), "payment"),
    (re.compile(r"^(?:ضيف|اضف|سجل)\s+(?:مستخدم|شخص|حد)\s+جديد|^اضافه\s+مستخدم"), "add_user"),
    (re.compile(r"^(?:غير|عدل)\s+(?:ال)?صلاحيات"), "change_permissions"),
]

_READ_NOTIF = re.compile(
    r"^(?:اقرا(?:\s*)(?:لي|ل)?|اقراه?لي)\s+(?:ال)?(?:رسايل|رسائل|اشعارات|ايميلات)(?:\s+.*)?$"
)

_REMINDER_ABS = re.compile(
    r"^فكرني\s+(?:(?:ان|اني|انو)\s+|ب(?=ال))?(?P<title>.+?)\s+(?:ال)?ساعه\s+(?P<time>.+)$"
)
_REMINDER_REL = re.compile(
    r"^فكرني\s+(?:(?:ان|اني|انو)\s+|ب(?=ال))?(?P<title>.+?)\s+(?:كمان|بعد)\s+(?P<n>\S+)\s+"
    r"(?P<unit>دقيقه|دقايق|دقيقة|ساعه|ساعات|ساعة)$"
)

_CALL = re.compile(r"^(?:كلم|كلمي|كلملي|اتصل|رن\s+علي)\s+(?P<rest>.+)$")
_MSG = re.compile(
    r"^(?:ابعت(?:له|لها|لو)?|ارسل|بعت)\s+(?:رساله\s+)?(?P<rest>.+)$"
)
_OPEN_APP = re.compile(r"^(?:افتح|فتح|شغل|ورجيني)\s+(?P<app>.+?)(?:\s+و?(?:وديني|وصلني|خدني)\s+(?P<dest>.+))?$")
_NAVIGATE = re.compile(r"^(?:وديني|وصلني|خدني|طريق)\s+(?:ل|الي|علي)?\s*(?P<dest>.+)$")


@dataclass(frozen=True)
class Intent:
    kind: str
    # call/msg: text after the verb («ماما» or «لأحمد إني جاي متأخر») — resolved by contacts.py
    raw_light: str = ""
    raw_norm: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


def _app_id(spoken_norm: str) -> Optional[str]:
    name = spoken_norm.strip()
    if name.startswith("ال") and len(name) > 3:
        name = name[2:]
    return _APP_NAMES.get(name)


class ActionPlanner:
    """plan(transcript) → Intent | None  (None ⇒ ordinary conversation → LLM)."""

    def plan(self, transcript: str) -> Optional[Intent]:
        light, norm = prepare(transcript)
        if not norm:
            return None
        m = _FILLER_PREFIX.match(norm)
        cut = m.end() if m else 0
        light, norm = light[cut:], norm[cut:]
        if not norm:
            return None

        # 1) Level-3 sensitive operations first (must never be shadowed)
        for pat, op in _SENSITIVE_PATTERNS:
            if pat.search(norm):
                return Intent(SENSITIVE, params={"op": op})

        # 2) Notifications
        if _READ_NOTIF.match(norm):
            return Intent(READ_NOTIFICATIONS)

        # 3) Reminders
        rel = _REMINDER_REL.match(norm)
        if rel:
            return self._reminder_relative(light, norm, rel)
        ab = _REMINDER_ABS.match(norm)
        if ab:
            return self._reminder_absolute(light, norm, ab)

        # 4) Calls / messages
        cm = _CALL.match(norm)
        if cm:
            s = cm.start("rest")
            return Intent(CALL, raw_light=light[s:].strip(), raw_norm=norm[s:].strip())
        mm = _MSG.match(norm)
        if mm:
            s = mm.start("rest")
            return Intent(MSG, raw_light=light[s:].strip(), raw_norm=norm[s:].strip())

        # 5) Open app / media / navigation
        om = _OPEN_APP.match(norm)
        if om:
            spoken = om.group("app").strip()
            dest = om.group("dest")
            app_id = _app_id(spoken)
            if app_id:
                query = None
                if dest:
                    ds = om.start("dest")
                    query = sanitize_destination(light[ds:])
                return Intent(APP_OPEN, params={"app": app_id, "query": query or None})
            hint = _media_hint(spoken)
            if hint and norm.startswith("شغل"):
                return Intent(APP_OPEN, params={"app": "music", "query": hint})
            if norm.startswith(("افتح", "فتح")):
                # Unknown app requested → let the Guard refuse explicitly
                return Intent(APP_OPEN, params={"app": None, "requested": sanitize_free_text(spoken, 32)})
            return None  # e.g. «شغل النور» → not a phone action

        nm = _NAVIGATE.match(norm)
        if nm:
            ds = nm.start("dest")
            q = sanitize_destination(light[ds:])
            if q:
                return Intent(APP_OPEN, params={"app": "maps", "query": q})
        return None

    # ── reminders ────────────────────────────────────────────────────────

    @staticmethod
    def _clean_title(title_light: str) -> str:
        t = title_light.strip()
        if t.startswith("بال"):
            t = t[1:]
        return sanitize_free_text(t, 120)

    def _reminder_relative(self, light: str, norm: str, m: "re.Match[str]") -> Optional[Intent]:
        n = parse_int(m.group("n"))
        if n is None or n <= 0 or n > 24 * 60:
            return None
        unit = m.group("unit")
        minutes = n if unit.startswith("دقيق") or unit.startswith("دقاي") else n * 60
        if minutes > 24 * 60:
            return None
        ts, te = m.span("title")
        title = self._clean_title(light[ts:te])
        if not title:
            return None
        return Intent(REMINDER, params={"title": title, "rel_minutes": minutes})

    def _reminder_absolute(self, light: str, norm: str, m: "re.Match[str]") -> Optional[Intent]:
        parsed = parse_time_phrase(m.group("time"))
        if parsed is None:
            return None
        ts, te = m.span("title")
        title = self._clean_title(light[ts:te])
        if not title:
            return None
        hour, minute, period = parsed
        return Intent(REMINDER, params={"title": title, "hour": hour, "minute": minute, "period": period})


def _media_hint(spoken_norm: str) -> Optional[str]:
    name = spoken_norm.strip()
    if name.startswith("ال") and len(name) > 3:
        name = name[2:]
    for k, v in _MEDIA_HINTS.items():
        if name.startswith(k):
            return v
    return None


# ── time helpers (pure → unit-testable) ──────────────────────────────────────

_PM_WORDS = ("بالليل", "بليل", "الليل", "مساء", "المسا", "المغرب", "العصر", "بعد الظهر", "العشا")
_AM_WORDS = ("الصبح", "صباحا", "بدري", "الفجر", "صبح")


def parse_time_phrase(phrase_norm: str) -> Optional[tuple[int, int, Optional[str]]]:
    """«8» / «8:30» / «8 ونص» / «تمانية الصبح» → (hour, minute, 'am'|'pm'|None)."""
    text = phrase_norm.strip()
    period: Optional[str] = None
    for w in _PM_WORDS:
        if w in text:
            period = "pm"
            text = text.replace(w, " ")
    for w in _AM_WORDS:
        if w in text:
            period = "am"
            text = text.replace(w, " ")
    text = text.strip()

    minute = 0
    colon = re.match(r"^(\d{1,2}):(\d{2})\b", text)
    if colon:
        hour, minute = int(colon.group(1)), int(colon.group(2))
        rest = text[colon.end():]
    else:
        toks = text.split()
        if not toks:
            return None
        h = parse_int(toks[0])
        if h is None:
            return None
        hour = h
        rest = " ".join(toks[1:])
    if "ونص" in rest or "و نص" in rest:
        minute = 30
    elif "وربع" in rest or "و ربع" in rest:
        minute = 15
    elif "الا ربع" in rest:
        hour = (hour - 1) if hour > 1 else 12
        minute = 45
    elif "وثلث" in rest:
        minute = 20
    if not (0 <= hour <= 24) or not (0 <= minute < 60):
        return None
    if hour == 24:
        hour = 0
    return hour, minute, period


def compute_target_time(params: Dict[str, Any], now_local: datetime) -> datetime:
    """
    Resolve reminder params to the NEXT matching local datetime (> now).
    With no am/pm hint and an ambiguous 12h hour, the sooner occurrence wins.
    """
    if "rel_minutes" in params:
        return now_local + timedelta(minutes=int(params["rel_minutes"]))
    hour, minute, period = params["hour"], params["minute"], params.get("period")
    candidates = []
    if hour > 12 or hour == 0:
        hours = [hour % 24]
    elif period == "am":
        hours = [0 if hour == 12 else hour]
    elif period == "pm":
        hours = [12 if hour == 12 else hour + 12]
    else:
        hours = [hour % 12, (hour % 12) + 12]
    for h in hours:
        cand = now_local.replace(hour=h, minute=minute, second=0, microsecond=0)
        if cand <= now_local:
            cand += timedelta(days=1)
        candidates.append(cand)
    return min(candidates)
