"""Conversations + messages endpoints with interactive LLM chat and full system grounding."""

import time
import uuid
from typing import Optional, List, Dict, Any, Tuple

from fastapi import APIRouter, Depends, Query, HTTPException, status, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from pathlib import Path
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
    message: str = Field(..., description="Text message to send to the LLM")
    session_id: Optional[str] = Field(None, description="Optional session UUID for multi-turn conversation tracking")
    personality_id: Optional[int] = Field(None, description="Specific personality ID to use (defaults to active personality)")
    stream: bool = Field(False, description="Whether to stream tokens via chunked transfer")
    provider: Optional[str] = Field(None, description="Override LLM provider ('local', 'nile', 'huggingface', 'openai', etc.)")
    model: Optional[str] = Field(None, description="Override model name (e.g. 'MBZUAI-Paris/Nile-Chat-3x4B-A6B' or 'nebula-rag')")

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "مشروع تخرج مازن إيه؟",
                "model": "nebula-rag",
                "stream": False,
            }
        }
    }


from app.services.ai.context_builder import build_grounding_context, GroundingInfo


class ChatResponse(BaseModel):
    reply: str
    cleaned_reply: str
    session_id: str
    conversation_id: int
    emotion: str
    llm_latency_ms: float
    llm_model: str = Field(..., description="Active LLM model used")
    llm_provider: str = Field(..., description="Active LLM provider used")
    memories_used: List[str]
    grounding: Optional[GroundingInfo] = None

    # Backward compatibility fields
    response: Optional[str] = None
    retrieved_memories: Optional[List[str]] = None
    personality_id: Optional[int] = None
    latency: Optional[dict] = None


# ── Authentication Helper ────────────────────────────────────────────────────

async def _get_auth_user(
    user: Optional[str] = Depends(get_optional_user),
) -> str:
    """Allow chat without strict auth if unauthenticated or in DEBUG mode."""
    if user:
        return user
    return "guest_user"



# ── Chat Endpoints ───────────────────────────────────────────────────────────

@router.get("/playground", response_class=HTMLResponse, summary="Interactive Web Chat Playground")
async def chat_playground():
    """Interactive visual web playground to chat with the LLM in real-time."""
    html_path = Path(__file__).parents[3] / "templates" / "chat_ui.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@router.post("/chat", summary="Chat with the LLM via REST API", response_model=ChatResponse)
async def chat_with_llm(
    request: Request,
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
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

    # Clean Swagger UI default placeholder values
    if body.personality_id == 0:
        body.personality_id = None
    if body.session_id == "string" or not body.session_id:
        body.session_id = str(uuid.uuid4())

    session_id = body.session_id

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
        await db.commit()
        await db.refresh(conv)

    # Fetch recent conversation history
    msg_res = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.desc(), Message.id.desc())
        .limit(6)
    )
    recent_msgs = list(reversed(msg_res.scalars().all()))
    history = [{"role": m.role, "content": m.content} for m in recent_msgs]
    conv_id = conv.id

    # Commit read transaction to release all SQLite locks before LLM generation
    await db.commit()

    # Load LLM provider and generate response
    target_provider = body.provider or settings.LLM_PROVIDER
    if body.model and ("nile" in body.model.lower() or "mbzuai" in body.model.lower()):
        if not body.provider:
            target_provider = "huggingface"
    llm = get_llm_provider(target_provider)
    if body.model:
        if hasattr(llm, "model_name"):
            llm.model_name = body.model
        if hasattr(llm, "model"):
            llm.model = body.model
    t_start = time.perf_counter()

    # If requested by Swagger UI (accept: application/json), always return non-streaming JSON
    # Swagger UI cannot parse raw streaming text under JSON response models.
    accept_hdr = request.headers.get("accept", "")
    force_json = "application/json" in accept_hdr and "text/event-stream" not in accept_hdr
    should_stream = body.stream and not force_json

    if should_stream:


        # Streaming response
        async def event_generator():
            full_content = []
            try:
                async for token in llm.generate_stream(
                    body.message,
                    context=memories,
                    system_prompt=system_prompt,
                    history=history,
                ):
                    full_content.append(token)
                    yield token
            except Exception as e:
                logger.error(f"Error during streamed LLM generation: {e}")
                yield f"\n[خطأ أثناء التوليد: {e}]"

            # Save to DB safely using a fresh session
            try:
                from app.db.session import AsyncSessionLocal
                async with AsyncSessionLocal() as session:
                    full_str = "".join(full_content)
                    llm_ms = (time.perf_counter() - t_start) * 1000
                    emotion = _extract_emotion(full_str)
                    user_msg = Message(
                        conversation_id=conv_id,
                        role="user",
                        content=body.message,
                    )
                    robot_msg = Message(
                        conversation_id=conv_id,
                        role="robot",
                        content=full_str,
                        llm_latency_ms=round(llm_ms, 2),
                        total_latency_ms=round(llm_ms, 2),
                        emotion=emotion,
                    )
                    session.add_all([user_msg, robot_msg])
                    await session.commit()
            except Exception as e:
                logger.error(f"Failed to persist streamed chat messages: {e}")

        import json
        import urllib.parse
        encoded_mems = urllib.parse.quote(json.dumps(memories, ensure_ascii=False))
        return StreamingResponse(
            event_generator(),
            media_type="text/plain; charset=utf-8",
            headers={"X-Memories-Used": encoded_mems},
        )

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
        conversation_id=conv_id,
        role="user",
        content=body.message,
    )
    robot_msg = Message(
        conversation_id=conv_id,
        role="assistant",
        content=reply,
        llm_latency_ms=round(llm_ms, 2),
        total_latency_ms=round(llm_ms, 2),
        emotion=emotion,
    )
    db.add_all([user_msg, robot_msg])
    await db.commit()

    active_model_name = getattr(llm, "model", None) or getattr(llm, "model_name", None) or settings.LLM_MODEL

    return ChatResponse(
        reply=reply,
        cleaned_reply=cleaned_reply,
        session_id=session_id,
        conversation_id=conv_id,
        emotion=emotion,
        llm_latency_ms=round(llm_ms, 2),
        llm_model=str(active_model_name),
        llm_provider=str(target_provider),
        memories_used=memories,
        grounding=grounding,
        response=reply,
        retrieved_memories=memories,
        personality_id=active_pid,
        latency={"llm_ms": round(llm_ms, 2)},
    )


@router.post("/chat/stream", summary="Stream chat tokens from LLM with RAG grounding (SSE)")
async def chat_stream(
    body: ChatRequest,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    system_prompt, memories, grounding, active_pid = await build_grounding_context(
        db=db,
        personality_id=body.personality_id,
        message=body.message,
    )
    target_provider = body.provider or settings.LLM_PROVIDER
    llm = get_llm_provider(target_provider)

    async def event_generator():
        import json
        yield f"data: {json.dumps({'type': 'context', 'memories': memories}, ensure_ascii=False)}\n\n"
        try:
            async for token in llm.generate_stream(
                body.message,
                context=memories,
                system_prompt=system_prompt,
            ):
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ── Read-only Endpoints ──────────────────────────────────────────────────────

@router.get("/", summary="List conversation sessions")
async def list_conversations(
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    r = await db.execute(select(Conversation).order_by(Conversation.started_at.desc()).limit(limit))
    return {"conversations": [_c(c) for c in r.scalars()]}


@router.get("/{cid}/messages", summary="Get messages for a conversation")
async def get_messages(
    cid: int,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
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
