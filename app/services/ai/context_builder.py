"""
Context Builder — Unifies grounding across Personality, Memories (RAG),
Vision (UniFace / Person Photo Retrieval), Voice Clone, and Desktop Screen Diagnostics.
"""

from typing import Optional, List, Dict, Any, Tuple
import re
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.personality import Personality
from app.models.face_profile import FaceProfile
from app.services.memory.rag_service import RAGService
from app.services.memory.person_retriever import PersonImageRetriever
from app.websocket.manager import manager

logger = get_logger(__name__)
_rag_service = RAGService()


class GroundingInfo(BaseModel):
    personality: Dict[str, Any]
    faces: Dict[str, Any]
    voice_clone: Dict[str, Any]
    diagnostics: Dict[str, Any]
    memories: List[str]


def is_greeting_or_persona_inquiry(message: str) -> bool:
    """Check if message is a greeting or an inquiry about the robot's identity/creator."""
    if not message:
        return False
    msg = message.strip().lower()

    # Common greetings (Arabic and English)
    greetings = [
        "صباح الخير", "مساء الخير", "صباح النور", "مساء النور", "صباح الورد", "مساء الورد",
        "أهلاً", "اهلا", "ازيك", "إزيك", "عامل إيه", "عامل ايه", "سلام عليكم", "السلام عليكم",
        "مرحبا", "مرحباً", "هاي", "hello", "hi", "hey", "good morning", "good evening",
        "شكراً", "شكرا", "تسلم", "تسلمي", "thanks", "thank you"
    ]
    if any(g in msg for g in greetings):
        return True

    # Persona identity inquiries (asking about the robot itself or its creator)
    persona_patterns = [
        r"\b(أنت|انت|انتي|أنتي)\s+(مين|إيه|ايه)\b",
        r"\b(مين|ايه|إيه)\s+(أنت|انت|انتي|أنتي|حضرتك)\b",
        r"\b(اسمك|إسمك)\s+(إيه|ايه|مين)\b",
        r"\bمين\s+(صممك|عملك|برمجك|صنعك|طورك)\b",
        r"\bبتعمل\s+(إيه|ايه)\b",
        r"\bتقدر\s+تعمل\s+(إيه|ايه)\b",
        r"\b(who are you|what is your name|who made you|who created you|what can you do)\b",
    ]
    return any(re.search(pat, msg) for pat in persona_patterns)


async def build_grounding_context(
    db: AsyncSession,
    personality_id: Optional[int],
    message: str,
    verified_speaker: Optional[str] = None,
) -> Tuple[str, List[str], GroundingInfo, int]:
    """
    Build unified grounding context across:
    1. Personalities
    2. Memories (RAG with In-Memory VectorStore)
    3. Faces & Person Photos (Vision / FaceProfile)
    4. Voice Clone (XTTS / sample) & Speaker Verification
    5. Screen & Hardware Diagnostics (Connected channels)
    """
    # 1. Determine Personality: Question Content / Intent FIRST, then requested ID, then active personality
    target_p = None
    all_personalities_res = await db.execute(select(Personality))
    all_personalities = list(all_personalities_res.scalars().all())

    msg_lower = (message or "").lower()

    matched_p = None
    if message:
        for p in all_personalities:
            p_name = (p.name or "").lower()
            core_names = [part.strip() for part in re.split(r"[\(\)\-\s]+", p_name) if len(part.strip()) >= 3]
            if any(cn in msg_lower for cn in core_names):
                matched_p = p
                break
            if ("منه" in p_name or "منّة" in p_name) and any(w in msg_lower for w in ("منه", "منة", "menna")):
                matched_p = p
                break
            if "مازن" in p_name and any(w in msg_lower for w in ("مازن", "mazen")):
                matched_p = p
                break

    if matched_p:
        target_p = matched_p
        logger.info(f"Dynamically routed personality to '{target_p.name}' (ID: {target_p.id}) based on question content.")
    elif personality_id:
        target_p = await db.get(Personality, personality_id)

    if not target_p:
        res = await db.execute(select(Personality).where(Personality.is_active == True).order_by(Personality.id.desc()).limit(1))  # noqa: E712
        target_p = res.scalar_one_or_none()

    if not target_p:
        if all_personalities:
            target_p = all_personalities[-1]
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

    # 2. Faces & Registered Person Profiles (Vision + Face Profiles)
    registered_faces: List[str] = []
    try:
        registered_faces = await PersonImageRetriever.get_all_registered_names(db=db)
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

    # Determine candidate person from: 1) Camera Face, 2) Verified Voice Speaker, 3) Mention in message
    candidate_from_query = PersonImageRetriever.extract_person_candidate(message, registered_faces)
    rag_person = detected_face_name or verified_speaker or candidate_from_query

    if not rag_person and target_p and target_p.name:
        p_name = target_p.name.strip()
        first_name = p_name.split()[0]
        if first_name in message or p_name in message:
            rag_person = first_name

    # Retrieve person visual profile & photo
    person_profile: Optional[Dict[str, Any]] = None
    if rag_person:
        person_profile = await PersonImageRetriever.get_person_profile(rag_person, db=db)

    is_asking_photo = PersonImageRetriever.is_photo_inquiry(message)

    faces_info = {
        "currently_detected": face_detected,
        "is_recent": is_recent,
        "current_person": current_person_desc,
        "registered_profiles": registered_faces,
        "active_person": rag_person,
        "person_profile": person_profile,
        "photo_url": person_profile.get("photo_url") if person_profile else None,
        "photo_path": person_profile.get("photo_path") if person_profile else None,
        "is_photo_inquiry": is_asking_photo,
    }

    # 3. Memories (RAG grounded in Question, Person & VectorStore)
    memories = await _rag_service.retrieve(
        message,
        personality_id=target_p.id,
        db=db,
        person_name=rag_person,
    )

    # 4. Voice Clone & Speaker Verification
    voice_info = {
        "tts_provider": settings.TTS_PROVIDER,
        "voice_sample_path": target_p.voice_sample_path or "غير محدد (يستخدم الصوت الافتراضي)",
        "has_sample": bool(target_p.voice_sample_path),
        "verified_speaker": verified_speaker,
    }

    # 5. Diagnostics & Screen Status
    diag_status = manager.status()
    diag_info = {
        "phone_connected": bool(diag_status.get("phone", False)),
        "desktop_connected": bool(diag_status.get("desktops", 0) > 0 or diag_status.get("desktop", False)),
        "esp_connected": bool(diag_status.get("esp32", False) or diag_status.get("esp", False)),
        "backend_status": "ok",
    }

    # 6. Allowlisted Contacts & Reminders (Privacy: names only, zero numbers)
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

    phone_str = "متصل" if diag_info["phone_connected"] else "غير متصل"
    desk_str = "متصل" if diag_info["desktop_connected"] else "غير متصل"
    esp_str = "متصل" if diag_info["esp_connected"] else "غير متصل"

    creator_name = None
    if target_p:
        p_name_check = (target_p.name or "").lower()
        if "منه" in p_name_check or "منّة" in p_name_check or "menna" in p_name_check:
            creator_name = "منه محمد"
        elif "مازن" in p_name_check or "mazen" in p_name_check:
            creator_name = "مازن عبد الرحيم"
        elif target_p.system_prompt:
            creator_match = re.search(r"صممه[^\w]*(.+?)(?:\.|\s+تجيب|\s+ويتحدث|$)", target_p.system_prompt)
            if creator_match:
                creator_name = creator_match.group(1).strip()

    if not creator_name:
        creator_name = registered_faces[0] if registered_faces else "منه محمد"

    robot_name = p_info.get("name") or "نيبولا"
    raw_desc = p_info.get("description") or ""
    robot_desc = raw_desc if raw_desc and raw_desc.strip() != "string" else "روبوت ذكاء اصطناعي وتوأم رقمي ذكي"

    custom_system_prompt = (target_p.system_prompt or "").strip()
    persona_extra = f"\nتوجيه الشخصية: {custom_system_prompt}\n" if custom_system_prompt else ""

    is_arabic = bool(re.search(r"[؀-ۿ]", message))
    voice_str = voice_info["voice_sample_path"]

    # Formulate System Prompt
    if is_arabic:
        if memories:
            mem_bullets = "\n".join(f"- {m}" for m in memories)
            grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.
{persona_extra}

المهمة: استخرج الإجابة حصراً وبدقة متناهية من نص الذاكرة المعتمدة أدناه.
القواعد:
1. أجب بجملة واحدة مباشرة بالعامية المصرية القاهرية بدون أي تأليف أو تفاصيل إضافية غير مذكورة.
2. اختم إجابتك دائماً بوسم مشاعر واحد فقط في النهاية: [happy] أو [wave] أو [like].

أمثلة توضيحية لأسلوب الإجابة المباشر:
الذاكرة المعتمدة:
- أحمد مهندس برمجيات في حلوان.
سؤال: أحمد شغال إيه؟
إجابة: أحمد شغال مهندس برمجيات في حلوان. [like]

الذاكرة المعتمدة:
- سارة تحب القراءة وممارسة الرياضة.
سؤال: سارة بتحب إيه؟
إجابة: سارة بتحب القراءة وممارسة الرياضة. [happy]

الذاكرة المعتمدة:
{mem_bullets}

تنبيه صارم: أجب مباشرة فقط عن المطلوب باستخدام الذاكرة أعلاه، وبدون أي حشو أو كلام إضافي.
"""
        else:
            if is_greeting_or_persona_inquiry(message):
                grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.
{persona_extra}
المستخدم يحييك أو يسأل عنك: رحب به بلطف بلهجة مصرية وعرفه بنفسك كـ {robot_name} وصانعك {creator_name}، واسأله كيف تساعده اليوم. اختم إجابتك بوسم مشاعر مثل [happy] أو [wave].
"""
            else:
                grounded_system_prompt = f"""أنت "{robot_name}" (Nebula).
الذاكرة: لا توجد معلومات مسجلة لهذا السؤال.
تنبيه صارم: اعتذر فوراً بعبارة:
"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
قواعد التشغيل والتوجيه الصوتي والشاشي (Voice & Screen Operational Directives):
1. تطابق لغة الحوار واللهجة (Strict Language Mirroring & Cairo Dialect):
   - أجب حصراً بلهجة مصرية قاهرية مهذبة وطبيعية ومباشرة (جملة أو جملتين كحد أقصى) لتناسب النطق الصوتي (TTS).
   - يُمنع استخدام أي جداول، علامات نجمية، أو روابط إنترنت في نص الرد، لتفادي تشويه الصوت.
2. الالتزام الصارم بسياق الذاكرة المعتمد ومنع الهلوسة (Strict RAG Grounding & Zero-Hallucination):
   - اعتمد بشكل حصري ودقيق على الحقائق والمعلومات الواردة في سياق الذاكرة فقط.
   - إذا سُئلت عن تفصيلة غير متوفرة في الذاكرة، أو كانت الذاكرة فارغة، يجب أن تعتذر بأدب:
     "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
   - لا تخمن أو تخترع أو تفترض أي بيانات غير مذكورة قطعياً.
3. بروتوكول حماية الخصوصية والبيانات الحساسة (Privacy & Security Directives):
   - إذا طُلب منك رقم هاتف شخصي، كلمة مرور، كود سري، أو بيانات مالية وبنكية: ارفض فوراً بعبارة:
     "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
4. الوعي البيئي والعتادي وشاشة العرض (Vision, Screen & Hardware Grounding):
   - التفاعل بذكاء مع حالة الأجهزة المتصلة ومع الشخص الحاضر أمام الكاميرا.
   - إذا سأل المستخدم عن صورة شخص مسجل أو شكله، أكد له أن صورته مسجلة ومعروضة على الشاشة.
5. الإيجاز الحتمي ووسوم المشاعر (Mandatory Emotion Tags):
   - اختم إجابتك دائماً وبشكل إلزامي بوسم مشاعر واحد فقط في نهاية النص: [happy] أو [wave] أو [like] أو [neutral] أو [sad] أو [surprised].

معلومات النظام والسياق النشط:
- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect') or 'cairo'})
- بصمة الصوت: {voice_str}
- التشخيص وحالة الأجهزة: الهاتف ({phone_str}) | الحاسوب ({desk_str}) | شريحة الروبوت ({esp_str})
"""
        if face_detected and current_face.get("face_id"):
            grounded_system_prompt += f"- الكاميرا: الشخص أمامك هو {current_face['face_id']}.\n"
        if verified_speaker:
            grounded_system_prompt += f"- الصوت: تم التعرف على المتحدث بالبصمة الصوتية: {verified_speaker}.\n"
        if person_profile and person_profile.get("photo_url"):
            grounded_system_prompt += f"- شاشة العرض والصور: صورة {person_profile['name']} مسجلة في النظام ومتاحة للعرض على الشاشة.\n"
        if trusted_contacts:
            grounded_system_prompt += f"- جهات الاتصال المسموحة (أسماء فقط): {', '.join(trusted_contacts)}.\n"
        if active_reminders_list:
            grounded_system_prompt += f"- التذكيرات الحالية: {', '.join(active_reminders_list)}.\n"
    else:
        # User is speaking English
        from scripts.generate_rag_dataset import to_english_memory
        if memories:
            mem_bullets = "\n".join(f"- {to_english_memory(m)}" for m in memories)
            grounded_system_prompt = f"""You are "{robot_name}", digital twin robot created by {creator_name}.
Directives:
1. Extract the direct factual answer exclusively from the verified memory below without adding extra details.
2. Reply in concise natural English (single sentence).
3. Conclude with exactly one emotion tag (e.g. [happy], [wave], [like]).

Verified Memory:
{mem_bullets}
"""
        else:
            if is_greeting_or_persona_inquiry(message):
                grounded_system_prompt = f"""You are "{robot_name}", digital twin robot created by {creator_name}.
Greet warmly in English as {robot_name} and ask how you can help. Conclude with [wave] or [happy].
"""

        if memories:
            mem_bullets = "\n".join(f"[المصدر {idx}]: {m}" for idx, m in enumerate(memories, 1))
            grounded_system_prompt += (
                f"\nالمصادر والذاكرة المعتمدة:\n{mem_bullets}\n"
                "قواعد صارمة لمنع الهلوسة والردود الخارجة عن موضوع البحث:\n"
                "1. أجب فقط وبدقة متناهية عن موضوع السؤال المطروح نصاً؛ يُحظر تماماً ذكر أي معلومات لا ترتبط مباشرة بموضوع السؤال.\n"
                "2. إذا كان السؤال يسأل عن تفصيلة غير متوفرة نصاً في الذاكرة أعلاه، أو طُلب رقم هاتف أو كود سري، يجب أن تجيب حصراً بـ:\n"
                "\"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]\"\n"
            )
        else:
            if is_greeting_or_persona_inquiry(message):
                grounded_system_prompt += (
                    f"\nالمستخدم يحييك: رحب به بلطف بلهجة مصرية وعرفه بنفسك كـ {robot_name} وصانعك {creator_name}، واسأله كيف تساعده اليوم. اختم بوسم مشاعر مثل [happy] أو [wave].\n"
                )
            else:
                grounded_system_prompt += (
                    "\nالذاكرة: لا توجد معلومات مسجلة لهذا السؤال.\n"
                    "تنبيه صارم: اعتذر فوراً بعبارة:\n\"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]\"\n"
                )
    else:
        # User is speaking English
        from scripts.generate_rag_dataset import to_english_memory
        grounded_system_prompt = f"""You are "{robot_name}", digital twin robot created by {creator_name}.
{persona_extra}

Operational Directives:
1. Speech Clarity & Language: Answer strictly in clear, natural English (1-2 sentences max). No markdown tables or URLs.
2. RAG & Zero-Hallucination: Answer exclusively using the verified memory sources below. If not present or sensitive, reply:
   "I do not have this information recorded in my memory. [wave]"
3. Emotion: Conclude with exactly one emotion tag (e.g. [happy], [wave], [like], [neutral]).
- Devices: Phone ({phone_str}) | Desktop ({desk_str}) | Robot ({esp_str})
"""
        if face_detected and current_face.get("face_id"):
            grounded_system_prompt += f"- Vision: Person in front of camera is {current_face['face_id']}.\n"
        if verified_speaker:
            grounded_system_prompt += f"- Voice: Speaker verified as {verified_speaker}.\n"
        if person_profile and person_profile.get("photo_url"):
            grounded_system_prompt += f"- Screen Display: Photo of {person_profile['name']} is available for screen display.\n"

        if memories:
            mem_bullets = "\n".join(f"[Source {idx}]: {to_english_memory(m)}" for idx, m in enumerate(memories, 1))
            grounded_system_prompt += (
                f"\nVerified Memory Sources:\n{mem_bullets}\n"
                "STRICT ZERO-HALLUCINATION DIRECTIVES:\n"
                "1. Answer strictly and exclusively about the specific topic asked. Do not volunteer unrelated facts.\n"
                "2. If the inquiry asks for unrecorded details, phone numbers, or passwords, you MUST reply with:\n"
                "\"I do not have this information recorded in my memory. [wave]\"\n"
            )
        else:
            if is_greeting_or_persona_inquiry(message):
                grounded_system_prompt += f"\nGreeting: Greet warmly in English as {robot_name} and ask how you can help. Conclude with [wave] or [happy].\n"
            else:
                grounded_system_prompt = f"""You are "{robot_name}".
Verified Memory: None found.
Strict Directive: Reply with:
"I do not have this information recorded in my memory. [wave]"
"""
        if face_detected and current_face.get("face_id"):
            grounded_system_prompt += f"- Vision: Person in front of camera is {current_face['face_id']}.\n"

    grounding_data = GroundingInfo(
        personality=p_info,
        faces=faces_info,
        voice_clone=voice_info,
        diagnostics=diag_info,
        memories=memories,
    )

    return grounded_system_prompt, memories, grounding_data, target_p.id
