"""
Universal Action Engine — Comprehensive, Multi-Domain System Action Planner,
Security Gatekeeper & LLM Integrator.

Covers ANY action across the entire Nebula ecosystem:
  1. MOTION:    Gestures (wave, like, nod, greet), head tracking, wheel motors, stop.
  2. SCREEN:    Eyes mood (happy, sad, surprised, etc.), gaze tracking, desktop display, photo display.
  3. VISION:    Camera snapshot, identify person, track face.
  4. DEVICE:    IoT relay / light toggle, battery status, distance sensor telemetry.
  5. PHONE:     Call allowlisted contacts, send messages, open apps, read notifications.
  6. REMINDER:  Create, list, and acknowledge reminders.
  7. MEDIA:     Play music/quran, pause, volume control.
  8. SENSITIVE: Level-3 operations (wipe memories, payments, permissions).

Dual Integration:
  - Method 1: Metadata (ContextBuilder, GroundingInfo, PromptBuilder).
  - Method 2: API (Universal Parse, Execute, Capabilities for LLM Tool Calling).

Strictly Deterministic Execution.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Sequence
from pydantic import BaseModel, Field

from app.core.logger import get_logger
from app.services.phone_action.textutil import (
    fold,
    prepare,
    strip_marks,
    sanitize_free_text,
    sanitize_destination,
    parse_int,
    HOUR_WORDS,
)

logger = get_logger(__name__)


class ActionDomain(str, Enum):
    MOTION = "motion"
    SCREEN = "screen"
    VISION = "vision"
    DEVICE = "device"
    PHONE = "phone"
    REMINDER = "reminder"
    MEDIA = "media"
    SENSITIVE = "sensitive"


@dataclass
class UniversalIntent:
    domain: str
    action: str
    target: Optional[str] = None
    params: Dict[str, Any] = field(default_factory=dict)
    required_level: int = 1       # 1: Safe/Public, 2: Personal/Device, 3: Sensitive/Dangerous
    channel: str = "internal"     # esp | phone | desk | internal
    action_tag: Optional[str] = None
    raw_utterance: str = ""


class UniversalActionParseResponse(BaseModel):
    has_action: bool
    domain: Optional[str] = None
    action: Optional[str] = None
    target: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    required_level: int = 1
    is_verified: bool = False
    is_authorized: bool = False
    decision: str  # ready | needs_confirm | unverified_speaker | unknown_contact | app_not_allowed | unsupported_action | none
    suggested_speech: str = ""
    llm_directive: str = ""
    action_tag: Optional[str] = None
    execution_payload: Optional[Dict[str, Any]] = None
    tool_call: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UniversalActionExecuteRequest(BaseModel):
    domain: str
    action: str
    target: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    speaker_name: Optional[str] = None
    is_verified: bool = False
    verification_level: int = 1


class UniversalActionExecuteResponse(BaseModel):
    ok: bool
    status: str
    dispatched_channel: str
    action: str
    payload: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# ── Action Capabilities Registry (for LLM Tool Calling / Function Schemas) ────

UNIVERSAL_CAPABILITIES_REGISTRY: List[Dict[str, Any]] = [
    # 1. Motion
    {
        "domain": ActionDomain.MOTION.value,
        "action": "wave",
        "description": "لوّح بيدك للترحيب أو لفت الانتباه (Wave gesture).",
        "required_level": 1,
        "channel": "esp",
        "tag": "[wave]",
        "parameters": {},
    },
    {
        "domain": ActionDomain.MOTION.value,
        "action": "like",
        "description": "إشارة الإعجاب بالإبهام لأعلى (Thumbs up / Like).",
        "required_level": 1,
        "channel": "esp",
        "tag": "[like]",
        "parameters": {},
    },
    {
        "domain": ActionDomain.MOTION.value,
        "action": "greet",
        "description": "تحية رسمية برفع الذراع وفتح اليد (Formal greeting).",
        "required_level": 1,
        "channel": "esp",
        "tag": "[greet]",
        "parameters": {},
    },
    {
        "domain": ActionDomain.MOTION.value,
        "action": "nod",
        "description": "إيماءة بالرأس للموافقة أو التأكيد (Nod head).",
        "required_level": 1,
        "channel": "esp",
        "tag": "[nod]",
        "parameters": {},
    },
    {
        "domain": ActionDomain.MOTION.value,
        "action": "shake_head",
        "description": "هز الرأس للرفض أو النفي (Shake head).",
        "required_level": 1,
        "channel": "esp",
        "tag": "[shake_head]",
        "parameters": {},
    },
    {
        "domain": ActionDomain.MOTION.value,
        "action": "look_direction",
        "description": "توجيه الرأس إلى اليمين أو اليسار أو المنتصف.",
        "required_level": 1,
        "channel": "esp",
        "tag": "[look_center]",
        "parameters": {"direction": {"type": "string", "enum": ["left", "right", "center"]}},
    },
    {
        "domain": ActionDomain.MOTION.value,
        "action": "stop",
        "description": "إيقاف فوري لجميع حركات ومحركات الروبوت (Emergency Stop).",
        "required_level": 1,
        "channel": "esp",
        "tag": "[stop]",
        "parameters": {},
    },
    {
        "domain": ActionDomain.MOTION.value,
        "action": "drive_wheels",
        "description": "قيادة عجلات الروبوت للأمام أو الخلف أو الدوران (يتطلب بصمة صوت موثقة Level 2).",
        "required_level": 2,
        "channel": "esp",
        "parameters": {
            "direction": {"type": "string", "enum": ["forward", "backward", "left", "right"]},
            "speed": {"type": "integer", "minimum": 50, "maximum": 255, "default": 150},
            "duration_ms": {"type": "integer", "default": 1000},
        },
    },

    # 2. Screen & Eyes
    {
        "domain": ActionDomain.SCREEN.value,
        "action": "eyes_mood",
        "description": "تغيير تعبيرات عيون الروبوت على شاشة الهاتف.",
        "required_level": 1,
        "channel": "phone",
        "parameters": {
            "mood": {"type": "string", "enum": ["happy", "sad", "surprised", "neutral", "thinking", "alert"]},
        },
    },
    {
        "domain": ActionDomain.SCREEN.value,
        "action": "gaze",
        "description": "توجيه نظرة العينين بإحداثيات x و y على الشاشة.",
        "required_level": 1,
        "channel": "phone",
        "parameters": {
            "x": {"type": "number", "minimum": -1.0, "maximum": 1.0},
            "y": {"type": "number", "minimum": -1.0, "maximum": 1.0},
        },
    },
    {
        "domain": ActionDomain.SCREEN.value,
        "action": "show_person_photo",
        "description": "عرض صورة الشخص المسجّل على شاشة سطح المكتب.",
        "required_level": 1,
        "channel": "desk",
        "parameters": {"person_name": {"type": "string"}},
    },
    {
        "domain": ActionDomain.SCREEN.value,
        "action": "desktop_screen_control",
        "description": "فتح لوحة التحكم بالشاشة أو أخذ لقطة سطح المكتب.",
        "required_level": 2,
        "channel": "desk",
        "parameters": {"command": {"type": "string"}},
    },

    # 3. Vision & Camera
    {
        "domain": ActionDomain.VISION.value,
        "action": "capture_photo",
        "description": "التقاط صورة فوتوغرافية بواسطة كاميرا الروبوت (Level 2).",
        "required_level": 2,
        "channel": "phone",
        "parameters": {},
    },
    {
        "domain": ActionDomain.VISION.value,
        "action": "identify_person",
        "description": "التعرف البصري الفوري على الشخص المقابل للكاميرا.",
        "required_level": 1,
        "channel": "internal",
        "parameters": {},
    },
    {
        "domain": ActionDomain.VISION.value,
        "action": "track_face",
        "description": "تتبع وجه شخص محدد أمام الروبوت بحركات الرأس والعينين.",
        "required_level": 1,
        "channel": "internal",
        "parameters": {"name": {"type": "string"}},
    },

    # 4. Device & IoT
    {
        "domain": ActionDomain.DEVICE.value,
        "action": "light_toggle",
        "description": "تشغيل أو إطفاء إضاءة الروبوت أو الريلاي المتصل بالـ ESP32.",
        "required_level": 2,
        "channel": "esp",
        "parameters": {"state": {"type": "boolean"}},
    },
    {
        "domain": ActionDomain.DEVICE.value,
        "action": "check_battery",
        "description": "قراءة قياسات جهد وشحن بطارية الروبوت الحالية.",
        "required_level": 1,
        "channel": "esp",
        "parameters": {},
    },
    {
        "domain": ActionDomain.DEVICE.value,
        "action": "check_distance",
        "description": "قراءة حساس الموجات فوق الصوتية لقياس المسافة للأجسام المقابلة.",
        "required_level": 1,
        "channel": "esp",
        "parameters": {},
    },

    # 5. Phone & Communication
    {
        "domain": ActionDomain.PHONE.value,
        "action": "call",
        "description": "إجراء مكالمة هاتفية مع جهة اتصال مسموحة في القائمة البيضاء.",
        "required_level": 1,
        "channel": "phone",
        "parameters": {"contact_name": {"type": "string"}},
    },
    {
        "domain": ActionDomain.PHONE.value,
        "action": "msg",
        "description": "إرسال رسالة نصية أو واتساب إلى جهة اتصال مسجلة وموثقة (Level 2).",
        "required_level": 2,
        "channel": "phone",
        "parameters": {
            "contact_name": {"type": "string"},
            "text": {"type": "string"},
            "app": {"type": "string", "enum": ["whatsapp", "sms", "telegram"], "default": "whatsapp"},
        },
    },
    {
        "domain": ActionDomain.PHONE.value,
        "action": "app_open",
        "description": "فتح تطبيق مدعوم ومسموح على الهاتف (maps, whatsapp, youtube, spotify, camera, telegram).",
        "required_level": 1,
        "channel": "phone",
        "parameters": {
            "app_id": {"type": "string"},
            "query": {"type": "string"},
        },
    },
    {
        "domain": ActionDomain.PHONE.value,
        "action": "read_notifications",
        "description": "قراءة الإشعارات والرسائل الواردة شفهياً (Level 2).",
        "required_level": 2,
        "channel": "phone",
        "parameters": {},
    },

    # 6. Reminders
    {
        "domain": ActionDomain.REMINDER.value,
        "action": "create_reminder",
        "description": "إنشاء تذكير بموعد دواء أو مهمة محددة.",
        "required_level": 1,
        "channel": "phone",
        "parameters": {
            "title": {"type": "string"},
            "target_time": {"type": "string"},
        },
    },
    {
        "domain": ActionDomain.REMINDER.value,
        "action": "list_reminders",
        "description": "استعراض التذكيرات النشطة والقادمة.",
        "required_level": 1,
        "channel": "internal",
        "parameters": {},
    },

    # 7. Media
    {
        "domain": ActionDomain.MEDIA.value,
        "action": "play_media",
        "description": "تشغيل مقطع صوتي، موسيقى، قرآن، أو بودكاست.",
        "required_level": 1,
        "channel": "phone",
        "parameters": {
            "query": {"type": "string"},
            "category": {"type": "string", "enum": ["music", "quran", "podcast"]},
        },
    },
    {
        "domain": ActionDomain.MEDIA.value,
        "action": "stop_media",
        "description": "إيقاف تشغيل الوسائط أو كتم الصوت.",
        "required_level": 1,
        "channel": "phone",
        "parameters": {},
    },
    {
        "domain": ActionDomain.MEDIA.value,
        "action": "volume_control",
        "description": "تعديل مستوى الصوت (رفع أو خفض أو كتم).",
        "required_level": 1,
        "channel": "phone",
        "parameters": {"command": {"type": "string", "enum": ["up", "down", "mute"]}},
    },

    # 8. Sensitive (Level 3)
    {
        "domain": ActionDomain.SENSITIVE.value,
        "action": "memory_wipe",
        "description": "مسح ذكريات الروبوت أو إعادة ضبط المصنع (حساس جداً - Level 3).",
        "required_level": 3,
        "channel": "desk",
        "parameters": {},
    },
    {
        "domain": ActionDomain.SENSITIVE.value,
        "action": "payment",
        "description": "إجراء معاملات مالية أو مدفوعات (حساس جداً - Level 3).",
        "required_level": 3,
        "channel": "desk",
        "parameters": {},
    },
]


def get_action_capabilities() -> List[Dict[str, Any]]:
    """Return the entire registry of executable capabilities for LLM function calling / tools."""
    return UNIVERSAL_CAPABILITIES_REGISTRY


# ── Action Vocabulary & Regular Expressions ───────────────────────────────────

_FILLER = re.compile(
    r"^(?:(?:يا\s+)?(?:توام|روبوت|نيبولا|توت)\s+)?(?:(?:لو\s+سمحت|ممكن|من\s+فضلك|عايز|عاوز|اريدك|اعمل|سوي)\s+)*"
)

# 1. Motion Patterns
_PATTERNS_MOTION = [
    # Wave / Hand gestures
    (re.compile(r"^(?:لوح|شاور|لوحلي|سلم|شاورلي|لوح\s+بايدك|شاور\s+بايدك|تلويح|wave)"), "wave", 1, "[wave]", "تلويح باليد"),
    (re.compile(r"^(?:اعمل\s+لايك|ارفع\s+ابهامك|لايك|like|عاش)"), "like", 1, "[like]", "إشارة الإعجاب"),
    (re.compile(r"^(?:حيي|حيينا|تحيه|تحية|greet)"), "greet", 1, "[greet]", "تحية رسمية"),
    (re.compile(r"^(?:اومئ|أومئ|هز\s+راسك\s+بنعم|هز\s+راسك\s+ايوه|nod|وافق)"), "nod", 1, "[nod]", "إيماءة موافقة"),
    (re.compile(r"^(?:هز\s+راسك\s+بلا|هز\s+راسك\s+بنفي|shake\s*head|ارفض)"), "shake_head", 1, "[shake_head]", "هز الرأس نفياً"),
    (re.compile(r"^(?:بص\s+يمين|انظر\s+يمين|انظر\s+يمينا|دور\s+يمين|look\s*right)"), "look_right", 1, "[look_right]", "توجيه النظر يميناً"),
    (re.compile(r"^(?:بص\s+شمال|انظر\s+شمال|انظر\s+يسارا|دور\s+شمال|look\s*left)"), "look_left", 1, "[look_left]", "توجيه النظر يساراً"),
    (re.compile(r"^(?:بص\s+قدام|انظر\s+للامام|بص\s+في\s+النص|look\s*center)"), "look_center", 1, "[look_center]", "توجيه النظر للأمام"),
    (re.compile(r"^(?:اقف|اثبت|فرمل|وقف|stop|توقف|بس\s+حركه)"), "stop", 1, "[stop]", "إيقاف الحركة"),
    # Wheels / Motors (Level 2)
    (re.compile(r"^(?:امشي\s+قدام|اتحرك\s+لقدام|امشي\s+للامام|سوق\s+لقدام|forward)"), "drive_forward", 2, None, "قيادة للأمام"),
    (re.compile(r"^(?:ارجع\s+لورا|ارجع\s+ورا|اتحرك\s+للخلف|backward)"), "drive_backward", 2, None, "قيادة للخلف"),
    (re.compile(r"^(?:لف\s+يمين|حود\s+يمين|دور\s+يمين)"), "turn_right", 2, None, "دوران يميناً"),
    (re.compile(r"^(?:لف\s+شمال|حود\s+شمال|دور\s+شمال)"), "turn_left", 2, None, "دوران يساراً"),
]

# 2. Screen / Mood / Display Patterns
_PATTERNS_SCREEN = [
    (re.compile(r"^(?:افرح|ابتسم|خلي\s+(?:عينيك|عينك)\s+(?:مبسوطه|سعيده|فرحانه)|(?:عينيك|عينك)\s+(?:مبسوطه|سعيده|فرحانه)|happy)"), "eyes_mood", 1, "[happy]", "تعبير السعادة", {"mood": "happy"}),
    (re.compile(r"^(?:ازعل|خلي\s+(?:عينيك|عينك)\s+حزينه|(?:عينيك|عينك)\s+حزينه|sad)"), "eyes_mood", 1, "[sad]", "تعبير الحزن", {"mood": "sad"}),
    (re.compile(r"^(?:اتفاجئ|خلي\s+(?:عينيك|عينك)\s+متفاجئه|surprised)"), "eyes_mood", 1, "[surprised]", "تعبير المفاجأة", {"mood": "surprised"}),
    (re.compile(r"^(?:فكر|خلي\s+(?:عينيك|عينك)\s+بتفكر|thinking)"), "eyes_mood", 1, "[thinking]", "تعبير التفكير", {"mood": "thinking"}),
    (re.compile(r"^(?:خلي\s+(?:عينيك|عينك)\s+عاديه|ارتاح|neutral)"), "eyes_mood", 1, "[neutral]", "تعبير محايد", {"mood": "neutral"}),
    (re.compile(r"^(?:خليك\s+حذر|خلي\s+(?:عينيك|عينك)\s+alert|alert)"), "eyes_mood", 1, "[alert]", "تعبير الانتباه", {"mood": "alert"}),
    (re.compile(r"^(?:بص\s+لفوق|انظر\s+لاعلي|gaze\s*up)"), "gaze", 1, None, "توجيه النظرة لأعلى", {"x": 0.0, "y": 1.0}),
    (re.compile(r"^(?:بص\s+لتحت|انظر\s+لاسفل|gaze\s*down)"), "gaze", 1, None, "توجيه النظرة لأسفل", {"x": 0.0, "y": -1.0}),
    (re.compile(r"^(?:تحكم\s+بالشاشه|افتح\s+لوحه\s+التحكم|سكرين\s*شوت)"), "desktop_screen_control", 2, None, "التحكم بالشاشة"),
]

# 3. Vision Patterns
_PATTERNS_VISION = [
    (re.compile(r"^(?:صورني|خد\s+صوره|خد\s+لقطه|التقط\s+صوره|افتح\s+الكاميرا\s+وصور)"), "capture_photo", 2, None, "التقاط صورة فوتوغرافية"),
    (re.compile(r"^(?:مين\s+اللي\s+قدامك|شايف\s+مين|اتعرف\s+علي\s+الشخص|مين\s+ده)"), "identify_person", 1, None, "التعرف البصري على الشخص"),
    (re.compile(r"^(?:ركز\s+علي\s+وش|اتبع\s+وش|تتبع\s+الوجه)\s*(?P<name>.*)"), "track_face", 1, None, "تتبع الوجه"),
]

# 4. Device / IoT Patterns
_PATTERNS_DEVICE = [
    (re.compile(r"^(?:شغل\s+النور|ولع\s+النور|افتح\s+الاضاءه|شغل\s+اللمبه|ولع\s+اللمبه)"), "light_toggle", 2, None, "تشغيل الإضاءة", {"state": True}),
    (re.compile(r"^(?:اطفي\s+النور|اقفل\s+النور|اطفي\s+الاضاءه|اطفي\s+اللمبه|اقفل\s+اللمبه)"), "light_toggle", 2, None, "إطفاء الإضاءة", {"state": False}),
    (re.compile(r"^(?:شوف\s+البطاريه|نسبه\s+الشحن|البطاريه\s+كام|حاله\s+البطاريه)"), "check_battery", 1, None, "فحص البطارية"),
    (re.compile(r"^(?:قيس\s+المسافه|المسافه\s+كام|في\s+حاجه\s+قدامك|حساس\s+المسافه)"), "check_distance", 1, None, "قياس المسافة"),
]

# 5. Media Patterns
_PATTERNS_MEDIA = [
    (re.compile(r"^(?:وقف\s+الصوت|وقف\s+الموسيقي|وقف\s+الاغنيه|وقف\s+الميديا|بس\s+صوت)"), "stop_media", 1, None, "إيقاف الصوت"),
    (re.compile(r"^(?:علي\s+الصوت|ارفع\s+الصوت)"), "volume_control", 1, None, "رفع الصوت", {"cmd": "up"}),
    (re.compile(r"^(?:وطي\s+الصوت|اخفض\s+الصوت)"), "volume_control", 1, None, "خفض الصوت", {"cmd": "down"}),
    (re.compile(r"^(?:اكتم\s+الصوت|ميوت|اسكت)"), "volume_control", 1, None, "كتم الصوت", {"cmd": "mute"}),
    (re.compile(r"^(?:شغل\s+)?(?:موسيقي|موسيقى|اغنيه|اغاني|سوره|قران|قرآن|بودكاست)\s*(?P<query>.*)"), "play_media", 1, None, "تشغيل الوسائط"),
]

# 6. Sensitive (Level 3) Patterns
_PATTERNS_SENSITIVE = [
    (re.compile(r"^(?:امسح|احذف|فضي)\s+(?:كل\s+)?(?:ال)?(?:ذاكره|ذكريات|بيانات|حاجه)"), "memory_wipe", 3, None, "مسح الذكريات"),
    (re.compile(r"^(?:فرمت|ريسيت|اعاده\s+ضبط\s+المصنع)"), "memory_wipe", 3, None, "إعادة ضبط المصنع"),
    (re.compile(r"^(?:ادفع|(?:حول|حولي)\s+(?:\d+|فلوس|مبلغ|المبلغ))"), "payment", 3, None, "معاملة مالية"),
    (re.compile(r"^(?:غير|عدل)\s+(?:ال)?صلاحيات|^اضافه\s+مستخدم"), "change_permissions", 3, None, "تعديل الصلاحيات"),
]

# Supported Apps Vocabulary
_APP_NAMES: Dict[str, str] = {
    "خرايط": "maps", "خريطه": "maps", "خرائط": "maps", "ماب": "maps", "ماپ": "maps",
    "جوجل ماب": "maps", "جوجل مابس": "maps", "مابس": "maps",
    "واتساب": "whatsapp", "واتس اب": "whatsapp", "واتس": "whatsapp",
    "يوتيوب": "youtube",
    "سبوتيفاي": "spotify",
    "كاميرا": "camera",
    "تيليجرام": "telegram", "تليجرام": "telegram",
    "صوتيات": "music", "موسيقى": "music",
}

_APP_DISPLAY = {
    "maps": "الخرايط", "whatsapp": "واتساب", "youtube": "يوتيوب", "spotify": "سبوتيفاي",
    "camera": "الكاميرا", "telegram": "تيليجرام", "music": "الصوتيات",
}


class UniversalActionPlanner:
    """
    Unified, Deterministic Rule-Based Action Planner covering ALL domains.
    Guarantees explicit deterministic decisions on every query.
    """

    def plan_raw(self, utterance: str) -> Optional[UniversalIntent]:
        """Classify utterance into a UniversalIntent without checking security credentials."""
        light, norm = prepare(utterance)
        if not norm:
            return None

        m = _FILLER.match(norm)
        cut = m.end() if m else 0
        light, norm = light[cut:], norm[cut:]
        if not norm:
            return None

        # 1. Level-3 Sensitive Operations (Always highest priority)
        for pat, act, lvl, tag, desc in _PATTERNS_SENSITIVE:
            if pat.search(norm):
                return UniversalIntent(
                    domain=ActionDomain.SENSITIVE.value,
                    action=act,
                    target=desc,
                    required_level=lvl,
                    channel="desk",
                    raw_utterance=utterance,
                )

        # 2. Motion Patterns
        for pat, act, lvl, tag, desc in _PATTERNS_MOTION:
            if pat.search(norm):
                return UniversalIntent(
                    domain=ActionDomain.MOTION.value,
                    action=act,
                    target=desc,
                    required_level=lvl,
                    channel="esp",
                    action_tag=tag,
                    raw_utterance=utterance,
                )

        # 3. Screen / Mood / Display Patterns
        for item in _PATTERNS_SCREEN:
            pat, act, lvl, tag, desc = item[0], item[1], item[2], item[3], item[4]
            params = item[5] if len(item) > 5 else {}
            if pat.search(norm):
                return UniversalIntent(
                    domain=ActionDomain.SCREEN.value,
                    action=act,
                    target=desc,
                    params=params,
                    required_level=lvl,
                    channel="phone" if act in ("eyes_mood", "gaze") else "desk",
                    action_tag=tag,
                    raw_utterance=utterance,
                )

        # Show Person Photo
        photo_m = re.match(r"^(?:اعرض|وريني|عرض|شوف)\s+(?:صوره|صورة)\s+(?P<name>.+)", norm)
        if photo_m:
            p_name = sanitize_free_text(photo_m.group("name"), 64)
            return UniversalIntent(
                domain=ActionDomain.SCREEN.value,
                action="show_person_photo",
                target=p_name,
                params={"person_name": p_name},
                required_level=1,
                channel="desk",
                raw_utterance=utterance,
            )

        # 4. Vision Patterns
        for pat, act, lvl, tag, desc in _PATTERNS_VISION:
            vm = pat.search(norm)
            if vm:
                params = vm.groupdict() if hasattr(vm, "groupdict") else {}
                target_val = params.get("name", desc)
                return UniversalIntent(
                    domain=ActionDomain.VISION.value,
                    action=act,
                    target=target_val,
                    params=params,
                    required_level=lvl,
                    channel="phone" if act == "capture_photo" else "internal",
                    raw_utterance=utterance,
                )

        # 5. Device / IoT Patterns
        for item in _PATTERNS_DEVICE:
            pat, act, lvl, tag, desc = item[0], item[1], item[2], item[3], item[4]
            params = item[5] if len(item) > 5 else {}
            if pat.search(norm):
                return UniversalIntent(
                    domain=ActionDomain.DEVICE.value,
                    action=act,
                    target=desc,
                    params=params,
                    required_level=lvl,
                    channel="esp",
                    raw_utterance=utterance,
                )

        # 6. Reminders Patterns
        # Acknowledge Reminder
        if re.search(r"^(?:اخدت\s+الدوا|تمام\s+التذكير|خلصت\s+التذكير|عملت\s+التذكير)", norm):
            return UniversalIntent(
                domain=ActionDomain.REMINDER.value,
                action="acknowledge_reminder",
                target="تأكيد تنفيذ التذكير",
                required_level=1,
                channel="phone",
                raw_utterance=utterance,
            )
        # List Reminders
        if re.search(r"^(?:ايه\s+التذكيرات|فكرني\s+باللي\s+ورايا|جدول\s+التذكيرات|التذكيرات\s+النشطه)", norm):
            return UniversalIntent(
                domain=ActionDomain.REMINDER.value,
                action="list_reminders",
                target="عرض التذكيرات النشطة",
                required_level=1,
                channel="internal",
                raw_utterance=utterance,
            )
        # Create Reminder
        rem_m = re.match(r"^فكرني\s+(?:(?:ان|اني|انو)\s+|ب(?=ال))?(?P<rest>.+)$", norm)
        if rem_m:
            title = sanitize_free_text(rem_m.group("rest"), 100)
            return UniversalIntent(
                domain=ActionDomain.REMINDER.value,
                action="create_reminder",
                target=title,
                params={"title": title},
                required_level=1,
                channel="phone",
                raw_utterance=utterance,
            )

        # 7. Media Patterns
        for item in _PATTERNS_MEDIA:
            pat, act, lvl, tag, desc = item[0], item[1], item[2], item[3], item[4]
            params = item[5] if len(item) > 5 else {}
            mm = pat.search(norm)
            if mm:
                if act == "play_media":
                    q = mm.groupdict().get("query", "").strip() or "موسيقى"
                    params = {"query": q}
                    desc = f"تشغيل {q}"
                return UniversalIntent(
                    domain=ActionDomain.MEDIA.value,
                    action=act,
                    target=desc,
                    params=params,
                    required_level=lvl,
                    channel="phone",
                    raw_utterance=utterance,
                )

        # 8. Phone / Call / Message / App Patterns
        # Read notifications
        if re.match(r"^(?:اقرا|اقراه?لي)\s+(?:ال)?(?:رسايل|رسائل|اشعارات|ايميلات)", norm):
            return UniversalIntent(
                domain=ActionDomain.PHONE.value,
                action="read_notifications",
                target="قراءة الإشعارات والرسائل",
                required_level=2,
                channel="phone",
                raw_utterance=utterance,
            )

        # Calls: كلم / اتصل بـ / رن على
        call_m = re.match(r"^(?:كلم|كلمي|كلملي|اتصل|رن\s+علي)\s+(?P<target>.+)$", norm)
        if call_m:
            tgt = sanitize_free_text(call_m.group("target"), 64)
            return UniversalIntent(
                domain=ActionDomain.PHONE.value,
                action="call",
                target=tgt,
                params={"requested_contact": tgt},
                required_level=1,
                channel="phone",
                raw_utterance=utterance,
            )

        # Messages: ابعت رسالة لـ
        msg_m = re.match(r"^(?:ابعت|ارسل|بعت)\s+(?:رساله\s+)?(?:ل|الي|علي)?\s*(?P<target>[^\s]+)\s*(?P<text>.*)$", norm)
        if msg_m:
            tgt = sanitize_free_text(msg_m.group("target"), 64)
            txt = sanitize_free_text(msg_m.group("text"), 300)
            return UniversalIntent(
                domain=ActionDomain.PHONE.value,
                action="msg",
                target=tgt,
                params={"requested_contact": tgt, "text": txt},
                required_level=2,
                channel="phone",
                raw_utterance=utterance,
            )

        # Open App: افتح / شغل
        open_m = re.match(r"^(?:افتح|فتح|شغل)\s+(?P<app>[^\s]+)(?:\s+(?P<dest>.+))?$", norm)
        if open_m:
            app_raw = open_m.group("app").strip()
            if app_raw.startswith("ال") and len(app_raw) > 3:
                app_raw_stripped = app_raw[2:]
            else:
                app_raw_stripped = app_raw

            app_id = _APP_NAMES.get(app_raw_stripped) or _APP_NAMES.get(app_raw)
            dest = open_m.group("dest")
            if app_id:
                app_name = _APP_DISPLAY.get(app_id, app_raw)
                return UniversalIntent(
                    domain=ActionDomain.PHONE.value,
                    action="app_open",
                    target=app_name,
                    params={"app_id": app_id, "app_name": app_name, "query": dest},
                    required_level=1,
                    channel="phone",
                    raw_utterance=utterance,
                )
            elif norm.startswith(("افتح", "فتح")):
                # Explicitly requested an app that is not in allowlist
                return UniversalIntent(
                    domain=ActionDomain.PHONE.value,
                    action="app_open",
                    target=app_raw,
                    params={"app_id": None, "requested": app_raw},
                    required_level=1,
                    channel="phone",
                    raw_utterance=utterance,
                )

        # Check for explicit action verbs that are unsupported
        action_verbs = ("اطبخ", "طير", "اقفز", "اغسل", "نظف", "سافر", "اشتر", "بيع")
        if any(norm.startswith(v) for v in action_verbs):
            return UniversalIntent(
                domain="unsupported",
                action="unsupported",
                target=utterance,
                required_level=1,
                channel="internal",
                raw_utterance=utterance,
            )

        return None

    def evaluate(
        self,
        utterance: str,
        speaker_name: Optional[str] = None,
        is_verified: bool = False,
        verification_level: int = 1,
        is_main: bool = False,
        allowlisted_contacts: Optional[Sequence[Any]] = None,
    ) -> UniversalActionParseResponse:
        """
        Evaluate utterance into a structured UniversalActionParseResponse.
        Enforces deterministic security rules:
        - Exact security level matching.
        - Exact allowlist contact matching.
        - Refusal is deterministic and unambiguous.
        """
        intent = self.plan_raw(utterance)

        if not intent:
            return UniversalActionParseResponse(
                has_action=False,
                decision="none",
                is_verified=is_verified,
                is_authorized=False,
                metadata={},
            )

        # Handle unsupported actions
        if intent.domain == "unsupported" or intent.action == "unsupported":
            return UniversalActionParseResponse(
                has_action=True,
                domain="unsupported",
                action="unsupported",
                target=intent.target,
                required_level=intent.required_level,
                is_verified=is_verified,
                is_authorized=False,
                decision="unsupported_action",
                suggested_speech="مش قادر أنفذ الطلب ده لأنه غير مدعوم في إمكانيات الروبوت حالياً.",
                llm_directive=f"طلب المستخدم إجراءً غير مدعوم ('{intent.target}'). ارفض الطلب صراحة واذكر أنه غير متاح، ولا تحاول اختلاق بديل أو استدعاء نموذج آخر.",
                metadata={"raw_utterance": utterance},
            )

        # ── 1. Security & Speaker Verification Check ──
        req_level = intent.required_level
        if req_level >= 2 and not is_verified:
            speech = "الطلب ده محتاج أتأكد من بصمة صوتك الأول." if req_level == 2 else "الطلب ده حساس ولازم أتأكد من بصمة صوتك ومن غرفة التحكم."
            directive = (
                f"طلب المستخدم إجراء '{intent.target}' وهو يتطلب مستوى أمان Level {req_level} وتوثيق بصمة الصوت. "
                "بصمة الصوت غير موثقة حالياً، ارفض التنفيذ بأدب وطالبه بتوثيق بصمة صوته أولاً."
            )
            return UniversalActionParseResponse(
                has_action=True,
                domain=intent.domain,
                action=intent.action,
                target=intent.target,
                params=intent.params,
                required_level=req_level,
                is_verified=False,
                is_authorized=False,
                decision="unverified_speaker",
                suggested_speech=speech,
                llm_directive=directive,
                metadata={"required_level": req_level, "user_level": verification_level},
            )

        # ── 2. Domain-Specific Routing & Validation ──

        # Phone Domain (Calls & Messages)
        if intent.domain == ActionDomain.PHONE.value:
            if intent.action in ("call", "msg"):
                matched_contact = None
                raw_tgt = intent.target or ""
                norm_tgt = fold(strip_marks(raw_tgt)).strip()
                if norm_tgt.startswith("ال") and len(norm_tgt) > 3:
                    norm_tgt = norm_tgt[2:]

                if allowlisted_contacts:
                    from app.services.phone_action.contacts import match_contact
                    match = match_contact(norm_tgt, raw_tgt, allowlisted_contacts, require_full=(intent.action == "call"))
                    matched_contact = match.contact

                if matched_contact:
                    c_name = matched_contact.name
                    c_slug = getattr(matched_contact, "slug", "")
                    req_conf = getattr(matched_contact, "requires_confirmation", True)
                    decision = "needs_confirm" if req_conf else "ready"
                    if intent.action == "call":
                        speech = f"أكلم لك {c_name} دلوقتي؟" if req_conf else f"بتصل بـ {c_name} حالاً."
                        directive = (
                            f"المستخدم يطلب الاتصال بـ '{c_name}'. "
                            + ("اطلب منه تأكيد الاتصال شفهياً بلطف مع تضمين [like]."
                               if req_conf else
                               f"الاتصال بـ '{c_name}' مصرح به وجاهز، أكد له الاتصال فوراً مع تضمين [happy].")
                        )
                    else:
                        speech = f"تمام، هبعت لـ {c_name} حالاً."
                        directive = f"المستخدم يطلب إرسال رسالة إلى '{c_name}'. أكد له إرسال الرسالة."

                    payload = {
                        "t": "call" if intent.action == "call" else "msg",
                        "contact": c_name,
                        "slug": c_slug,
                    }
                    tool_call = {
                        "name": f"phone_{intent.action}",
                        "arguments": {"contact": c_name, "slug": c_slug},
                    }
                    return UniversalActionParseResponse(
                        has_action=True,
                        domain=ActionDomain.PHONE.value,
                        action=intent.action,
                        target=c_name,
                        params={"contact_name": c_name, "slug": c_slug, **intent.params},
                        required_level=req_level,
                        is_verified=is_verified,
                        is_authorized=True,
                        decision=decision,
                        suggested_speech=speech,
                        llm_directive=directive,
                        action_tag="[like]" if req_conf else "[happy]",
                        execution_payload=payload,
                        tool_call=tool_call,
                        metadata={"contact_slug": c_slug},
                    )
                else:
                    return UniversalActionParseResponse(
                        has_action=True,
                        domain=ActionDomain.PHONE.value,
                        action=intent.action,
                        target=raw_tgt,
                        required_level=req_level,
                        is_verified=is_verified,
                        is_authorized=False,
                        decision="unknown_contact",
                        suggested_speech="مش لاقي الاسم ده في جهات الاتصال المسموحة.",
                        llm_directive=f"طلب المستخدم التواصل مع '{raw_tgt}' وهو غير مسجل في جهات الاتصال المسموحة. ارفض الطلب بأدب واذكر: 'مش لاقي الاسم ده في جهات الاتصال المسموحة.'",
                        metadata={"requested_target": raw_tgt},
                    )

            elif intent.action == "app_open":
                app_id = intent.params.get("app_id")
                app_name = intent.params.get("app_name") or intent.target
                if app_id:
                    return UniversalActionParseResponse(
                        has_action=True,
                        domain=ActionDomain.PHONE.value,
                        action="app_open",
                        target=app_name,
                        params=intent.params,
                        required_level=1,
                        is_verified=is_verified,
                        is_authorized=True,
                        decision="ready",
                        suggested_speech=f"تمام، بفتحلك {app_name} حالاً.",
                        llm_directive=f"المستخدم يطلب فتح تطبيق {app_name}. أكد له أن التطبيق قيد الفتح الآن مع تضمين الوسم [happy].",
                        action_tag="[happy]",
                        execution_payload={"t": "app", "cmd": "open", "app": app_id},
                        tool_call={"name": "phone_open_app", "arguments": {"app_id": app_id}},
                        metadata=intent.params,
                    )
                else:
                    req_app = intent.params.get("requested", intent.target)
                    return UniversalActionParseResponse(
                        has_action=True,
                        domain=ActionDomain.PHONE.value,
                        action="app_open",
                        target=req_app,
                        params=intent.params,
                        required_level=1,
                        is_verified=is_verified,
                        is_authorized=False,
                        decision="app_not_allowed",
                        suggested_speech="التطبيق ده مش مسموح أفتحه.",
                        llm_directive=f"التطبيق المطلوب ({req_app}) غير مصرح به على الهاتف. ارفض الطلب بأدب واذكر أنه غير مسموح.",
                        metadata={"requested": req_app},
                    )

            elif intent.action == "read_notifications":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.PHONE.value,
                    action="read_notifications",
                    target="الإشعارات والرسائل",
                    required_level=2,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="بقرألك الإشعارات والرسائل الجديدة حالاً.",
                    llm_directive="المستخدم يطلب قراءة الإشعارات والرسائل الواردة. أكد له قراءتها بأمان.",
                    execution_payload={"t": "app", "cmd": "read_notifications"},
                    tool_call={"name": "phone_read_notifications", "arguments": {}},
                )

        # Motion Domain
        if intent.domain == ActionDomain.MOTION.value:
            tag = intent.action_tag or f"[{intent.action}]"
            payload = {"t": "signal", "name": intent.action} if intent.action != "stop" else {"t": "stop"}
            if "drive" in intent.action or "turn" in intent.action:
                speech = f"تمام، بتحرك {intent.target}."
                directive = f"المستخدم يطلب قيادة الروبوت ({intent.target}). أكد له الحركة بحذر."
                payload = {"t": "motor_cmd", "action": intent.action}
            elif intent.action == "stop":
                speech = "وقفت كل الحركات فوراً."
                directive = "المستخدم يطلب إيقاف حركة الروبوت (Emergency Stop). أكد له التوقف الفوري مع تضمين [stop]."
            else:
                speech = f"تمام، بنفّذ {intent.target}."
                directive = f"المستخدم يطلب حركة {intent.target}. رد بلطف وضمن وسم الحركة {tag} في إجابتك."

            return UniversalActionParseResponse(
                has_action=True,
                domain=ActionDomain.MOTION.value,
                action=intent.action,
                target=intent.target,
                params=intent.params,
                required_level=req_level,
                is_verified=is_verified,
                is_authorized=True,
                decision="ready",
                suggested_speech=speech,
                llm_directive=directive,
                action_tag=tag,
                execution_payload=payload,
                tool_call={"name": f"motion_{intent.action}", "arguments": intent.params},
            )

        # Screen Domain
        if intent.domain == ActionDomain.SCREEN.value:
            if intent.action == "eyes_mood":
                mood = intent.params.get("mood", "happy")
                tag = intent.action_tag or f"[{mood}]"
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.SCREEN.value,
                    action="eyes_mood",
                    target=f"تعبير {mood}",
                    params=intent.params,
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech=f"غيرت تعبير عيني إلى {mood}.",
                    llm_directive=f"المستخدم يطلب تغيير تعبيرات عينيك إلى ({mood}). غير التعبير وضمن الوسم {tag}.",
                    action_tag=tag,
                    execution_payload={"t": "eyes", "mood": mood},
                    tool_call={"name": "screen_set_eyes_mood", "arguments": {"mood": mood}},
                )
            elif intent.action == "gaze":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.SCREEN.value,
                    action="gaze",
                    target=intent.target,
                    params=intent.params,
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="وجهت نظري.",
                    llm_directive="المستخدم يطلب توجيه النظر على الشاشة. أكد التوجيه.",
                    execution_payload={"t": "gaze", **intent.params},
                    tool_call={"name": "screen_set_gaze", "arguments": intent.params},
                )
            elif intent.action == "show_person_photo":
                p_name = intent.target
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.SCREEN.value,
                    action="show_person_photo",
                    target=p_name,
                    params=intent.params,
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech=f"بعرض صورة {p_name} على الشاشة حالاً.",
                    llm_directive=f"المستخدم يطلب عرض صورة {p_name}. أكد له عرض الصورة على شاشة سطح المكتب.",
                    execution_payload={"t": "screen_action", "action": "show_person_photo", "name": p_name},
                    tool_call={"name": "screen_show_person_photo", "arguments": {"person_name": p_name}},
                )
            elif intent.action == "desktop_screen_control":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.SCREEN.value,
                    action="desktop_screen_control",
                    target="التحكم بالشاشة",
                    params=intent.params,
                    required_level=2,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="فتحت لوحة التحكم بالشاشة.",
                    llm_directive="المستخدم يطلب التحكم بالشاشة وسطح المكتب. أكد له تجهيز لوحة التحكم.",
                    execution_payload={"t": "desktop_screen_control", "cmd": "open"},
                    tool_call={"name": "desktop_screen_control", "arguments": {}},
                )

        # Vision Domain
        if intent.domain == ActionDomain.VISION.value:
            if intent.action == "capture_photo":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.VISION.value,
                    action="capture_photo",
                    target="التقاط صورة",
                    params={},
                    required_level=2,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="ابتسم، باخدلك لقطة حالاً! [happy]",
                    llm_directive="المستخدم يطلب التقاط صورة بالكاميرا. أكد له أخذ الصورة وضمن [happy].",
                    action_tag="[happy]",
                    execution_payload={"t": "camera_capture"},
                    tool_call={"name": "vision_capture_photo", "arguments": {}},
                )
            elif intent.action == "identify_person":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.VISION.value,
                    action="identify_person",
                    target="التعرف على الشخص",
                    params={},
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="بتعرف على الشخص اللي قدام الكاميرا حالاً.",
                    llm_directive="المستخدم يسأل عن الشخص المقابل للكاميرا. اذكر هويته من بيانات الـ Vision المرفقة بدقة.",
                    tool_call={"name": "vision_identify_person", "arguments": {}},
                )
            elif intent.action == "track_face":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.VISION.value,
                    action="track_face",
                    target=intent.target,
                    params=intent.params,
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech=f"بدأت أتبع وجه {intent.target}.",
                    llm_directive=f"المستخدم يطلب تتبع وجه {intent.target}. أكد له بدء التتبع.",
                    execution_payload={"t": "track_face", "name": intent.target},
                    tool_call={"name": "vision_track_face", "arguments": {"name": intent.target}},
                )

        # Device Domain
        if intent.domain == ActionDomain.DEVICE.value:
            if intent.action == "light_toggle":
                state = intent.params.get("state", True)
                state_str = "تشغيل" if state else "إطفاء"
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.DEVICE.value,
                    action="light_toggle",
                    target=f"{state_str} الإضاءة",
                    params=intent.params,
                    required_level=2,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech=f"تمام، تم {state_str} النور.",
                    llm_directive=f"المستخدم يطلب {state_str} النور/الإضاءة. أكد له التنفيذ فوراً.",
                    execution_payload={"t": "relay", "pin": 1, "state": state},
                    tool_call={"name": "device_light_toggle", "arguments": {"state": state}},
                )
            elif intent.action == "check_battery":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.DEVICE.value,
                    action="check_battery",
                    target="فحص البطارية",
                    params={},
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="بفحص نسبة شحن البطارية حالاً.",
                    llm_directive="المستخدم يسأل عن حالة وشحن البطارية. اعرض نسبة الشحن والجهد بدقة.",
                    execution_payload={"t": "telemetry_request"},
                    tool_call={"name": "device_check_battery", "arguments": {}},
                )
            elif intent.action == "check_distance":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.DEVICE.value,
                    action="check_distance",
                    target="قياس المسافة",
                    params={},
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="بقيس المسافة للأجسام اللي قدامي.",
                    llm_directive="المستخدم يسأل عن المسافة أمام الروبوت. اعرض قراءة الحساس بالسنتيمتر بدقة.",
                    execution_payload={"t": "distance_request"},
                    tool_call={"name": "device_check_distance", "arguments": {}},
                )

        # Reminders Domain
        if intent.domain == ActionDomain.REMINDER.value:
            title = intent.target or "تذكير"
            if intent.action == "create_reminder":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.REMINDER.value,
                    action="create_reminder",
                    target=title,
                    params=intent.params,
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech=f"تمام، فكرتك بـ {title} في ميعادها [happy].",
                    llm_directive=f"المستخدم يطلب تذكيراً: '{title}'. أكد له حفظ التذكير مع تضمين [happy].",
                    action_tag="[happy]",
                    execution_payload={"t": "reminder_create", "title": title},
                    tool_call={"name": "reminder_create", "arguments": {"title": title}},
                )
            elif intent.action == "list_reminders":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.REMINDER.value,
                    action="list_reminders",
                    target="عرض التذكيرات",
                    params={},
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="دي كل التذكيرات اللي متسجلة.",
                    llm_directive="المستخدم يسأل عن التذكيرات النشطة. استعرض التذكيرات المسجلة بدقة ووضوح.",
                    tool_call={"name": "reminder_list", "arguments": {}},
                )
            elif intent.action == "acknowledge_reminder":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.REMINDER.value,
                    action="acknowledge_reminder",
                    target="تأكيد التذكير",
                    params={},
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="ألف سلامة، سجلت إنك أخدت الدوا ونفذت التذكير [like].",
                    llm_directive="المستخدم يؤكد تنفيذ التذكير (مثل أخذ الدواء). أكد له التسجيل بنجاح مع تمنيات العافية وتضمين [like].",
                    action_tag="[like]",
                    execution_payload={"t": "reminder_ack"},
                    tool_call={"name": "reminder_acknowledge", "arguments": {}},
                )

        # Media Domain
        if intent.domain == ActionDomain.MEDIA.value:
            if intent.action == "play_media":
                q = intent.params.get("query", "موسيقى")
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.MEDIA.value,
                    action="play_media",
                    target=q,
                    params=intent.params,
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech=f"شغلتلك {q} حالاً [happy].",
                    llm_directive=f"المستخدم يطلب تشغيل صوتيات ({q}). أكد له التشغيل مع تضمين [happy].",
                    action_tag="[happy]",
                    execution_payload={"t": "media", "cmd": "play", "query": q},
                    tool_call={"name": "media_play", "arguments": {"query": q}},
                )
            elif intent.action == "stop_media":
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.MEDIA.value,
                    action="stop_media",
                    target="إيقاف الصوت",
                    params={},
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="وقفت الصوت.",
                    llm_directive="المستخدم يطلب إيقاف الصوتيات. أكد له الإيقاف الفوري.",
                    execution_payload={"t": "media", "cmd": "stop"},
                    tool_call={"name": "media_stop", "arguments": {}},
                )
            elif intent.action == "volume_control":
                cmd = intent.params.get("cmd", "up")
                return UniversalActionParseResponse(
                    has_action=True,
                    domain=ActionDomain.MEDIA.value,
                    action="volume_control",
                    target=f"تعديل الصوت ({cmd})",
                    params=intent.params,
                    required_level=1,
                    is_verified=is_verified,
                    is_authorized=True,
                    decision="ready",
                    suggested_speech="عدلت مستوى الصوت.",
                    llm_directive=f"المستخدم يطلب تعديل مستوى الصوت ({cmd}). أكد له التعديل.",
                    execution_payload={"t": "media", "cmd": f"volume_{cmd}"},
                    tool_call={"name": "media_volume", "arguments": {"command": cmd}},
                )

        # Sensitive Domain (Level 3)
        if intent.domain == ActionDomain.SENSITIVE.value:
            return UniversalActionParseResponse(
                has_action=True,
                domain=ActionDomain.SENSITIVE.value,
                action=intent.action,
                target=intent.target,
                params=intent.params,
                required_level=3,
                is_verified=is_verified,
                is_authorized=is_verified and (is_main or verification_level >= 3),
                decision="ready" if (is_verified and (is_main or verification_level >= 3)) else "needs_confirm",
                suggested_speech="الطلب ده بالغ الحساسية ويتطلب تأكيداً من غرفة التحكم.",
                llm_directive=(
                    f"طلب المستخدم عملية حساسة للغاية من المستوى 3 ({intent.target}). "
                    "يجب طلب تأكيد صريح ومباشر من غرفة التحكم المشرفة قبل أي إجراء."
                ),
                execution_payload={"t": "sensitive_request", "action": intent.action},
                tool_call={"name": f"sensitive_{intent.action}", "arguments": intent.params},
            )

        # Default deterministic response (should not occur, but preserved for completeness)
        return UniversalActionParseResponse(
            has_action=False,
            decision="none",
            is_verified=is_verified,
            is_authorized=False,
        )


# Singleton instance
_universal_planner = UniversalActionPlanner()


def get_universal_action_planner() -> UniversalActionPlanner:
    return _universal_planner
