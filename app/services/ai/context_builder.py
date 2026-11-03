"""
Context Builder — Unifies grounding across Personality, Memories (RAG),
Vision (UniFace / Person Photo Retrieval), Voice Clone, and Desktop Screen Diagnostics.
Supports dynamic multi-personality routing and zero-hardcoded creator resolution.
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
from app.utils.masri_normalizer import normalize_masri_orthography
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


def extract_clean_personality_tokens(p_name: str) -> List[str]:
    """
    Extracts searchable name tokens from a personality name.
    Strips parentheses/brackets (e.g. '(Default)', '(Dev)', '[Admin]').
    Returns normalized tokens of length >= 2.
    """
    if not p_name:
        return []
    clean = re.sub(r"[\(\[\{].*?[\)\]\}]", "", p_name).strip()
    norm = normalize_masri_orthography(clean)

    tokens: List[str] = []
    if len(norm) >= 2:
        tokens.append(norm)

    parts = [part.strip() for part in re.split(r"[\s\-_/]+", norm) if len(part.strip()) >= 2]
    noise = {"default", "bot", "v1", "v2", "روبوت", "افتراضي", "الافتراضي"}
    for part in parts:
        if part not in noise and part not in tokens:
            tokens.append(part)

    latin_tokens = re.findall(r"[a-zA-Z]{3,}", p_name.lower())
    for lt in latin_tokens:
        if lt not in noise and lt not in tokens:
            tokens.append(lt)

    return tokens


def match_personality_in_message(
    message: str,
    personalities: List[Personality],
) -> Optional[Personality]:
    """
    Dynamically identifies if any personality's name or alias is explicitly mentioned in the user message.
    Uses Masri orthographic normalization and prefix/boundary awareness.
    Supports N arbitrary personalities without any hardcoded names.
    Prioritizes longer and more specific name matches.
    """
    if not message or not personalities:
        return None

    norm_msg = normalize_masri_orthography(message)
    raw_lower = message.lower()

    best_match: Optional[Personality] = None
    best_match_len = 0

    for p in personalities:
        if not p.name:
            continue
        tokens = extract_clean_personality_tokens(p.name)
        for token in tokens:
            matched = False
            token_len = len(token)

            # Check Latin / English tokens
            if re.match(r"^[a-zA-Z0-9]+$", token):
                pattern = rf"\b{re.escape(token)}\b"
                if re.search(pattern, raw_lower):
                    matched = True
            else:
                # Arabic token: check with vocative (يا), prepositions (لـ, بـ, و, ف), or word boundaries
                if token_len >= 3:
                    pattern = rf"(?:^|[\s\b]|(?:يا\s*)|[ويفلب]ـ?){re.escape(token)}(?:$|[\s\b،,\.!\?؟])"
                    if re.search(pattern, norm_msg):
                        matched = True
                elif token_len == 2:
                    pattern = rf"(?:^|\s|(?:يا\s*)){re.escape(token)}(?:$|[\s،,\.!\?؟])"
                    if re.search(pattern, norm_msg):
                        matched = True

            if matched and token_len > best_match_len:
                best_match = p
                best_match_len = token_len

    return best_match


def match_personality_by_identity(
    identity_name: str,
    personalities: List[Personality],
) -> Optional[Personality]:
    """
    Matches a biometric identity (Face ID from camera or Verified Speaker from voice) to a personality.
    Matches against personality name tokens or individual identity name parts.
    """
    if not identity_name or not personalities:
        return None

    norm_id = normalize_masri_orthography(identity_name).strip()
    if not norm_id:
        return None

    first_name = norm_id.split()[0] if norm_id else ""

    for p in personalities:
        if not p.name:
            continue
        tokens = extract_clean_personality_tokens(p.name)
        for token in tokens:
            if token == norm_id or (len(token) >= 3 and token == first_name) or (len(norm_id) >= 3 and norm_id in token):
                return p

    return None


async def resolve_creator_name(
    target_p: Optional[Personality],
    registered_faces: List[str],
    db: AsyncSession,
    is_arabic: bool = True,
) -> str:
    """
    Dynamically resolves the creator / owner name for the robot persona with zero hardcoded values:
    1. Check target_p's linked owner User record (User.full_name)
    2. Extract creator name from target_p.system_prompt or target_p.description via regex
    3. Use personality name if it represents an individual person (digital twin)
    4. First registered face profile
    5. Generic team attribution ("فريق التطوير والمهندسين" / "the engineering team")
    """
    # 1. Owner User record
    if target_p and target_p.user_id:
        try:
            from app.models.user import User
            user = await db.get(User, target_p.user_id)
            if user and user.full_name and user.full_name.strip():
                return user.full_name.strip()
        except Exception as e:
            logger.debug(f"Could not load owner user for creator resolution: {e}")

    # 2. Regex extraction from system prompt or description
    if target_p:
        text_sources = f"{target_p.system_prompt or ''}\n{target_p.description or ''}"
        if text_sources.strip():
            # Arabic creator patterns
            ar_patterns = [
                r"(?:صممه|طوره|صنعه|برمجه|ابتكره|أنشأه|انشاه)(?:\s+و\s*(?:صممه|طوره|صنعه|برمجه|ابتكره))*\s*(?:المهندس|المهندسة|م\.)?\s*([^\d\n\.\،\؛\!]+?)(?:\.|\s+(?:تجيب|ويتحدث|ليساعد|ليعمل|ليكون|وهو|وهي|الذي|التي)|،|؛|\n|$)",
                r"(?:الخاص بـ|توأم رقمي لـ|التوأم الرقمي لـ|توأم رقمي لـ)\s*(?:المهندس|المهندسة|م\.)?\s*([^\d\n\.\،\؛\!]+?)(?:\.|\s+(?:تجيب|ويتحدث|ليساعد|ليعمل|ليكون|وهو|وهي|الذي|التي)|،|؛|\n|$)",
            ]
            for pat in ar_patterns:
                match = re.search(pat, text_sources)
                if match:
                    cand = match.group(1).strip().strip("\"'()[]{}")
                    cand = re.sub(r"\s+(وهو|وهي|الذي|التي|ليكون|ليعمل|ليساعد).*$", "", cand).strip()
                    if 2 <= len(cand) <= 40:
                        return cand

            # English creator patterns
            en_patterns = [
                r"(?:created by|developed by|designed by|built by)\s+([A-Za-z\s]+?)(?:\.|\,|$|\n)",
            ]
            for pat in en_patterns:
                match = re.search(pat, text_sources, re.IGNORECASE)
                if match:
                    cand = match.group(1).strip().strip("\"'()[]{}")
                    if 2 <= len(cand) <= 40:
                        return cand

    # 3. Personality name itself if it's a digital twin (person name)
    if target_p and target_p.name:
        clean_name = re.sub(r"[\(\[\{].*?[\)\]\}]", "", target_p.name).strip()
        generic_names = {"توت", "نيبولا", "nebula", "bot", "robot", "assistant", "ai", "افتراضي"}
        if clean_name.lower() not in generic_names and len(clean_name) >= 3:
            return clean_name

    # 4. First registered face profile
    if registered_faces and len(registered_faces) > 0 and registered_faces[0].strip():
        return registered_faces[0].strip()

    # 5. Generic professional fallback (Zero hardcoded names)
    return "فريق التطوير والمهندسين" if is_arabic else "the engineering team"


async def build_grounding_context(
    db: AsyncSession,
    personality_id: Optional[int],
    message: str,
    verified_speaker: Optional[str] = None,
) -> Tuple[str, List[str], GroundingInfo, int]:
    """
    Build unified grounding context across:
    1. Faces & Registered Person Profiles (Vision / UniFace) - evaluated first to enable biometric routing
    2. Personalities (Dynamic Hybrid Smart Routing across N personalities, zero fallback model)
    3. Visual Profile & Photo Retrieval
    4. Memories (RAG with In-Memory VectorStore)
    5. Voice Clone (XTTS / sample) & Speaker Verification
    6. Screen & Hardware Diagnostics (Connected channels)
    """
    # 1. Faces & Registered Person Profiles (Vision + Face Profiles)
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
        from app.services.vision.face_service import get_face_service
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

    # 2. Determine Personality: Dynamic Hybrid Smart Routing
    # Priority: 1) Explicit mention in question -> 2) Camera Face -> 3) Voice Speaker -> 4) Requested ID -> 5) Active -> 6) Default
    target_p: Optional[Personality] = None
    all_personalities_res = await db.execute(select(Personality))
    all_personalities = list(all_personalities_res.scalars().all())

    # Priority 1: Explicit name in user question
    matched_p = match_personality_in_message(message, all_personalities)
    if matched_p:
        target_p = matched_p
        logger.info(f"Dynamically routed personality to '{target_p.name}' (ID: {target_p.id}) based on explicit mention in message.")

    # Priority 2: Biometric Camera Face
    if not target_p and detected_face_name:
        matched_p = match_personality_by_identity(detected_face_name, all_personalities)
        if matched_p:
            target_p = matched_p
            logger.info(f"Biometrically routed personality to '{target_p.name}' (ID: {target_p.id}) based on detected face: {detected_face_name}.")

    # Priority 3: Biometric Verified Voice Speaker
    if not target_p and verified_speaker:
        matched_p = match_personality_by_identity(verified_speaker, all_personalities)
        if matched_p:
            target_p = matched_p
            logger.info(f"Biometrically routed personality to '{target_p.name}' (ID: {target_p.id}) based on verified speaker: {verified_speaker}.")

    # Priority 4: Requested personality_id parameter
    if not target_p and personality_id:
        target_p = await db.get(Personality, personality_id)

    # Priority 5: Active personality in DB
    if not target_p:
        res = await db.execute(
            select(Personality).where(Personality.is_active == True).order_by(Personality.id.desc()).limit(1)  # noqa: E712
        )
        target_p = res.scalar_one_or_none()

    # Priority 6: Default fallback
    if not target_p:
        if all_personalities:
            target_p = all_personalities[0]
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

    # 3. Determine candidate person from: 1) Camera Face, 2) Verified Voice Speaker, 3) Mention in message
    candidate_from_query = PersonImageRetriever.extract_person_candidate(message, registered_faces)
    rag_person = detected_face_name or verified_speaker or candidate_from_query

    if not rag_person and target_p and target_p.name:
        p_name = target_p.name.strip()
        first_name = p_name.split()[0]
        norm_msg = normalize_masri_orthography(message)
        norm_first = normalize_masri_orthography(first_name)
        norm_full = normalize_masri_orthography(p_name)
        if (len(norm_first) >= 3 and norm_first in norm_msg) or (len(norm_full) >= 3 and norm_full in norm_msg):
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

    # 4. Memories (RAG grounded in Question, Person & VectorStore)
    memories = await _rag_service.retrieve(
        message,
        personality_id=target_p.id,
        db=db,
        person_name=rag_person,
    )

    # 5. Voice Clone & Speaker Verification
    voice_info = {
        "tts_provider": settings.TTS_PROVIDER,
        "voice_sample_path": target_p.voice_sample_path or "غير محدد (يستخدم الصوت الافتراضي)",
        "has_sample": bool(target_p.voice_sample_path),
        "verified_speaker": verified_speaker,
    }

    # 6. Diagnostics & Screen Status
    diag_status = manager.status()
    diag_info = {
        "phone_connected": bool(diag_status.get("phone", False)),
        "desktop_connected": bool(diag_status.get("desktops", 0) > 0 or diag_status.get("desktop", False)),
        "esp_connected": bool(diag_status.get("esp32", False) or diag_status.get("esp", False)),
        "backend_status": "ok",
    }

    # 7. Allowlisted Contacts & Reminders (Privacy: names only, zero numbers)
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

    is_arabic = bool(re.search(r"[\u0600-\u06FF]", message or ""))
    creator_name = await resolve_creator_name(target_p, registered_faces, db=db, is_arabic=is_arabic)

    robot_name = p_info.get("name") or "نيبولا"
    raw_desc = p_info.get("description") or ""
    robot_desc = raw_desc if raw_desc and raw_desc.strip() != "string" else "روبوت ذكاء اصطناعي وتوأم رقمي ذكي"

    custom_system_prompt = (target_p.system_prompt or "").strip()
    persona_extra = f"\nتوجيه الشخصية: {custom_system_prompt}\n" if custom_system_prompt else ""

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
"""

        # Append environmental & hardware telemetry
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
{persona_extra}
Directives:
1. Extract the direct factual answer exclusively from the verified memory below without adding extra details.
2. Reply in concise natural English (single sentence). No markdown tables or URLs.
3. Conclude with exactly one emotion tag (e.g. [happy], [wave], [like], [neutral]).

- Devices: Phone ({phone_str}) | Desktop ({desk_str}) | Robot ({esp_str})
Verified Memory:
{mem_bullets}
"""
        else:
            if is_greeting_or_persona_inquiry(message):
                grounded_system_prompt = f"""You are "{robot_name}", digital twin robot created by {creator_name}.
{persona_extra}
Greet warmly in English as {robot_name} and ask how you can help. Conclude with [wave] or [happy].
"""
            else:
                grounded_system_prompt = f"""You are "{robot_name}".
Verified Memory: None found.
Strict Directive: Reply with:
"I do not have this information recorded in my memory. [wave]"
"""

        # Append environmental & hardware telemetry
        if face_detected and current_face.get("face_id"):
            grounded_system_prompt += f"- Vision: Person in front of camera is {current_face['face_id']}.\n"
        if verified_speaker:
            grounded_system_prompt += f"- Voice: Speaker verified as {verified_speaker}.\n"
        if person_profile and person_profile.get("photo_url"):
            grounded_system_prompt += f"- Screen Display: Photo of {person_profile['name']} is available for screen display.\n"

    grounding_data = GroundingInfo(
        personality=p_info,
        faces=faces_info,
        voice_clone=voice_info,
        diagnostics=diag_info,
        memories=memories,
    )

    return grounded_system_prompt, memories, grounding_data, target_p.id
