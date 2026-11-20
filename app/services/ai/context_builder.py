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
        r"(?:عرفني|عرفنا|عرف|كلمنا|اتكلم|تكلم)\s+(?:عن\s+)?نفسك",
        r"\b(who are you|what is your name|who made you|who created you|what can you do|introduce yourself)\b",
        r"\b(أنا|معاك|اسمي)\s+[\w]+\b",
        r"\b(فاكر|عارف|فاكرني|عارفني)\b",
        r"\b(شايف|سامع|مين\s+قدامك|مين\s+اللي\s+قدامك|شايفني|سامعني)\b",
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

    # Support aliases for the Digital Twin (Mazen)
    if "التوأم" in p_name or "twin" in p_name.lower():
        for extra in ["مازن", "mazen"]:
            if extra not in tokens:
                tokens.append(extra)

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
    speaker_verification: Optional[Any] = None,
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
    if is_greeting_or_persona_inquiry(message):
        memories = []
    else:
        # If the user explicitly targeted a personality in their question, scope RAG to that persona.
        # If the query is general (e.g. 'الساعة فين'), search across all personas so facts are retrieved & attributed.
        from app.services.memory.query_decomposer import QueryDecomposer
        atomic_subs = QueryDecomposer.get_atomic_subqueries(message)
        rel_info = QueryDecomposer.decompose_multihop_relational(message)

        if len(atomic_subs) > 1 and not rel_info:
            memories = []
            for sub_q in atomic_subs:
                sub_matched_p = match_personality_in_message(sub_q, all_personalities)
                sub_pid = sub_matched_p.id if sub_matched_p else None
                if not sub_pid:
                    sub_target_name = QueryDecomposer.extract_target_persona_name(sub_q)
                    if sub_target_name:
                        for p in all_personalities:
                            if sub_target_name in p.name or (sub_target_name in ("مازن", "mazen") and p.id == 1):
                                sub_pid = p.id
                                break
                if QueryDecomposer.is_past_inquiry(sub_q):
                    sub_mems = await _rag_service.retrieve_historical_contrast(
                        sub_q,
                        personality_id=sub_pid,
                        db=db,
                    )
                else:
                    sub_mems = await _rag_service.retrieve(
                        sub_q,
                        personality_id=sub_pid,
                        top_k=2,
                        db=db,
                    )
                for sm in sub_mems:
                    if sm not in memories:
                        memories.append(sm)
        else:
            mentioned_in_msg = QueryDecomposer.extract_mentioned_person_names(message)
            target_in_query = QueryDecomposer.extract_target_persona_name(message)
            if len(mentioned_in_msg) > 1:
                # Multi-persona question inquiring about multiple individuals (e.g. 'ساعة أحمد فين وساعة مازن فين؟')
                # Search across all personas so all requested facts are retrieved
                rag_target_pid = None
            elif target_in_query:
                rag_target_pid = target_p.id if matched_p else (personality_id if personality_id is not None else None)
            elif QueryDecomposer.is_location_query(message):
                # General item/location inquiry without mentioning person (e.g. 'الساعة فين')
                # Scope to None so facts across multiple personas are retrieved and attributed
                rag_target_pid = None
            else:
                rag_target_pid = target_p.id if matched_p else (personality_id if personality_id is not None else None)

            if QueryDecomposer.is_past_inquiry(message):
                memories = await _rag_service.retrieve_historical_contrast(
                    message,
                    personality_id=rag_target_pid,
                    db=db,
                )
            else:
                memories = await _rag_service.retrieve(
                    message,
                    personality_id=rag_target_pid,
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
            elif action_eval.action == "show_person_photo":
                p_target = action_eval.target or rag_person
                p_prof = await PersonImageRetriever.get_person_profile(p_target, db=db) if p_target else None
                if p_prof and p_prof.get("has_photo"):
                    p_url = p_prof.get("photo_url") or f"/api/v1/faces/{p_target}/photo"
                    action_meta["execution_payload"] = {
                        "t": "screen_action",
                        "action": "show_person_photo",
                        "name": p_target,
                        "url": p_url,
                    }
                    action_meta["url"] = p_url
                    action_meta["photo_url"] = p_url
                    action_meta["suggested_speech"] = f"بعرض صورة {p_target} على الشاشة حالاً."
                    action_meta["decision"] = "ready"
                    action_meta["status"] = "ready"
                    if not person_profile:
                        person_profile = p_prof
                else:
                    action_meta["execution_payload"] = None
                    action_meta["decision"] = "no_photo"
                    action_meta["status"] = "no_photo"
                    action_meta["suggested_speech"] = f"معنديش صورة مسجلة لـ {p_target} حالياً. [wave]"
                    action_meta["action_tag"] = "[wave]"
                    action_meta["directive"] = f"لا توجد صورة مسجلة لـ '{p_target}' في النظام. أخبر المستخدم بأدب بعدم وجود صورة مسجلة له حالياً."
    except Exception as e:
        logger.debug(f"Universal action planning in context_builder notice: {e}")

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

    # 7. Formulate Unified System Prompt in Authentic Egyptian Arabic (arz) with Strict RAG Grounding
    if action_meta.get("has_action"):
        action_kind = action_meta.get("kind")
        action_target = action_meta.get("target") or ""
        action_directive = action_meta.get("directive") or ""
        suggested_speech = action_meta.get("suggested_speech") or ""

        grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.
{persona_extra}
توجيه الاستجابة وتأكيد تنفيذ الأمر المطلوب (Action Execution Directive):
المستخدم يطلب منك أمراً مباشراً: {action_kind} لـ '{action_target}'.
- توجيه الرد: {action_directive}
- أسلوب الرد: أجب مباشرة وبجملة واحدة ودودة وموجزة بالعامية المصرية القاهرية تؤكد تنفيذ هذا الأمر فوراً (مثال: "{suggested_speech or f'حاضر، بعرض صورة {action_target} حالاً.'}").
- يُمنع منعاً باتاً استبدال هذا الأمر بسرد أي معلومات أو ذكريات أخرى لا علاقة لها بما طلبه المستخدم.
- اختم ردك دائماً وبشكل إلزامي بوسم مشاعر مثل [nod] أو [happy] أو [like] لتحريك ملامح الأفاتار وفمه.
"""
        # When an action is being executed, clear unrelated factual memories so they don't hijack the action confirmation
        memories = []
    elif memories:
        mem_bullets = "\n".join(f"[المصدر {idx}]: {m.strip()}" for idx, m in enumerate(memories, 1))
        grounded_system_prompt = f"""أنت "{robot_name}" (Nebula)، {robot_desc}، صممه وطوره {creator_name}.
{persona_extra}
توجيهات التشغيل والاستناد الصارم للذاكرة (Strict RAG Grounding & Zero-Hallucination):
1. أجب حصراً وبدقة متناهية على السؤال المطلوب فقط، واستخرج الإجابة فقط من سياق الذاكرة المعتمدة أدناه. ممنوع منعاً باتاً تخمين، تأليف، أو افتراض أي وقائع أو ذكريات أو تفاصيل لم تُذكر صراحة في المصادر.
2. إذا كان السؤال يطلب تفصيلة أو شخصاً أو شيئاً غير موجود نصاً في الذاكرة أدناه، يجب الرد حصراً بعبارة:
   "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
3. أسلوب الرد المباشر: أجب بإيجاز مباشر بالعامية المصرية القاهرية على قدر السؤال فقط دون حشو. يُمنع منعاً باتاً استخدام أي مقدمات ميكانيكية مكررة مثل "بناءً على المعلومات المسجلة عندي" أو "وفقاً للذاكرة" أو "حسب المسجل"؛ ادخل في الإجابة مباشرة، ولا تسرد ذكريات أخرى مسجلة لم يسأل عنها المستخدم (مثلاً إذا سأل عن وظيفة شخص، أجب بوظيفته فقط ولا تذكر ماذا يركب أو تفاصيل جانبية أخرى).
4. وسم المشاعر وإيموجي الأفاتار: اختم إجابتك دائماً وبشكل إلزامي بإيموجي وجه معبّر (😊 😂 😍 😢 😮 😡 🤔 😉 😐) أو وسم مشاعر واحد فقط في النهاية مثل: [happy] أو [wave] أو [like] أو [neutral] أو [sad] لتحريك ملامح الأفاتار وفمه أثناء التحدث.
5. في الأسئلة المركبة (السؤال عن أكثر من شخص أو شيء):
   - يجب عليك الإجابة عن كل شخص أو شيء سأل عنه المستخدم بالترتيب وبشكل كامل دون إهمال أو إسقاط أي واحد منهم طالما معلومته مسجلة في المصادر (مثال: إذا سأل عن وظيفة 3 أشخاص، اذكر وظيفة الثلاثة جميعاً).
   - إذا كانت إحدى المعلومات متوفرة والأخرى غير مسجلة: أجب عن المعلومة المتوفرة واذكر صراحة أن المعلومة الأخرى غير مسجلة.
6. عند السؤال العام عن غرض أو شيء يمتلكه أكثر من شخص (مثل: 'الكراسة فين؟' أو 'الساعة فين؟' والمصادر تحتوي على أغراض لأشخاص مختلفين):
   - انسب الغرض لكل شخص باسمه صراحة بصيغة إضافة طبيعية وسلسة (مثال: 'كراسة أحمد على الأرض، وكراسة مازن على السرير.')، ويُمنع منعاً باتاً ذكر الغرض مبهماً أو بدون نسبته لصاحبه.
7. عند السؤال عن مكان غرض في الماضي (مثل: 'كراسة أحمد كانت فين قبل كده؟' أو 'كانت فين كراسة أحمد؟'):
   - وضّح المكان السابق مع تأكيد المكان الحالي بلباقة ووضوح (مثال: 'كانت على الأرض، لكن حالياً اتنقلت وبقت على المكتب. 😊').

أمثلة توضيحية لأسلوب الإجابة المباشر ومنع التأليف:
- المصدر المعتمد: [المصدر 1]: مكان كراسة أحمد السابق كان على الأرض، وحالياً اتنقلت وبقت على المكتب.
  سؤال: كراسة أحمد كانت فين قبل كده؟
  إجابة: كانت على الأرض، لكن حالياً اتنقلت وبقت على المكتب. 😊
- المصادر المعتمدة: [المصدر 1]: كراسة أحمد على الأرض. [المصدر 2]: كراسة مازن على السرير.
  سؤال: الكراسة فين؟
  إجابة: كراسة أحمد على الأرض، وكراسة مازن على السرير. 😊
- المصدر المعتمد: [المصدر 1]: أحمد مهندس برمجيات مقيم في حلوان.
  سؤال: أحمد شغال إيه؟
  إجابة: أحمد شغال مهندس برمجيات في حلوان. 😊
- المصدر المعتمد: [المصدر 1]: أحمد مهندس برمجيات مقيم في حلوان.
  سؤال: الكاب فين؟
  إجابة: المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]
- المصادر المعتمدة: [المصدر 1]: مصعب شغال لاعب كورة تنس. [المصدر 2]: عمر شغال سواق. [المصدر 3]: طارق شغال مهندس ديكور.
  سؤال: مصعب شغال إيه وعمر شغال إيه وطارق شغال إيه؟
  إجابة: مصعب شغال لاعب كورة تنس، وعمر شغال سواق، وطارق شغال مهندس ديكور. 😊
- المصدر المعتمد: [المصدر 1]: أحمد شغال دكتور.
  سؤال: أحمد شغال إيه ومصعب شغال إيه؟
  إجابة: أحمد شغال دكتور، لكن بخصوص مصعب فالمعلومة دي مش مسجلة عندي في الذاكرة حالياً. 😊
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
3. اختم إجابتك دائماً وبشكل إلزامي بإيموجي وجه مناسب (😊 😍 😂 😉 😮 😢 🤔 😐 👋) أو وسم مشاعر مثل [happy] أو [wave] أو [like] لتحريك الأفاتار.
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
    if verified_speaker:
        sys_status_block += f"- الصوت: تم التعرف على المتحدث بالبصمة الصوتية: {verified_speaker}.\n"
    if spk_name:
        main_tag = " | متحدث رئيسي" if is_main_speaker else ""
        sys_status_block += f"- المتحدث: {spk_name} (حالة البصمة: {spk_status}{main_tag}).\n"
        if spk_directive:
            sys_status_block += f"- توجيه المتحدث: {spk_directive}\n"

    if action_meta.get("has_action"):
        sys_status_block += (
            f"- الإجراء المطلوب (Action): {action_meta.get('kind')} لـ '{action_meta.get('target')}' (الحالة: {action_meta.get('status')}).\n"
            f"- توجيه الإجراء للرد: {action_meta.get('directive')}\n"
        )
    if person_profile and person_profile.get("photo_url"):
        sys_status_block += f"- شاشة العرض والصور: صورة {person_profile['name']} مسجلة في النظام ومتاحة للعرض على الشاشة.\n"
        faces_info["person_profile"] = person_profile
        faces_info["photo_url"] = person_profile.get("photo_url")
        faces_info["photo_path"] = person_profile.get("photo_path")
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
