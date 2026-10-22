"""Conversations + messages endpoints (with RAG + LLM chat)."""

import json
from typing import AsyncIterator
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_optional_user
from app.db.session import get_db
from app.models.conversation import Conversation, Message
from app.websocket.handlers import _get_ai_pipeline

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, description="User prompt or question to the LLM")
    personality_id: int | None = Field(None, description="Optional personality ID to ground responses")
    session_id: str | None = Field(None, description="Optional conversation session ID")
    broadcast_to_clients: bool = Field(False, description="Whether to broadcast live tokens to connected desks/phones")


class ChatResponse(BaseModel):
    session_id: str
    response: str
    retrieved_memories: list[str]
    personality_id: int | None
    emotion: str
    latency: dict


@router.post("/chat", response_model=ChatResponse, summary="Chat with LLM grounded by RAG memories")
async def chat_with_rag(
    body: ChatRequest,
    _u=Depends(get_optional_user),
):
    """
    Direct text chat endpoint linking RAG with LLM:
    1. Retrieves top relevant memories from the DB via semantic/lexical RAG.
    2. Builds system prompt with personality persona and RAG context.
    3. Streams/generates response using selected LLM provider (Ollama / OpenAI / Claude).
    4. Records turn and latency telemetry to conversations/messages table.
    """
    pipeline = _get_ai_pipeline()
    result = await pipeline.process_text(
        text=body.message,
        personality_id=body.personality_id,
        session_id=body.session_id,
        broadcast_to_clients=body.broadcast_to_clients,
    )
    return result


@router.post("/chat/stream", summary="Stream chat tokens from LLM with RAG grounding (SSE)")
async def chat_stream_with_rag(
    body: ChatRequest,
    _u=Depends(get_optional_user),
):
    """
    Server-Sent Events (SSE) streaming endpoint:
    Streams tokens as they are produced by the LLM with RAG context.
    """
    pipeline = _get_ai_pipeline()

    async def event_generator() -> AsyncIterator[str]:
        async for item in pipeline.process_text_stream(
            text=body.message,
            personality_id=body.personality_id,
            session_id=body.session_id,
        ):
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/", summary="List conversation sessions")
async def list_conversations(
    limit: int = Query(20, le=100),
    db: AsyncSession = Depends(get_db),
    _u=Depends(get_current_user),
):
    r = await db.execute(select(Conversation).order_by(Conversation.started_at.desc()).limit(limit))
    return {"conversations": [_c(c) for c in r.scalars()]}


@router.get("/{cid}/messages", summary="Get messages for a conversation")
async def get_messages(
    cid: int,
    db: AsyncSession = Depends(get_db),
    _u=Depends(get_current_user),
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
