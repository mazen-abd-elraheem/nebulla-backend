"""Memories CRUD + search endpoints (RAG)."""

from typing import Any, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
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
    content: Union[str, list[str]] = Field(default="", description="The factual text (or list of texts) to store in memory")
    text: Optional[Union[str, list[str]]] = Field(default=None, description="Alias for content")
    memory: Optional[Union[str, list[str]]] = Field(default=None, description="Alias for content")
    personality_id: int | str | None = Field(default=None, description="Personality ID (e.g. 1)")
    source: str = Field(default="manual", description="Source of memory (manual, conversation, etc.)")
    importance: int | str | None = Field(default=5, description="Importance score 1-10")

    @model_validator(mode="before")
    @classmethod
    def sanitize(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"content": data}
        if isinstance(data, list):
            return {"content": data}
        if isinstance(data, dict):
            # Resolve content from aliases
            content = data.get("content")
            if content is None:
                content = data.get("text") or data.get("memory") or data.get("fact") or ""
            
            if isinstance(content, list):
                data["content"] = [str(c).strip() for c in content if str(c).strip()]
            else:
                data["content"] = str(content).strip()

            # Sanitize personality_id
            pid = data.get("personality_id")
            if pid in ("", "string", "null", 0, "0", None):
                data["personality_id"] = None
            elif isinstance(pid, str):
                try:
                    data["personality_id"] = int(pid)
                except ValueError:
                    data["personality_id"] = None

            # Sanitize importance
            imp = data.get("importance")
            if imp in ("", "string", "null", None):
                data["importance"] = 5
            elif isinstance(imp, str):
                try:
                    data["importance"] = int(imp)
                except ValueError:
                    data["importance"] = 5
        return data


class RAGPromptRequest(BaseModel):
    query: str = Field(default="", description="User query to ground with RAG memories")
    personality_id: int | str | None = Field(default=None, description="Personality ID")
    person_name: Optional[str] = Field(default=None, description="Optional recognized person name")
    top_k: int | str | None = Field(default=5, description="Top K memories")
    instructions: Optional[str] = Field(default=None, description="Custom prompt instructions")

    @model_validator(mode="before")
    @classmethod
    def sanitize(cls, data: Any) -> Any:
        if isinstance(data, dict):
            pid = data.get("personality_id")
            if pid in ("", "string", "null", 0, "0", None):
                data["personality_id"] = None
            elif isinstance(pid, str):
                try:
                    data["personality_id"] = int(pid)
                except ValueError:
                    data["personality_id"] = None

            top_k = data.get("top_k")
            if top_k in ("", "string", "null", None):
                data["top_k"] = 5
            elif isinstance(top_k, str):
                try:
                    data["top_k"] = int(top_k)
                except ValueError:
                    data["top_k"] = 5
        return data


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
    body: Optional[MemoryCreate] = None,
    content: Optional[str] = Query(None, description="Content if provided as query param"),
    personality_id: Optional[int] = Query(None, description="Personality ID query param"),
    importance: Optional[int] = Query(None, description="Importance query param"),
    db: AsyncSession = Depends(get_db),
    _u: str | None = Depends(get_optional_user),
):
    actual_content: Union[str, list[str]] = ""
    pid = None
    src = "manual"
    imp = 5

    if body:
        actual_content = body.content
        pid = body.personality_id
        src = body.source or "manual"
        imp = int(body.importance or 5)

    if not actual_content and content:
        actual_content = content.strip()
        if personality_id is not None:
            pid = personality_id
        if importance is not None:
            imp = importance

    if not actual_content:
        raise HTTPException(
            status_code=400,
            detail="Memory content cannot be empty. Please provide 'content' or 'text' in the request body.",
        )

    if not pid:
        res = await db.execute(select(Personality.id).where(Personality.is_active == True).limit(1))  # noqa: E712
        active_id = res.scalar_one_or_none()
        pid = active_id or 1

    # If a list of memories was provided, add all of them
    if isinstance(actual_content, list):
        created_ids = []
        for text_item in actual_content:
            item_str = str(text_item).strip()
            if item_str:
                mid = await _rag.add_memory(
                    content=item_str,
                    personality_id=pid,
                    source=src,
                    importance=imp,
                )
                created_ids.append(mid)
        return {
            "ids": created_ids,
            "count": len(created_ids),
            "personality_id": pid,
            "message": f"Successfully added {len(created_ids)} memories and embedded them.",
        }

    mid = await _rag.add_memory(
        content=actual_content,
        personality_id=pid,
        source=src,
        importance=imp,
    )
    return {
        "id": mid,
        "content": actual_content,
        "personality_id": pid,
        "message": "Memory added and embedded successfully",
    }


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
    db: AsyncSession = Depends(get_db),
):
    if detailed:
        results = await _rag.retrieve_detailed(
            q,
            personality_id=personality_id,
            top_k=top_k,
            person_name=person_name,
            db=db,
        )
    else:
        results = await _rag.retrieve(
            q,
            personality_id=personality_id,
            top_k=top_k,
            person_name=person_name,
            db=db,
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
