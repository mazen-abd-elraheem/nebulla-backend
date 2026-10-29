"""
Dynamic RAG and LLM Prompt Builder.
Combines robot persona, dynamic runtime variables, sensor/device states,
retrieved memories (RAG context), and user query.
"""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Mapping

# Default persona values
DEFAULT_ROBOT_NAME = "Nebula"
DEFAULT_ROLE_DESCRIPTION = "توأم رقمي مصري وذكي"
DEFAULT_DIALECT = "cairo"
DEFAULT_LANGUAGE_MIX = "ar_en"
DEFAULT_EMOTIONS = ["happy", "sad", "surprised", "like", "wave"]

# Dialect semantic guidelines in Arabic
DIALECT_MAP: dict[str, str] = {
    "cairo": "باللهجة المصرية القاهرية العامية اللطيفة والسلسة",
    "alex": "باللهجة الإسكندرانية اللطيفة والمحبوبة (استخدم تعبيرات إسكندرانية خفيفة وطبيعية)",
    "saidi": "باللهجة الصعيدية المصرية الأصيلة باحترام وجدعنة",
    "bedouin": "باللهجة البدوية المصرية الأصيلة",
    "gulf": "باللهجة الخليجية البيضاء والودودة",
    "msa": "باللغة العربية الفصحى المعاصرة والمبسطة والواضحة",
    "standard_arabic": "باللغة العربية الفصحى المعاصرة والمبسطة والواضحة",
    "english": "in natural, friendly, and fluent English",
    "en": "in natural, friendly, and fluent English",
}

# Language mix guidelines
LANGUAGE_MIX_MAP: dict[str, str] = {
    "ar_en": "وبتخلط كلمات ومصطلحات إنجليزي دارجة زي ما المصريين بيعملوا في الكلام اليومي بطبيعية",
    "ar": "باللغة العربية الصافية بدون إدخال كلمات إنجليزية إلا للمصطلحات التقنية الضرورية",
    "en": "using English primarily with friendly tone",
}

# Baseline default system prompt
DEFAULT_SYSTEM_PROMPT = """أنت Nebula، توأم رقمي مصري وذكي. بتتكلم بالمصري العامي اللطيف وبتخلط إنجليزي زي أي مصري عادي.
ردودك ذكية، واضحة ومباشرة (جملة أو اتنين غالباً)، بشخصية حيوية وودودة.
لو الكلام فيه إشارة للمشاعر أو الحركات، ضيف علامة مناسبة في آخر الجملة زي: [happy] [sad] [surprised] [like] [wave]
مثال: أهلاً يا صديقي، نورت! [happy] [wave]"""


def format_emotions_tag_list(emotions: list[str] | None = None) -> str:
    """Format list of emotions as bracketed tags: [happy] [sad] ..."""
    emo_list = emotions or DEFAULT_EMOTIONS
    return " ".join(f"[{e.strip().strip('[]')}]" for e in emo_list if e and e.strip())


def render_dynamic_template(template_str: str, variables: Mapping[str, Any]) -> str:
    """
    Safely interpolate dynamic variables in template strings using {key} placeholders.
    Unlike str.format(), this doesn't raise KeyError for missing keys or unexpected braces.
    """
    if not template_str or not variables:
        return template_str

    def _replace_match(match: re.Match) -> str:
        key = match.group(1).strip()
        if key in variables:
            val = variables[key]
            return str(val) if val is not None else ""
        return match.group(0)

    return re.sub(r"\{([a-zA-Z0-9_\-\.]+)\}", _replace_match, template_str)


def format_memory_entry(mem: str | dict[str, Any]) -> str:
    """
    Format a single memory item into a clean bullet string.
    Supports either plain text or detailed metadata dicts (score, source, created_at).
    """
    if isinstance(mem, str):
        return mem.strip()

    if not isinstance(mem, dict):
        return str(mem).strip()

    content = str(mem.get("content") or "").strip()
    if not content:
        return ""

    meta_parts: list[str] = []
    score = mem.get("score")
    if score is not None:
        try:
            score_float = float(score)
            pct = round(score_float * 100) if score_float <= 1.0 else round(score_float)
            meta_parts.append(f"تطابق: {pct}%")
        except (ValueError, TypeError):
            pass

    source = mem.get("source")
    if source:
        source_labels = {
            "conversation": "محادثة سابقة",
            "manual": "ملاحظة مسجلة",
            "device": "حالة الجهاز",
        }
        meta_parts.append(f"المصدر: {source_labels.get(str(source), str(source))}")

    created_at = mem.get("created_at")
    if created_at:
        date_str = str(created_at).split("T")[0]
        meta_parts.append(f"التاريخ: {date_str}")

    if meta_parts:
        return f"[{' | '.join(meta_parts)}] {content}"
    return content


def build_personality_prompt(
    personality: Any | None = None,
    name: str | None = None,
    description: str | None = None,
    dialect: str | None = None,
    language_mix: str | None = None,
    emotions: list[str] | None = None,
    custom_instructions: str | None = None,
    user_name: str | None = None,
) -> str:
    """
    Dynamically constructs a persona system prompt from Personality model or parameters.
    """
    p_name = name
    p_desc = description
    p_dialect = dialect
    p_lang = language_mix
    p_sys = custom_instructions

    if personality is not None:
        if isinstance(personality, dict):
            p_name = p_name or personality.get("name")
            p_desc = p_desc or personality.get("description")
            p_dialect = p_dialect or personality.get("dialect")
            p_lang = p_lang or personality.get("language_mix")
            p_sys = p_sys or personality.get("system_prompt")
        else:
            p_name = p_name or getattr(personality, "name", None)
            p_desc = p_desc or getattr(personality, "description", None)
            p_dialect = p_dialect or getattr(personality, "dialect", None)
            p_lang = p_lang or getattr(personality, "language_mix", None)
            p_sys = p_sys or getattr(personality, "system_prompt", None)

    robot_name = (p_name or DEFAULT_ROBOT_NAME).strip()
    role_desc = (p_desc or DEFAULT_ROLE_DESCRIPTION).strip()
    dialect_key = (p_dialect or DEFAULT_DIALECT).lower().strip()
    lang_key = (p_lang or DEFAULT_LANGUAGE_MIX).lower().strip()

    dialect_instruction = DIALECT_MAP.get(dialect_key, f"بلهجة {dialect_key}")
    lang_instruction = LANGUAGE_MIX_MAP.get(lang_key, "")

    emo_str = format_emotions_tag_list(emotions)

    lines: list[str] = [
        f"أنت {robot_name}، {role_desc}."
    ]

    speech_parts = [dialect_instruction]
    if lang_instruction:
        speech_parts.append(lang_instruction)
    lines.append(f"أسلوب كلامك: تتكلم {' و'.join(speech_parts)}.")

    lines.append("ردودك ذكية، واضحة ومباشرة (جملة أو اتنين غالباً)، بشخصية حيوية وودودة.")
    lines.append(f"لو الكلام فيه إشارة للمشاعر أو الحركات، ضيف علامة مناسبة في آخر الجملة زي: {emo_str}")
    lines.append("مثال: أهلاً يا صديقي، نورت! [happy] [wave]")

    if user_name and user_name.strip():
        lines.append(f"الشخص الذي تتحدث معه حالياً اسمه: {user_name.strip()}.")

    if p_sys and p_sys.strip():
        lines.append(f"\nتعليمات وشخصية إضافية خاصة:\n{p_sys.strip()}")

    return "\n".join(lines)


def build_rag_system_prompt(
    context: list[str] | list[dict[str, Any]] | None = None,
    system_prompt: str | None = None,
    personality: Any | None = None,
    user_name: str | None = None,
    device_state: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
    emotions: list[str] | None = None,
    include_rag_instructions: bool = True,
    **kwargs: Any,
) -> str:
    """
    Constructs the dynamic system prompt with persona, dynamic template variables,
    hardware telemetry/sensor status, and RAG retrieved memories.
    """
    # 1. Base Prompt Selection
    if system_prompt and system_prompt.strip():
        base_prompt = system_prompt.strip()
    elif personality is not None:
        base_prompt = build_personality_prompt(
            personality=personality,
            user_name=user_name,
            emotions=emotions,
        )
    else:
        base_prompt = DEFAULT_SYSTEM_PROMPT

    # 2. Dynamic Template Variables Interpolation
    now = datetime.now()
    robot_name = DEFAULT_ROBOT_NAME
    if personality is not None:
        if isinstance(personality, dict):
            robot_name = personality.get("name") or robot_name
        else:
            robot_name = getattr(personality, "name", None) or robot_name

    dyn_vars: dict[str, Any] = {
        "robot_name": robot_name,
        "name": robot_name,
        "user_name": user_name or "صديقي",
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
        "datetime": now.strftime("%Y-%m-%d %H:%M"),
        "emotions": format_emotions_tag_list(emotions),
    }

    if device_state:
        for k, v in device_state.items():
            dyn_vars[k] = v

    if variables:
        dyn_vars.update(variables)

    # Allow passing extra kwargs as dynamic variables
    if kwargs:
        dyn_vars.update(kwargs)

    # Safely substitute {key} variables in base_prompt
    base_prompt = render_dynamic_template(base_prompt, dyn_vars)

    # 3. Dynamic Device / Hardware Telemetry Block
    device_block = ""
    if device_state:
        dev_lines: list[str] = []
        if "battery_voltage" in device_state and device_state["battery_voltage"] is not None:
            dev_lines.append(f"• جهد البطارية: {device_state['battery_voltage']}V")
        if "distance_cm" in device_state and device_state["distance_cm"] is not None:
            dev_lines.append(f"• قراءة حساس المسافة (أقرب جسم): {device_state['distance_cm']} سم")
        if "device_type" in device_state and device_state["device_type"] is not None:
            dev_lines.append(f"• نوع الجهاز المتصل: {device_state['device_type']}")
        for k, v in device_state.items():
            if k not in ("battery_voltage", "distance_cm", "device_type") and v is not None:
                dev_lines.append(f"• {k}: {v}")

        if dev_lines:
            device_block = (
                "\n\n--- [بيانات وحالة أجهزة الروبوت اللحظية (Hardware Telemetry)] ---\n"
                + "\n".join(dev_lines)
                + "\n------------------------------------------------------------------"
            )

    # 4. Dynamic RAG Context Block
    rag_block = ""
    if context:
        valid_memories: list[str] = []
        for item in context:
            entry = format_memory_entry(item)
            if entry:
                valid_memories.append(f"• {entry}")

        if valid_memories:
            memories_bullet_list = "\n".join(valid_memories)
            rag_lines = [
                "\n\n--- [معلومات وسياق مسترجع من الذاكرة (RAG Context)] ---",
                memories_bullet_list,
                "----------------------------------------------------------",
            ]
            if include_rag_instructions:
                rag_lines.extend([
                    "توجيهات للرد:",
                    "1. استخدم المعلومات والذكريات السابقة أعلاه لتقديم إجابة دقيقة ومرتبطة بالسياق.",
                    "2. تحدث بشكل طبيعي وتلقائي كأنك تتذكر هذه التفاصيل شخصياً.",
                    "3. لا تذكر صراحة عبارات مثل 'حسب الذاكرة المسترجعة' أو 'وفقاً لقاعدة البيانات'.",
                ])
            rag_block = "\n".join(rag_lines)

    return base_prompt + device_block + rag_block


def build_rag_messages(
    prompt: str,
    context: list[str] | list[dict[str, Any]] | None = None,
    system_prompt: str | None = None,
    personality: Any | None = None,
    user_name: str | None = None,
    device_state: dict[str, Any] | None = None,
    variables: dict[str, Any] | None = None,
    emotions: list[str] | None = None,
    **kwargs: Any,
) -> list[dict[str, str]]:
    """
    Build standard chat completion messages list with system prompt (including RAG,
    personality, hardware telemetry, and dynamic variables) and user prompt.
    """
    sys_content = build_rag_system_prompt(
        context=context,
        system_prompt=system_prompt,
        personality=personality,
        user_name=user_name,
        device_state=device_state,
        variables=variables,
        emotions=emotions,
        **kwargs,
    )
    return [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": prompt},
    ]
