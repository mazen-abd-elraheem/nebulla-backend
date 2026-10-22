"""Memories CRUD + search endpoints (RAG)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.session import get_db
from app.models.memory import Memory
from app.services.memory.rag_service import RAGService

router = APIRouter()
_rag = RAGService()


class MemoryCreate(BaseModel):
    content: str
    personality_id: int | None = None
    source: str = "manual"
    importance: int = 5


@router.get("/", summary="List memories")
async def list_memories(
    personality_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _u=Depends(get_current_user),
):
    stmt = select(Memory).order_by(Memory.created_at.desc())
    if personality_id:
        stmt = stmt.where(Memory.personality_id == personality_id)
    r = await db.execute(stmt)
    return {"memories": [_m(m) for m in r.scalars()]}


@router.post("/", status_code=201, summary="Add a memory")
async def add_memory(body: MemoryCreate, _u=Depends(get_current_user)):
    mid = await _rag.add_memory(
        content=body.content,
        personality_id=body.personality_id,
        source=body.source,
        importance=body.importance,
    )
    return {"id": mid, "message": "Memory added and embedded"}


@router.delete("/{mid}", status_code=204, summary="Delete a memory")
async def delete_memory(mid: int, db: AsyncSession = Depends(get_db), _u=Depends(get_current_user)):
    m = await db.get(Memory, mid)
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(m)


@router.get("/search", summary="Semantic search memories")
async def search_memories(
    q: str = Query(..., description="Search query"),
    personality_id: int | None = Query(None),
    top_k: int = Query(5, ge=1, le=20),
    detailed: bool = Query(False, description="Whether to include similarity score and metadata"),
    _u=Depends(get_current_user),
):
    if detailed:
        results = await _rag.retrieve_detailed(q, personality_id=personality_id, top_k=top_k)
    else:
        results = await _rag.retrieve(q, personality_id=personality_id, top_k=top_k)
    return {"query": q, "results": results}


def _m(m: Memory) -> dict:
    return {
        "id": m.id, "content": m.content, "source": m.source,
        "importance": m.importance,
        "created_at": m.created_at.isoformat(),
        "last_accessed": m.last_accessed.isoformat() if m.last_accessed else None,
    }
