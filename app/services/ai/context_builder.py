"""
Context Builder — unifies grounding across Personality, Memories (RAG),
Vision (UniFace / detected person), Voice Clone, and Hardware Diagnostics.
"""

from typing import Optional, List, Dict, Any, Tuple
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.personality import Personality
from app.models.face_profile import FaceProfile
from app.services.memory.rag_service import RAGService
from app.websocket.manager import manager

logger = get_logger(__name__)
_rag_service = RAGService()


class GroundingInfo(BaseModel):
    personality: Dict[str, Any]
    faces: Dict[str, Any]
    voice_clone: Dict[str, Any]
    diagnostics: Dict[str, Any]
    memories: List[str]


async def build_grounding_context(
    db: AsyncSession,
    personality_id: Optional[int],
    message: str,
) -> Tuple[str, List[str], GroundingInfo, int]:
    """
    Build unified grounding context across:
    1. Personalities
    2. Memories (RAG)
    3. Faces (Vision)
    4. Voice Clone (XTTS / sample)
    5. Diagnostics (Connected hardware channels)
    """
    # 1. Personality
    target_p = None
    if personality_id:
        target_p = await db.get(Personality, personality_id)
    if not target_p:
        res = await db.execute(select(Personality).where(Personality.is_active == True).limit(1))  # noqa: E712
        target_p = res.scalar_one_or_none()
    if not target_p:
        first_p = (await db.execute(select(Personality).limit(1))).scalar_one_or_none()
        if first_p:
            target_p = first_p
        else:
            target_p = Personality(
                name="توت (Default)",
                system_prompt="أنت توأم رقمي مصري ذكي وودود.",
                dialect="cairo",
                language_mix="ar_en",
                is_active=True,
            )
            db.add(target_p)
            await db.flush()

    p_info = {
        "id": target_p.id,
        "name": target_p.name,
        "dialect": target_p.dialect or "cairo",
        "language_mix": target_p.language_mix or "ar_en",
        "description": target_p.description or "",
        "system_prompt": target_p.system_prompt or "",
    }

    import asyncio

    # 2. Concurrent Retrieval: Memories (RAG) + Face Profiles
    async def _fetch_faces():
        try:
            res = await db.execute(select(FaceProfile.name))
            return list(res.scalars().all())
        except Exception as e:
            logger.warning(f"Could not load registered face profiles: {e}")
            return []

    memories_coro = _rag_service.retrieve(message, personality_id=target_p.id, db=db)
    faces_coro = _fetch_faces()
    memories, registered_faces = await asyncio.gather(memories_coro, faces_coro)

    # 3. Faces (Vision / Face Recognition)
    current_person_desc = "لا يوجد أحد أمام الكاميرا حالياً"
    face_detected = False
    is_recent = False
    current_face = {}
    try:
        from app.websocket.handlers import get_face_service
        face_service = get_face_service()
        current_face = face_service.get_current_face_info()
        face_detected = current_face.get("detected", False)
        is_recent = current_face.get("is_recent", False)
        if face_detected:
            if current_face.get("face_id"):
                current_person_desc = f"الشخص الذي تراه أمامك هو: {current_face['face_id']}"
            else:
                current_person_desc = "يوجد شخص أمام الكاميرا ولكن لم يتم التعرف على هويته"
    except Exception as e:
        logger.warning(f"Could not retrieve live face info: {e}")

    faces_info = {
        "currently_detected": face_detected,
        "is_recent": is_recent,
        "current_person": current_person_desc,
        "registered_profiles": registered_faces,
    }

    # 4. Voice Clone
    voice_info = {
        "tts_provider": settings.TTS_PROVIDER,
        "voice_sample_path": target_p.voice_sample_path or "غير محدد (يستخدم الصوت الافتراضي)",
        "has_sample": bool(target_p.voice_sample_path),
    }

    # 5. Diagnostics
    diag_status = manager.status()
    diag_info = {
        "phone_connected": bool(diag_status.get("phone", False)),
        "desktop_connected": bool(diag_status.get("desktops", 0) > 0 or diag_status.get("desktop", False)),
        "esp_connected": bool(diag_status.get("esp32", False) or diag_status.get("esp", False)),
        "backend_status": "ok",
    }

    # Formulate system prompt
    phone_str = "متصل" if diag_info["phone_connected"] else "غير متصل"
    desk_str = "متصل" if diag_info["desktop_connected"] else "غير متصل"
    esp_str = "متصل" if diag_info["esp_connected"] else "غير متصل"

    creator_name = registered_faces[0] if registered_faces else "مازن عبد الرحيم"
    robot_name = p_info.get("name") or "نيبولا"
    robot_desc = p_info.get("description") or "روبوت ذكاء اصطناعي وتوأم رقمي ذكي"

    import re
    is_arabic = bool(re.search(r"[\u0600-\u06FF]", message))

    voice_str = voice_info["voice_sample_path"]

    if is_arabic:
        grounded_system_prompt = (
            f"أنت \"{robot_name}\" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.\n"
            "تعليمات التشغيل:\n"
            "1. اللهجة: أجب بلهجة مصرية قاهرية مهذبة وطبيعية.\n"
            "2. الذاكرة ومنع الهلوسة: اعتمد حصرياً على الذاكرة أدناه. إذا لم تجد الإجابة، أو طُلب رقم سري/بيانات خاصة، اعتذر فوراً بعبارة:\n"
            "   \"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]\"\n"
            "3. الإيجاز: أجب باختصار في جملة أو جملتين فقط.\n"
            "4. المشاعر: اختم دائماً بوسم مشاعر واحد فقط في النهاية (مثل [happy] أو [wave]).\n"
            f"- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect', 'cairo')})\n"
            f"- استنساخ الصوت: {voice_str}\n"
            f"- التشخيص وحالة الأجهزة: هاتف ({phone_str}) | حاسوب ({desk_str}) | روبوت ({esp_str})\n"
        )
        if face_detected and current_face.get("face_id"):
            grounded_system_prompt += f"- الكاميرا: الشخص أمامك هو {current_face['face_id']}.\n"

        if memories:
            mem_bullets = "\n".join(f"- {m}" for m in memories)
            grounded_system_prompt += (
                f"\nالذاكرة المعتمدة:\n{mem_bullets}\n"
                "تنبيه صارم لمنع الهلوسة: إذا طُلب رقم هاتف، كلمة مرور، أو تفصيلة غير مذكورة نصاً في الذاكرة أعلاه، يجب أن تجيب حصراً بـ:\n"
                "\"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]\"\n"
            )
        else:
            greeting_patterns_ar = [
                r"\b(صباح|مساء)\s+(الخير|النور|الفل|الورد|الياسمين)\b",
                r"\b(أهلاً|اهلا|ازيك|إزيك|عامل إيه|عامل ايه|سلام عليكم|السلام عليكم|مرحبا|مرحباً|هاي|أنا|انا|منور)\b",
                r"\b(شكراً|شكرا|تسلم|تسلمي|يعطيك العافية)\b",
            ]
            is_greeting = any(re.search(pat, message.lower()) for pat in greeting_patterns_ar)
            if is_greeting:
                grounded_system_prompt += (
                    f"\nالمستخدم يحييك: رحب به بلطف بلهجة مصرية وعرفه بنفسك كـ {robot_name}، واسأله كيف تساعده اليوم.\n"
                )
            else:
                grounded_system_prompt += (
                    "\nالذاكرة: لا توجد معلومات مسجلة لهذا السؤال.\n"
                    "تنبيه صارم: اعتذر فوراً بعبارة:\n\"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]\"\n"
                )
    else:
        # User is speaking English
        from scripts.generate_rag_dataset import to_english_memory
        grounded_system_prompt = (
            f"You are \"{robot_name}\", digital twin robot created by {creator_name}.\n"
            "Directives:\n"
            "1. Language: Answer strictly in clear, natural English.\n"
            "2. RAG & Zero-Hallucination: Answer exclusively using the verified memory below. If not present or sensitive, reply:\n"
            "   \"I do not have this information recorded in my memory. [wave]\"\n"
            "3. Conciseness: Answer in 1 to 2 sentences max.\n"
            "4. Emotion: Conclude with exactly one emotion tag (e.g. [happy], [wave], [like]).\n"
            f"- Devices: Phone ({phone_str}) | Desktop ({desk_str}) | Robot ({esp_str})\n"
        )
        if face_detected and current_face.get("face_id"):
            grounded_system_prompt += f"- Vision: Person in front of camera is {current_face['face_id']}.\n"

        if memories:
            mem_bullets = "\n".join(f"- {to_english_memory(m)}" for m in memories)
            grounded_system_prompt += (
                f"\nVerified Memory:\n{mem_bullets}\n"
                "STRICT DIRECTIVE: If the inquiry asks for unrecorded details, phone numbers, or passwords, you MUST reply with:\n"
                "\"I do not have this information recorded in my memory. [wave]\"\n"
            )
        else:
            greeting_patterns_en = [
                r"\b(hello|hi|hey|good morning|good afternoon|good evening|my name is|i am|nice to meet you)\b",
            ]
            is_greeting_en = any(re.search(pat, message.lower()) for pat in greeting_patterns_en)
            if is_greeting_en:
                grounded_system_prompt += f"\nGreeting: Greet warmly in English as {robot_name} and ask how you can help.\n"
            else:
                grounded_system_prompt += (
                    "\nVerified Memory: None found.\n"
                    "Strict Directive: Reply with:\n\"I do not have this information recorded in my memory. [wave]\"\n"
                )

    grounding_data = GroundingInfo(
        personality=p_info,
        faces=faces_info,
        voice_clone=voice_info,
        diagnostics=diag_info,
        memories=memories,
    )

    return grounded_system_prompt, memories, grounding_data, target_p.id
