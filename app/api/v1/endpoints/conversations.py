"""Conversations + messages read-only endpoints (live display in control room)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.session import get_db
from app.models.conversation import Conversation, Message

router = APIRouter()


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
