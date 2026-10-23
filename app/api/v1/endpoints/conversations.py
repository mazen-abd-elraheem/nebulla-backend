"""Conversations + messages endpoints with interactive LLM chat and full system grounding."""

import time
import uuid
from typing import Optional, List, Dict, Any, Tuple

from fastapi import APIRouter, Depends, Query, HTTPException, Header, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_optional_user, api_key_scheme
from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import get_db
from app.models.conversation import Conversation, Message
from app.models.personality import Personality
from app.models.face_profile import FaceProfile
from app.providers.llm.factory import get_llm_provider
from app.services.ai.pipeline import clean_text_for_tts, _extract_emotion
from app.services.memory.rag_service import RAGService
from app.websocket.manager import manager
from app.websocket.handlers import get_face_service

logger = get_logger(__name__)

router = APIRouter()
_rag_service = RAGService()


# ── Schemas ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., description="Text message to send to the LLM", examples=["أهلاً، شايف مين قدامك؟"])
    session_id: Optional[str] = Field(None, description="Optional session UUID for multi-turn conversation tracking")
    personality_id: Optional[int] = Field(None, description="Specific personality ID to use (defaults to active personality)")
    stream: bool = Field(False, description="Whether to stream tokens via Server-Sent Events / chunked transfer")


class GroundingInfo(BaseModel):
    personality: Dict[str, Any]
    faces: Dict[str, Any]
    voice_clone: Dict[str, Any]
    diagnostics: Dict[str, Any]
    memories: List[str]


class ChatResponse(BaseModel):
    reply: str
    cleaned_reply: str
    session_id: str
    conversation_id: int
    emotion: str
    llm_latency_ms: float
    memories_used: List[str]
    grounding: Optional[GroundingInfo] = None


# ── Authentication Helper ────────────────────────────────────────────────────

async def _get_auth_user(
    user: Optional[str] = Depends(get_optional_user),
) -> str:
    """Allow chat without strict auth if unauthenticated or in DEBUG mode."""
    if user:
        return user
    return "guest_user"


# ── Grounding Context Builder ────────────────────────────────────────────────

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
    memories = await _rag_service.retrieve(message, personality_id=target_p.id)

    # 3. Faces (Vision / Face Recognition)
    face_service = get_face_service()
    current_face = face_service.get_current_face_info()
    faces_res = await db.execute(select(FaceProfile.name))
    registered_faces = list(faces_res.scalars().all())

    current_person_desc = "لا يوجد أحد أمام الكاميرا حالياً"
    if current_face.get("detected"):
        if current_face.get("face_id"):
            current_person_desc = f"الشخص الذي تراه أمامك هو: {current_face['face_id']}"
        else:
            current_person_desc = "يوجد شخص أمام الكاميرا ولكن لم يتم التعرف على هويته"

    faces_info = {
        "currently_detected": current_face.get("detected", False),
        "is_recent": current_face.get("is_recent", False),
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

    grounded_system_prompt = f"""أنت توأم رقمي مصري (روبوت Nebula).
تتحدث باللهجة المصرية العامية ({p_info['dialect']}) مع خلط كلمات إنجليزية شائعة كما يفعل المصريون.
ردودك قصيرة وموجزة (جملة أو اتنين)، ذات طابع حيوي، ودود، وسريع البديهة.
إذا كان الرد يتضمن إشارة لمشاعر أو حركة جسدية، ضع وسماً في نهاية الجملة مثل: [happy] [sad] [surprised] [like] [wave].

سياق ومعلومات النظام الحية المتاحة لك الآن للإجابة بدقة:
1. الشخصية النشطة (Personality):
   - الاسم: {p_info['name']}
   - التوجيه الخاص: {p_info['system_prompt']}

2. الرؤية والوجوه (Faces & Vision):
   - من تراه أمامك الآن: {current_person_desc}
   - قائمة الوجوه المسجلة في النظام: {registered_str}

3. الصوت المستنسخ (Voice Clone):
   - العينة الصوتية المستخدمة: {voice_str}
   - محرك تحويل النص لصوت: {voice_info['tts_provider']}

4. التشخيص وحالة الأجهزة (Diagnostics & Hardware):
   - تطبيق الهاتف (الشاشة والعيون): {phone_str}
   - غرفة التحكم (Desktop): {desk_str}
   - المتحكم الحركي والجسد (ESP32): {esp_str}
"""
    if memories:
        mem_bullets = "\n".join(f"- {m}" for m in memories)
        grounded_system_prompt += f"\n5. ذكريات سابقة مرتبطة بالحديث (Memories / RAG):\n{mem_bullets}\n"

    grounding_data = GroundingInfo(
        personality=p_info,
        faces=faces_info,
        voice_clone=voice_info,
        diagnostics=diag_info,
        memories=memories,
    )

    return grounded_system_prompt, memories, grounding_data, target_p.id


# ── Chat Endpoints ───────────────────────────────────────────────────────────

@router.post("/chat", summary="Chat with the LLM via REST API", response_model=ChatResponse)
async def chat_with_llm(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(_get_auth_user),
):
    """
    Direct REST API endpoint to chat with the LLM.
    Grounded in real-time on:
    1. Active Personality & dialect.
    2. RAG memories.
    3. Vision / Faces (seen faces & registered face profiles).
    4. Voice Clone state.
    5. Diagnostics & hardware connection states (Phone, Desktop, ESP32).
    """
    if not body.message.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message cannot be empty")

    session_id = body.session_id or str(uuid.uuid4())

    # Build full grounding context
    system_prompt, memories, grounding, active_pid = await build_grounding_context(
        db=db,
        personality_id=body.personality_id,
        message=body.message,
    )

    # Find or create Conversation
    conv_res = await db.execute(
        select(Conversation)
        .where(Conversation.session_id == session_id)
        .order_by(Conversation.started_at.desc())
        .limit(1)
    )
    conv = conv_res.scalar_one_or_none()
    if not conv:
        conv = Conversation(personality_id=active_pid, session_id=session_id)
        db.add(conv)
        await db.flush()

    # Fetch recent conversation history
    msg_res = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(6)
    )
    recent_msgs = list(reversed(msg_res.scalars().all()))
    history = [{"role": m.role, "content": m.content} for m in recent_msgs]

    # Load LLM provider and generate response
    llm = get_llm_provider(settings.LLM_PROVIDER)
    t_start = time.perf_counter()

    if body.stream:
        # Streaming response
        async def event_generator():
            full_content = []
            async for token in llm.generate_stream(
                body.message,
                context=memories,
                system_prompt=system_prompt,
                history=history,
            ):
                full_content.append(token)
                yield token

            # Save to DB after streaming completes
            full_str = "".join(full_content)
            llm_ms = (time.perf_counter() - t_start) * 1000
            emotion = _extract_emotion(full_str)
            user_msg = Message(
                conversation_id=conv.id,
                role="user",
                content=body.message,
            )
            robot_msg = Message(
                conversation_id=conv.id,
                role="robot",
                content=full_str,
                llm_latency_ms=round(llm_ms, 2),
                total_latency_ms=round(llm_ms, 2),
                emotion=emotion,
            )
            db.add_all([user_msg, robot_msg])
            await db.commit()

        return StreamingResponse(event_generator(), media_type="text/plain; charset=utf-8")

    # Non-streaming response
    reply = await llm.generate(
        body.message,
        context=memories,
        system_prompt=system_prompt,
        history=history,
    )
    llm_ms = (time.perf_counter() - t_start) * 1000
    cleaned_reply = clean_text_for_tts(reply)
    emotion = _extract_emotion(reply)

    # Save messages to DB
    user_msg = Message(
        conversation_id=conv.id,
        role="user",
        content=body.message,
    )
    robot_msg = Message(
        conversation_id=conv.id,
        role="robot",
        content=reply,
        llm_latency_ms=round(llm_ms, 2),
        total_latency_ms=round(llm_ms, 2),
        emotion=emotion,
    )
    db.add_all([user_msg, robot_msg])
    await db.commit()

    return ChatResponse(
        reply=reply,
        cleaned_reply=cleaned_reply,
        session_id=session_id,
        conversation_id=conv.id,
        emotion=emotion,
        llm_latency_ms=round(llm_ms, 2),
        memories_used=memories,
        grounding=grounding,
    )


# ── Read-only Endpoints ──────────────────────────────────────────────────────

@router.get("/", summary="List conversation sessions")
async def list_conversations(
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(_get_auth_user),
):
    r = await db.execute(select(Conversation).order_by(Conversation.started_at.desc()).limit(limit))
    return {"conversations": [_c(c) for c in r.scalars()]}


@router.get("/{cid}/messages", summary="Get messages for a conversation")
async def get_messages(
    cid: int,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(_get_auth_user),
):
    r = await db.execute(select(Message).where(Message.conversation_id == cid).order_by(Message.created_at))
    return {"messages": [_msg(m) for m in r.scalars()]}


def _c(c: Conversation) -> dict:
    return {
        "id": c.id, "session_id": c.session_id,
        "started_at": c.started_at.isoformat(),
        "ended_at": c.ended_at.isoformat() if c.ended_at else None,
        "message_count": len(c.messages),
    }


def _msg(m: Message) -> dict:
    return {
        "id": m.id, "role": m.role, "content": m.content,
        "emotion": m.emotion,
        "stt_ms": m.stt_latency_ms, "llm_ms": m.llm_latency_ms,
        "tts_ms": m.tts_latency_ms, "total_ms": m.total_latency_ms,
        "created_at": m.created_at.isoformat(),
    }
