"""Memories CRUD + search endpoints (RAG)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_optional_user
from app.core.config import settings
from app.db.session import get_db
from app.models.memory import Memory
from app.models.personality import Personality
from app.services.memory.rag_service import RAGService

router = APIRouter()
_rag = RAGService()


class MemoryCreate(BaseModel):
    content: str
    personality_id: int | None = None
    source: str = "manual"
    importance: int = 5


class RAGPromptRequest(BaseModel):
    query: str
    personality_id: int | None = None
    person_name: str | None = None
    top_k: int = 5
    instructions: str | None = None


@router.get("/", summary="List memories")
async def list_memories(
    personality_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _u: str | None = Depends(get_optional_user),
):
    stmt = select(Memory).order_by(Memory.created_at.desc())
    if personality_id:
        stmt = stmt.where(Memory.personality_id == personality_id)
    r = await db.execute(stmt)
    return {"memories": [_m(m) for m in r.scalars()]}


@router.post("/", status_code=201, summary="Add a memory")
async def add_memory(
    body: MemoryCreate,
    db: AsyncSession = Depends(get_db),
    _u: str | None = Depends(get_optional_user),
):
    pid = body.personality_id
    if not pid:
        res = await db.execute(select(Personality.id).where(Personality.is_active == True).limit(1))  # noqa: E712
        active_id = res.scalar_one_or_none()
        pid = active_id or 1

    mid = await _rag.add_memory(
        content=body.content,
        personality_id=pid,
        source=body.source,
        importance=body.importance,
    )
    return {"id": mid, "content": body.content, "personality_id": pid, "message": "Memory added and embedded"}


@router.delete("/{mid}", status_code=204, summary="Delete a memory")
async def delete_memory(
    mid: int,
    db: AsyncSession = Depends(get_db),
    _u: str | None = Depends(get_optional_user),
):
    m = await db.get(Memory, mid)
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(m)
    await db.commit()


@router.get("/search", summary="Semantic search memories")
async def search_memories(
    q: str = Query(..., description="Search query"),
    personality_id: int | None = Query(None),
    person_name: str | None = Query(None, description="Optional recognized person name from Vision/Face Recognition"),
    top_k: int = Query(5, ge=1, le=20),
    detailed: bool = Query(False, description="Whether to include similarity score and metadata"),
    _u: str | None = Depends(get_optional_user),
):
    if detailed:
        results = await _rag.retrieve_detailed(
            q,
            personality_id=personality_id,
            top_k=top_k,
            person_name=person_name,
        )
    else:
        results = await _rag.retrieve(
            q,
            personality_id=personality_id,
            top_k=top_k,
            person_name=person_name,
        )
    return {"query": q, "person_name": person_name, "results": results}


@router.post("/prompt", summary="Retrieve memories and compile as clean LLM Prompt (not JSON)")
async def build_rag_prompt_endpoint(
    body: RAGPromptRequest,
    db: AsyncSession = Depends(get_db),
    _u: str | None = Depends(get_optional_user),
):
    """
    RAG Prompt Builder Endpoint:
    Retrieves personalized context (grounded in Face Recognition/Person identity)
    and formats everything into a clean textual Prompt for the LLM rather than JSON,
    saving tokens and improving generation performance.
    """
    pid = body.personality_id
    target_p = None
    if pid:
        target_p = await db.get(Personality, pid)
    if not target_p:
        res = await db.execute(select(Personality).where(Personality.is_active == True).limit(1))  # noqa: E712
        target_p = res.scalar_one_or_none()

    p_id = target_p.id if target_p else 1
    instructions = body.instructions or (target_p.system_prompt if target_p else None)
    robot_name = target_p.name if target_p else "نيبولا"

    memories = await _rag.retrieve(
        query=body.query,
        personality_id=p_id,
        top_k=body.top_k,
        db=db,
        person_name=body.person_name,
    )
    prompt_str = _rag.format_rag_prompt(
        query=body.query,
        memories=memories,
        instructions=instructions,
        person_name=body.person_name,
        robot_name=robot_name,
    )
    return {
        "format": "prompt",
        "prompt": prompt_str,
        "retrieved_memories": memories,
        "personality_id": p_id,
        "person_name": body.person_name,
    }


def _m(m: Memory) -> dict:
    return {
        "id": m.id, "content": m.content, "source": m.source,
        "importance": m.importance,
        "created_at": m.created_at.isoformat(),
        "last_accessed": m.last_accessed.isoformat() if m.last_accessed else None,
    }
