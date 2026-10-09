"""Personalities CRUD endpoints (doc §5.2 personality & memory screen)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.session import get_db
from app.models.personality import Personality

router = APIRouter()


class PersonalityCreate(BaseModel):
    name: str
    description: str | None = None
    system_prompt: str = ""
    dialect: str = "cairo"
    language_mix: str = "ar_en"
    voice_sample_path: str | None = None


class PersonalityUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    system_prompt: str | None = None
    dialect: str | None = None
    language_mix: str | None = None
    voice_sample_path: str | None = None
    is_active: bool | None = None


@router.get("/", summary="List all personalities")
async def list_personalities(db: AsyncSession = Depends(get_db), _u=Depends(get_current_user)):
    r = await db.execute(select(Personality).order_by(Personality.id))
    return {"personalities": [_p(p) for p in r.scalars()]}


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a personality")
async def create_personality(body: PersonalityCreate, db: AsyncSession = Depends(get_db), _u=Depends(get_current_user)):
    p = Personality(**body.model_dump())
    db.add(p)
    await db.flush()
    await db.refresh(p)
    return _p(p)


@router.get("/{pid}", summary="Get personality by ID")
async def get_personality(pid: int, db: AsyncSession = Depends(get_db), _u=Depends(get_current_user)):
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return _p(p)


@router.patch("/{pid}", summary="Update personality")
async def update_personality(pid: int, body: PersonalityUpdate, db: AsyncSession = Depends(get_db), _u=Depends(get_current_user)):
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    await db.flush()
    return _p(p)


@router.delete("/{pid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personality(pid: int, db: AsyncSession = Depends(get_db), _u=Depends(get_current_user)):
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(p)


@router.post("/{pid}/activate", summary="Set this personality as the active one")
async def activate_personality(pid: int, db: AsyncSession = Depends(get_db), _u=Depends(get_current_user)):
    # Deactivate all
    all_p = (await db.execute(select(Personality))).scalars().all()
    for p in all_p:
        p.is_active = False
    # Activate target
    target = await db.get(Personality, pid)
    if not target:
        raise HTTPException(status_code=404, detail="Not found")
    target.is_active = True
    await db.flush()
    return {"active_personality_id": pid}


def _p(p: Personality) -> dict:
    return {
        "id": p.id, "name": p.name, "description": p.description,
        "system_prompt": p.system_prompt, "dialect": p.dialect,
        "language_mix": p.language_mix, "voice_sample_path": p.voice_sample_path,
        "is_active": p.is_active,
    }
