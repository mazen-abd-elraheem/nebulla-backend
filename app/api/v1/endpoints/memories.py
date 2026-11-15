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
            if pid in ("", "string", "null", "none", None):
                data["personality_id"] = None
            elif isinstance(pid, (int, str)):
                try:
                    data["personality_id"] = int(pid)
                except ValueError:
                    data["personality_id"] = None

            # Sanitize importance
            imp = data.get("importance")
            if imp in ("", "string", "null", "none", None):
                data["importance"] = 5
            elif isinstance(imp, (int, str)):
                try:
                    data["importance"] = int(imp)
                except ValueError:
                    data["importance"] = 5
        return data


class MemoryUpdate(BaseModel):
    content: Optional[str] = Field(default=None, description="Updated factual text")
    text: Optional[str] = Field(default=None, description="Alias for content")
    memory: Optional[str] = Field(default=None, description="Alias for content")
    personality_id: int | str | None = Field(default=None, description="Personality ID")
    source: Optional[str] = Field(default=None, description="Source of memory")
    importance: int | str | None = Field(default=None, description="Importance score 1-10")

    @model_validator(mode="before")
    @classmethod
    def sanitize(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"content": data}
        if isinstance(data, dict):
            content = data.get("content")
            if content is None:
                content = data.get("text") or data.get("memory") or data.get("fact")
            if content is not None:
                data["content"] = str(content).strip()

            pid = data.get("personality_id")
            if pid in ("", "string", "null", "none", None):
                data["personality_id"] = None
            elif isinstance(pid, (int, str)):
                try:
                    data["personality_id"] = int(pid)
                except ValueError:
                    data["personality_id"] = None

            imp = data.get("importance")
            if imp in ("", "string", "null", "none", None):
                data["importance"] = None
            elif isinstance(imp, (int, str)):
                try:
                    data["importance"] = int(imp)
                except ValueError:
                    data["importance"] = None
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
            if pid in ("", "string", "null", "none", None):
                data["personality_id"] = None
            elif isinstance(pid, (int, str)):
                try:
                    data["personality_id"] = int(pid)
                except ValueError:
                    data["personality_id"] = None

            top_k = data.get("top_k")
            if top_k in ("", "string", "null", "none", None):
                data["top_k"] = 5
            elif isinstance(top_k, (int, str)):
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
    if personality_id is not None:
        stmt = stmt.where(Memory.personality_id == personality_id)
    r = await db.execute(stmt)
    return {"memories": [_m(m) for m in r.scalars()]}


@router.post("/", status_code=201, summary="Add a memory")
async def add_memory(
    body: Optional[MemoryCreate] = None,
    content: Optional[str] = Query(None, description="Content if provided as query param"),
    personality_id: Optional[int] = Query(None, description="Personality ID query param"),
    person_name: Optional[str] = Query(None, description="Optional personality/person name to bind memory to"),
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
    if pid is None and personality_id is not None:
        pid = personality_id
    if importance is not None:
        imp = importance

    if not actual_content:
        raise HTTPException(
            status_code=400,
            detail="نص المعلومة مينفعش يكون فاضي، اكتب المعلومة اللي عايز تحفظها.",
        )

    # Dynamic Personality resolution: if pid is None, check person_name first, else active personality
    if pid is None and person_name and person_name.strip():
        clean_p = person_name.strip()
        p_res = await db.execute(
            select(Personality.id).where(Personality.name.ilike(f"%{clean_p}%")).limit(1)
        )
        matched_id = p_res.scalar_one_or_none()
        if matched_id is not None:
            pid = matched_id

    if pid is None:
        res = await db.execute(select(Personality.id).where(Personality.is_active == True).limit(1))  # noqa: E712
        active_id = res.scalar_one_or_none()
        pid = active_id if active_id is not None else 1

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
                    db=db,
                )
                created_ids.append(mid)
        return {
            "ids": created_ids,
            "count": len(created_ids),
            "personality_id": pid,
            "message": f"حفظنا {len(created_ids)} معلومة في الذاكرة وعملنالهم التضمين بنجاح.",
        }

    mid = await _rag.add_memory(
        content=actual_content,
        personality_id=pid,
        source=src,
        importance=imp,
        db=db,
    )
    return {
        "id": mid,
        "content": actual_content,
        "personality_id": pid,
        "message": "المعلومة اتحفظت واتسجلت في عقل الروبوت بنجاح.",
    }


@router.put("/{mid}", summary="Update a memory")
@router.patch("/{mid}", summary="Partially update a memory")
async def update_memory_endpoint(
    mid: int,
    body: Optional[MemoryUpdate] = None,
    content: Optional[str] = Query(None, description="Updated content if provided as query param"),
    personality_id: Optional[int] = Query(None, description="Personality ID query param"),
    importance: Optional[int] = Query(None, description="Importance query param"),
    source: Optional[str] = Query(None, description="Source query param"),
    db: AsyncSession = Depends(get_db),
    _u: str | None = Depends(get_optional_user),
):
    """
    Update / Replace an existing memory in both SQLite and In-Memory VectorStore.
    Re-generates vector embedding if content changed, discarding obsolete knowledge.
    """
    mem = await db.get(Memory, mid)
    if not mem:
        raise HTTPException(status_code=404, detail="المعلومة دي مش موجودة في الذاكرة.")

    actual_content = None
    pid = None
    src = None
    imp = None

    if body:
        actual_content = body.content
        pid = body.personality_id
        src = body.source
        imp = body.importance

    if actual_content is None and content:
        actual_content = content.strip()
    if pid is None and personality_id is not None:
        pid = personality_id
    if src is None and source is not None:
        src = source
    if imp is None and importance is not None:
        imp = importance

    updated_mem = await _rag.update_memory(
        memory_id=mid,
        content=actual_content,
        personality_id=pid,
        source=src,
        importance=imp,
        db=db,
    )
    if not updated_mem:
        raise HTTPException(status_code=404, detail="فشل تحديث المعلومة في الذاكرة.")

    return {
        "id": updated_mem.id,
        "content": updated_mem.content,
        "personality_id": updated_mem.personality_id,
        "source": updated_mem.source,
        "importance": updated_mem.importance,
        "message": "تم تحديث المعلومة واستبدال التضمين القديم في الذاكرة بنجاح.",
    }


class MemoryForgetRequest(BaseModel):
    query: str = Field(..., description="Query or fact keywords of the memory to forget/delete")
    personality_id: int | str | None = Field(default=None, description="Optional personality ID filter")

    @model_validator(mode="before")
    @classmethod
    def sanitize(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"query": data}
        if isinstance(data, dict):
            pid = data.get("personality_id")
            if pid in ("", "string", "null", "none", None):
                data["personality_id"] = None
            elif isinstance(pid, (int, str)):
                try:
                    data["personality_id"] = int(pid)
                except ValueError:
                    data["personality_id"] = None
        return data


@router.delete("/{mid}", summary="Delete a memory by ID")
async def delete_memory(
    mid: int,
    db: AsyncSession = Depends(get_db),
    _u: str | None = Depends(get_optional_user),
):
    m = await db.get(Memory, mid)
    if not m:
        raise HTTPException(status_code=404, detail="المعلومة دي مش موجودة في الذاكرة.")
    deleted_content = m.content
    deleted_pid = m.personality_id
    await db.delete(m)
    await db.commit()
    await _rag.delete_memory(mid, db=db)
    return {
        "status": "success",
        "deleted_id": mid,
        "personality_id": deleted_pid,
        "content": deleted_content,
        "message": f"تم مسح المعلومة رقم {mid} ('{deleted_content}') بنجاح من الذاكرة وقاعدة البيانات.",
    }


@router.post("/forget", summary="Forget/delete memories matching a keyword or phrase")
async def forget_memory_endpoint(
    body: MemoryForgetRequest,
    db: AsyncSession = Depends(get_db),
    _u: str | None = Depends(get_optional_user),
):
    """
    Search and delete memories matching a fact or query (e.g. 'الكتاب في الصالة').
    Clears from SQLite and In-Memory VectorStore.
    """
    stmt = select(Memory)
    if body.personality_id is not None:
        stmt = stmt.where((Memory.personality_id == body.personality_id) | (Memory.personality_id.is_(None)))
    res = await db.execute(stmt)
    all_mems = res.scalars().all()

    clean_q = body.query.strip()
    deleted_items = []
    for m in all_mems:
        if _rag._is_conflicting_fact(clean_q, m.content) or clean_q.lower() in m.content.lower():
            deleted_items.append({"id": m.id, "content": m.content, "personality_id": m.personality_id})
            await db.delete(m)
            _rag._vstore.delete(m.id)

    if deleted_items:
        await db.commit()
        with RAGService._cache_lock:
            RAGService._shared_cache.clear()

    return {
        "status": "success",
        "query": clean_q,
        "deleted_count": len(deleted_items),
        "deleted_memories": deleted_items,
        "message": f"تم نسيان ومسح {len(deleted_items)} معلومة من الذاكرة بنجاح." if deleted_items else "لم يتم العثور على معلومات تطابق هذا النص لمسحها.",
    }


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
        "id": m.id,
        "personality_id": m.personality_id,
        "content": m.content,
        "source": m.source,
        "importance": m.importance,
        "created_at": m.created_at.isoformat(),
        "last_accessed": m.last_accessed.isoformat() if m.last_accessed else None,
    }
