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

    # 2. Faces (Vision / Face Recognition)
    registered_faces: List[str] = []
    try:
        faces_res = await db.execute(select(FaceProfile.name))
        registered_faces = list(faces_res.scalars().all())
    except Exception as e:
        logger.warning(f"Could not load registered face profiles from DB: {e}")

    current_person_desc = "لا يوجد أحد أمام الكاميرا حالياً"
    face_detected = False
    is_recent = False
    detected_face_name: Optional[str] = None
    current_face: Dict[str, Any] = {}
    try:
        from app.websocket.handlers import get_face_service
        face_service = get_face_service()
        if not registered_faces and getattr(face_service, "_known_embeddings", None):
            registered_faces = list(face_service._known_embeddings.keys())
        current_face = face_service.get_current_face_info()
        face_detected = current_face.get("detected", False)
        is_recent = current_face.get("is_recent", False)
        if face_detected and current_face.get("face_id"):
            detected_face_name = current_face["face_id"]
            current_person_desc = f"الشخص الذي تراه أمامك هو: {detected_face_name}"
        elif face_detected:
            current_person_desc = "يوجد شخص أمام الكاميرا ولكن لم يتم التعرف على هويته"
    except Exception as e:
        logger.warning(f"Could not retrieve live face info: {e}")

    faces_info = {
        "currently_detected": face_detected,
        "is_recent": is_recent,
        "current_person": current_person_desc,
        "registered_profiles": registered_faces,
    }

    # 3. Memories (RAG grounded in Face Recognition & Persona)
    rag_person = detected_face_name
    if not rag_person and target_p and "مازن" in (target_p.name or ""):
        rag_person = "مازن"

    memories = await _rag_service.retrieve(
        message,
        personality_id=target_p.id,
        db=db,
        person_name=rag_person,
    )

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

    # 6. Allowlisted Contacts & Reminders (Privacy: names only, zero numbers per §14.9)
    trusted_contacts: List[str] = []
    active_reminders_list: List[str] = []
    try:
        from app.models.contact import Contact
        from app.models.reminder import Reminder
        c_res = await db.execute(select(Contact.name).where(Contact.is_allowlisted == True).limit(20))
        trusted_contacts = list(c_res.scalars().all())
        r_res = await db.execute(select(Reminder.title).where(Reminder.is_active == True, Reminder.status == "pending").limit(5))
        active_reminders_list = list(r_res.scalars().all())
    except Exception as e:
        logger.debug(f"Contacts/reminders grounding notice: {e}")

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
        grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.

قواعد التشغيل والتوجيه الشامل (Comprehensive Operational Directives):
1. تطابق لغة الحوار واللهجة (Strict Language Mirroring & Cairo Dialect):
   - المستخدم يتحدث باللغة العربية: يجب أن تجيب حصراً بلهجة مصرية قاهرية مهذبة وطبيعية ومفهومة.
   - يُحظر تماماً خلط لغات أجنبية أو استخدام رموز صينية أو مصطلحات مشوهة.
2. الالتزام الصارم بسياق الذاكرة المعتمد ومنع الهلوسة (Strict RAG Grounding & Zero-Hallucination):
   - اعتمد بشكل حصري ودقيق على الحقائق والمعلومات الواردة في سياق الذاكرة (RAG Context) فقط.
   - إذا سُئلت عن تفصيلة غير متوفرة في الذاكرة، أو كانت الذاكرة فارغة، يجب أن تعتذر بأدب وبشكل مباشر:
     "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
   - لا تخمن أو تخترع أو تفترض أي بيانات غير مذكورة قطعياً.
3. بروتوكول حماية الخصوصية والبيانات الحساسة (Privacy & Security Directives):
   - إذا طُلب منك رقم هاتف شخصي، كلمة مرور، كود سري، أو بيانات مالية وبنكية خاصة: ارفض فوراً بعبارة:
     "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
4. الوعي البيئي والعتادي (Vision & Hardware Grounding):
   - التفاعل بذكاء مع حالة الأجهزة المتصلة ومع الشخص الحاضر أمام الكاميرا.
5. الإيجاز الحتمي ووسوم المشاعر (Conciseness & Mandatory Emotion Tags):
   - أجب دائماً باختصار في حدود جملة إلى جملتين كحد أقصى لتوفير سرعة استجابة عالية.
   - اختم إجابتك دائماً وبشكل إلزامي بوسم مشاعر واحد فقط في نهاية النص: [happy] أو [wave] أو [like] أو [neutral] أو [sad] أو [surprised].

معلومات النظام والسياق النشط:
- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect') or 'cairo'})
- بصمة الصوت: {voice_str}
- التشخيص وحالة الأجهزة: الهاتف ({phone_str}) | الحاسوب ({desk_str}) | شريحة الروبوت ({esp_str})
"""
        if face_detected and current_face.get("face_id"):
            grounded_system_prompt += f"- الكاميرا: الشخص أمامك هو {current_face['face_id']}.\n"
        if trusted_contacts:
            grounded_system_prompt += f"- جهات الاتصال المسموحة (أسماء فقط): {', '.join(trusted_contacts)}.\n"
        if active_reminders_list:
            grounded_system_prompt += f"- التذكيرات الحالية: {', '.join(active_reminders_list)}.\n"

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
