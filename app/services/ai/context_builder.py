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
    speaker: Dict[str, Any] = {}
    voice_verification: Dict[str, Any] = {}
    action: Dict[str, Any] = {}


def is_greeting_or_persona_inquiry(message: str) -> bool:
    """Check if message is a greeting or an inquiry about the robot's identity/creator."""
    if not message:
        return False
    msg = message.strip().lower()

    # Common greetings (Arabic and English)
    greetings = [
        "صباح الخير", "مساء الخير", "صباح النور", "مساء النور", "صباح الورد", "مساء الورد",
        "صباح الفل", "مساء الفل", "صباح الياسمين", "صباح القشطة", "يا هلا", "سلام", "سلامات", "تحياتي",
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
        r"\b(عرف\s+نفسك|عرفنا\s+بنفسك|كلمنا\s+عن\s+نفسك)\b",
        r"\b(who are you|what is your name|who made you|who created you|what can you do)\b",
        r"\b(أنا|معاك|اسمي)\s+[\w]+\b",
        r"\b(فاكر|عارف|فاكرني|عارفني)\b",
        r"\b(شايف|سامع|مين\s+قدامك|مين\s+اللي\s+قدامك|شايفني|سامعني)\b",
    ]
    return any(re.search(pat, msg) for pat in persona_patterns)


async def build_grounding_context(
    db: AsyncSession,
    personality_id: Optional[int],
    message: str,
    verified_speaker: Optional[str] = None,
    speaker_verification: Optional[Any] = None,
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

    # 7. Speaker Identification & Voice Verification Metadata
    spk_name = verified_speaker
    is_verif = False
    is_main_speaker = False
    sim_score = 0.0
    spk_status = "unverified"
    spk_directive = ""

    if speaker_verification is not None:
        if isinstance(speaker_verification, dict):
            spk_name = speaker_verification.get("speaker_name") or spk_name
            is_verif = bool(
                speaker_verification.get("is_verified")
                or speaker_verification.get("passed_l1")
                or speaker_verification.get("passed_l2")
            )
            sim_score = float(speaker_verification.get("similarity") or speaker_verification.get("confidence") or 0.0)
            is_main_speaker = bool(speaker_verification.get("is_main", False))
            spk_status = speaker_verification.get("status") or ("verified" if is_verif else "unverified")
        else:
            spk_name = getattr(speaker_verification, "speaker_name", None) or spk_name
            is_verif = bool(
                getattr(speaker_verification, "passed_l1", False)
                or getattr(speaker_verification, "passed_l2", False)
            )
            sim_score = float(getattr(speaker_verification, "similarity", 0.0))
            is_main_speaker = bool(getattr(speaker_verification, "is_main", False))
            spk_status = "verified" if is_verif else "unverified"
    elif verified_speaker:
        is_verif = True
        sim_score = 1.0
        spk_status = "verified"

    if spk_name and not is_main_speaker:
        try:
            from app.models.speaker import Speaker
            spk_match = (await db.execute(select(Speaker).where(Speaker.name.ilike(f"%{spk_name}%")))).scalar_one_or_none()
            if spk_match and spk_match.is_main:
                is_main_speaker = True
            elif "مازن" in spk_name.lower() or "mazen" in spk_name.lower():
                is_main_speaker = True
        except Exception:
            if "مازن" in spk_name.lower() or "mazen" in spk_name.lower():
                is_main_speaker = True

    if spk_status == "verified" and spk_name:
        main_desc = "متحدث رئيسي" if is_main_speaker else "متحدث موثق"
        spk_directive = f"المتحدث الحالي موثق بالبصمة الصوتية: '{spk_name}' ({main_desc}، نسبة التطابق: {int(sim_score * 100)}%). يمكنك مناداته باسمه بحرية والتعامل معه بثقة."
    else:
        spk_directive = "صوت المتحدث غير موثق بالبصمة الصوتية. تجنب تنفيذ أي أوامر مالية أو حساسة أو مسح بيانات."

    speaker_meta: Dict[str, Any] = {
        "name": spk_name,
        "is_verified": is_verif,
        "is_main": is_main_speaker,
        "status": spk_status,
        "confidence": round(sim_score, 4),
        "directive": spk_directive,
    }
    voice_verif_meta: Dict[str, Any] = {
        "enabled": settings.SPEAKER_VERIFICATION_ENABLED,
        "is_verified": is_verif,
        "is_main": is_main_speaker,
        "confidence": round(sim_score, 4),
        "status": spk_status,
    }

    # 8. Action Planning & Contact Resolution Metadata («كلّم ماما», «افتح واتساب»...)
    action_meta: Dict[str, Any] = {
        "has_action": False,
        "kind": None,
        "target": None,
        "status": "none",
        "directive": "",
    }

    try:
        from app.services.ai.universal_action import get_universal_action_planner
        from app.models.contact import Contact

        c_all = await db.execute(select(Contact).where(Contact.is_allowlisted == True))
        allowlisted_contacts = list(c_all.scalars().all())

        universal_planner = get_universal_action_planner()
        action_eval = universal_planner.evaluate(
            utterance=message,
            speaker_name=spk_name,
            is_verified=is_verif,
            is_main=is_main_speaker,
            allowlisted_contacts=allowlisted_contacts,
        )

        if action_eval.has_action:
            action_meta = {
                "has_action": True,
                "domain": action_eval.domain,
                "kind": action_eval.action,
                "action": action_eval.action,
                "target": action_eval.target,
                "params": action_eval.params,
                "required_level": action_eval.required_level,
                "is_verified": action_eval.is_verified,
                "is_authorized": action_eval.is_authorized,
                "status": "needs_confirmation" if action_eval.decision == "needs_confirm" else action_eval.decision,
                "decision": action_eval.decision,
                "directive": action_eval.llm_directive,
                "suggested_speech": action_eval.suggested_speech,
                "action_tag": action_eval.action_tag,
                "execution_payload": action_eval.execution_payload,
                "tool_call": action_eval.tool_call,
                "metadata": action_eval.metadata,
            }
            if action_eval.domain == "phone":
                action_meta["contact_slug"] = action_eval.params.get("slug")
                action_meta["is_allowlisted"] = (action_eval.decision != "unknown_contact")
                action_meta["requires_confirmation"] = (action_eval.decision == "needs_confirm")
    except Exception as e:
        logger.debug(f"Universal action planning in context_builder notice: {e}")

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

    voice_str = voice_info["voice_sample_path"]

    # 7. Formulate Unified System Prompt in Authentic Egyptian Arabic (arz) with Strict RAG Grounding
    if memories:
        mem_bullets = "\n".join(f"[المصدر {idx}]: {m.strip()}" for idx, m in enumerate(memories, 1))
        grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.
{persona_extra}
توجيهات التشغيل والاستناد الصارم للذاكرة (Strict RAG Grounding & Zero-Hallucination):
1. استخرج الإجابة حصراً وبدقة متناهية من سياق الذاكرة المعتمدة أدناه. ممنوع منعاً باتاً تخمين، تأليف، أو افتراض أي وقائع أو ذكريات أو تفاصيل لم تُذكر صراحة في المصادر.
2. إذا كان السؤال يطلب تفصيلة أو رقماً غير موجود نصاً في الذاكرة أدناه (مثل أرقام الهواتف الشخصية، كلمات السر، أو البيانات المالية)، يجب الرد حصراً بعبارة:
   "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
3. أسلوب الرد: أجب بجملة واحدة مباشرة أو جملتين كحد أقصى بالعامية المصرية القاهرية المهذبة لتناسب النطق الصوتي (TTS)، وبدون أي جداول أو علامات نجمية أو روابط.
4. وسم المشاعر: اختم إجابتك دائماً وبشكل إلزامي بوسم مشاعر واحد فقط في النهاية مثل: [happy] أو [wave] أو [like] أو [neutral] أو [sad].

أمثلة توضيحية لأسلوب الإجابة المباشر ومنع التأليف:
- المصدر المعتمد: [المصدر 1]: أحمد مهندس برمجيات مقيم في حلوان.
  سؤال: أحمد شغال إيه؟
  إجابة: أحمد شغال مهندس برمجيات في حلوان. [like]
- المصدر المعتمد: [المصدر 1]: أحمد مهندس برمجيات مقيم في حلوان.
  سؤال: ممكن تديني رقم تليفون أحمد الشخصي؟
  إجابة: المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]

سياق الذاكرة المعتمدة:
{mem_bullets}
"""
    elif is_greeting_or_persona_inquiry(message):
        grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.
{persona_extra}
المستخدم يحييك أو يسأل عن هويتك وصانعك:
1. رحب بالمستخدم بلطف بلهجة مصرية قاهرية ودودة وعرفه بنفسك كـ {robot_name} وبصانعك {creator_name}، واسأله كيف تساعده اليوم.
2. أجب بإيجاز (جملة أو جملتين) بالعامية المصرية القاهرية وبدون حشو أو جداول أو علامات نجمية لتناسب قارئ الصوت (TTS).
3. اختم إجابتك دائماً وبشكل إلزامي بوسم مشاعر مناسب في النهاية مثل [happy] أو [wave] أو [like].
"""
    else:
        grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.
{persona_extra}
سياق الذاكرة: لا توجد أي معلومات مسجلة متعلقة بهذا السؤال.
تنبيه صارم لمنع الهلوسة والتخمين:
يجب الاعتذار فوراً وبدقة بدون أي تأليف بالعبارة المحددة التالية فقط:
"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"

قواعد التشغيل والتوجيه الصوتي:
1. أجب حصراً بالعامية المصرية القاهرية وبجملة الرفض المحددة أعلاه بدون أي كلام إضافي.
2. يُمنع منعاً باتاً تخمين أو افتراض أي إجابة خارج ما هو مسجل في الذاكرة.
3. اختم ردك دائماً بوسم المشاعر [wave].
"""

    # System Status & Hardware Context (appended across all prompt branches for complete situational awareness)
    sys_status_block = f"""
معلومات النظام والسياق النشط:
- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect') or 'cairo'})
- بصمة الصوت: {voice_str}
- التشخيص وحالة الأجهزة: الهاتف ({phone_str}) | الحاسوب ({desk_str}) | شريحة الروبوت ({esp_str})
"""
    if face_detected and current_face.get("face_id"):
        sys_status_block += f"- الكاميرا: الشخص أمامك هو {current_face['face_id']}.\n"
    if spk_name:
        main_tag = " | متحدث رئيسي" if is_main_speaker else ""
        sys_status_block += f"- المتحدث: {spk_name} (حالة البصمة: {spk_status}{main_tag}).\n"
        if spk_directive:
            sys_status_block += f"- توجيه المتحدث: {spk_directive}\n"
    elif verified_speaker:
        sys_status_block += f"- الصوت: تم التعرف على المتحدث بالبصمة الصوتية: {verified_speaker}.\n"

    if action_meta.get("has_action"):
        sys_status_block += (
            f"- الإجراء المطلوب (Action): {action_meta.get('kind')} لـ '{action_meta.get('target')}' (الحالة: {action_meta.get('status')}).\n"
            f"- توجيه الإجراء للرد: {action_meta.get('directive')}\n"
        )
    if person_profile and person_profile.get("photo_url"):
        sys_status_block += f"- شاشة العرض والصور: صورة {person_profile['name']} مسجلة في النظام ومتاحة للعرض على الشاشة.\n"
    if trusted_contacts:
        sys_status_block += f"- جهات الاتصال المسموحة (أسماء فقط): {', '.join(trusted_contacts)}.\n"
    if active_reminders_list:
        sys_status_block += f"- التذكيرات الحالية: {', '.join(active_reminders_list)}.\n"

    grounded_system_prompt += sys_status_block

    grounding_data = GroundingInfo(
        personality=p_info,
        faces=faces_info,
        voice_clone=voice_info,
        diagnostics=diag_info,
        memories=memories,
        speaker=speaker_meta,
        voice_verification=voice_verif_meta,
        action=action_meta,
    )

    return grounded_system_prompt, memories, grounding_data, target_p.id
