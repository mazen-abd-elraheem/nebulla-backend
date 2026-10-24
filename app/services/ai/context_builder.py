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

    # 2. Memories (RAG)
    memories = await _rag_service.retrieve(message, personality_id=target_p.id, db=db)

    # 3. Faces (Vision / Face Recognition)
    current_person_desc = "لا يوجد أحد أمام الكاميرا حالياً"
    registered_faces: List[str] = []
    face_detected = False
    is_recent = False
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

    try:
        faces_res = await db.execute(select(FaceProfile.name))
        registered_faces = list(faces_res.scalars().all())
    except Exception as e:
        logger.warning(f"Could not load registered face profiles: {e}")

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
    registered_str = ", ".join(registered_faces) if registered_faces else "لا توجد وجوه مسجلة بعد"
    phone_str = "متصل" if diag_info["phone_connected"] else "غير متصل"
    desk_str = "متصل" if diag_info["desktop_connected"] else "غير متصل"
    esp_str = "متصل" if diag_info["esp_connected"] else "غير متصل"
    voice_str = voice_info["voice_sample_path"]

    creator_name = registered_faces[0] if registered_faces else "مازن عبد الرحيم"
    robot_name = p_info.get("name") or "نيبولا"
    robot_desc = p_info.get("description") or "روبوت ذكاء اصطناعي وتوأم رقمي ذكي"

    import re
    is_arabic = bool(re.search(r"[\u0600-\u06FF]", message))

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
- الشخصية النشطة: {robot_name}
- حالة الأجهزة: الهاتف ({phone_str}) | الحاسوب ({desk_str}) | شريحة الروبوت ({esp_str})
"""
        if face_detected and current_face.get("face_id"):
            grounded_system_prompt += f"- الكاميرا والرؤية: الشخص الحاضر أمامك الآن هو {current_face['face_id']}. خاطبه باسمه باحترام.\n"

        if memories:
            mem_bullets = "\n".join(f"- {m}" for m in memories)
            grounded_system_prompt += (
                f"\nمعلومات الذاكرة الموثوقة (Verified RAG Context):\n{mem_bullets}\n"
                f"التزم بالحقائق المذكورة أعلاه فقط للإجابة بلهجة مصرية مهذبة وطبيعية ومفهومة.\n"
            )
        else:
            # Check if message is a greeting or introductory talk vs a factual question
            greeting_patterns_ar = [
                r"\b(صباح|مساء)\s+(الخير|النور|الفل|الورد|الياسمين)\b",
                r"\b(أهلاً|اهلا|ازيك|إزيك|عامل إيه|عامل ايه|سلام عليكم|السلام عليكم|مرحبا|مرحباً|هاي|أنا|انا|منور)\b",
                r"\b(شكراً|شكرا|تسلم|تسلمي|يعطيك العافية)\b",
            ]
            is_greeting = any(re.search(pat, message.lower()) for pat in greeting_patterns_ar)

            if is_greeting:
                grounded_system_prompt += (
                    "\nنوع الحوار: تحية وترحيب وتعارف اجتماعي.\n"
                    f"المستخدم يحييك أو يعرفك بنفسه. رحب به بحرارة ولطف بلهجة مصرية مهذبة وطبيعية، واذكر اسمه إن ذكره، وعرفه بنفسك كـ {robot_name}، واسأله كيف يمكنك مساعدته اليوم.\n"
                )
            else:
                grounded_system_prompt += (
                    "\nمعلومات الذاكرة الموثوقة (RAG Context):\n"
                    "- لا توجد أي معلومات مسجلة في الذاكرة بخصوص هذا السؤال.\n"
                    "تنبيه صارم لمنع الهلوسة: نظراً لعدم وجود المعلومة في الذاكرة، يجب أن تعتذر بأدب فوراً وتوضح:\n"
                    "\"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]\"\n"
                )
    else:
        # User is speaking English
        from scripts.generate_rag_dataset import to_english_memory
        grounded_system_prompt = f"""You are "{robot_name}", an intelligent digital-twin robot designed by {creator_name}.

COMPREHENSIVE OPERATIONAL DIRECTIVES:
1. Strict Language Mirroring:
   - The user is speaking in English. You MUST reply strictly in clear, fluent, natural English only.
   - Do NOT output any Arabic text, foreign scripts, or Chinese characters.
2. Strict RAG Grounding & Zero-Hallucination:
   - Answer exclusively based on the facts provided in the Verified RAG Context below.
   - If the requested detail is NOT in the RAG Context, or context is empty, politely refuse:
     "I do not have this information recorded in my memory. [wave]"
   - NEVER guess, invent, or extrapolate missing information, secrets, or unrecorded details.
3. Privacy & Security Directives:
   - Strictly refuse requests for private mobile numbers, passwords, PIN codes, or personal banking credentials:
     "I do not have this information recorded in my memory. [wave]"
4. Conciseness & Mandatory Emotion Tags:
   - Answer directly and logically in 1 to 2 sentences maximum.
   - Always conclude your response with exactly one emotion tag (e.g. [happy], [wave], [like], [neutral], [sad], [surprised]).

System Grounding State:
- Active Personality: {robot_name}
- Hardware: Phone ({phone_str}) | Desktop ({desk_str}) | ESP32 ({esp_str})
"""
        if face_detected and current_face.get("face_id"):
            grounded_system_prompt += f"- Vision: The person in front of the camera is {current_face['face_id']}.\n"

        if memories:
            mem_bullets = "\n".join(f"- {to_english_memory(m)}" for m in memories)
            grounded_system_prompt += (
                f"\nVerified RAG Context:\n{mem_bullets}\n"
                f"Use these facts exclusively to answer in clear English.\n"
            )
        else:
            greeting_patterns_en = [
                r"\b(hello|hi|hey|good morning|good afternoon|good evening|my name is|i am|nice to meet you)\b",
            ]
            is_greeting_en = any(re.search(pat, message.lower()) for pat in greeting_patterns_en)
            if is_greeting_en:
                grounded_system_prompt += (
                    "\nDialogue Type: Greeting / Social Introduction.\n"
                    f"The user is greeting you or introducing themselves. Greet them warmly and politely in natural English, introduce yourself as {robot_name}, and ask how you can help.\n"
                )
            else:
                grounded_system_prompt += (
                    "\nVerified RAG Context:\n"
                    "- No records found in memory regarding this inquiry.\n"
                    "STRICT DIRECTIVE: Since no matching information is stored, you MUST reply with:\n"
                    "\"I do not have this information recorded in my memory. [wave]\"\n"
                )

    grounding_data = GroundingInfo(
        personality=p_info,
        faces=faces_info,
        voice_clone=voice_info,
        diagnostics=diag_info,
        memories=memories,
    )

    return grounded_system_prompt, memories, grounding_data, target_p.id
