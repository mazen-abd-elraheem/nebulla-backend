"""
Personalities CRUD endpoints — user-scoped with global system defaults.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user_model, get_optional_user_model
from app.db.session import get_db
from app.models.personality import Personality
from app.models.user import User

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


@router.get("/", summary="List all accessible personalities (user-owned + shared defaults)")
async def list_personalities(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user_model),
):
    """
    Returns global system default personalities (user_id is None)
    plus custom personalities created by the authenticated user.
    """
    if current_user:
        stmt = (
            select(Personality)
            .where(or_(Personality.user_id == None, Personality.user_id == current_user.id))  # noqa: E711
            .order_by(Personality.id)
        )
    else:
        stmt = (
            select(Personality)
            .where(Personality.user_id == None)  # noqa: E711
            .order_by(Personality.id)
        )

    r = await db.execute(stmt)
    return {"personalities": [_p(p) for p in r.scalars()]}


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a user-owned personality")
async def create_personality(
    body: PersonalityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_model),
):
    """
    Create a new robot personality profile tied to the authenticated user.
    """
    data = body.model_dump()
    data["user_id"] = current_user.id

    p = Personality(**data)
    db.add(p)
    try:
        await db.flush()
        await db.refresh(p)
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Personality could not be created due to database constraint: {exc.orig}",
        )
    return _p(p)


@router.get("/{pid}", summary="Get personality by ID")
async def get_personality(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user_model),
):
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Personality not found")

    # If personality is private to a user, enforce ownership
    if p.user_id is not None:
        if not current_user or current_user.id != p.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this personality.",
            )

    return _p(p)


@router.patch("/{pid}", summary="Update a user-owned personality")
async def update_personality(
    pid: int,
    body: PersonalityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_model),
):
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Personality not found")

    if p.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot modify a global system default personality.",
        )

    if p.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own personalities.",
        )

    for k, v in body.model_dump(exclude_none=True).items():
        setattr(p, k, v)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Personality update violates database constraint: {exc.orig}",
        )
    return _p(p)


@router.delete("/{pid}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_personality(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user_model),
):
    p = await db.get(Personality, pid)
    if not p:
        raise HTTPException(status_code=404, detail="Personality not found")

    if p.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete a global system default personality.",
        )

    if p.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own personalities.",
        )

    await db.delete(p)


@router.post("/{pid}/activate", summary="Set this personality as the active one")
async def activate_personality(
    pid: int,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_optional_user_model),
):
    target = await db.get(Personality, pid)
    if not target:
        raise HTTPException(status_code=404, detail="Personality not found")

    if target.user_id is not None and current_user and target.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot activate another user's private personality.",
        )

    # Deactivate all accessible personalities
    if current_user:
        stmt = select(Personality).where(
            or_(Personality.user_id == None, Personality.user_id == current_user.id)  # noqa: E711
        )
    else:
        stmt = select(Personality)

    all_p = (await db.execute(stmt)).scalars().all()
    for p in all_p:
        p.is_active = False

    target.is_active = True
    await db.flush()
    return {"active_personality_id": pid}


def _p(p: Personality) -> dict:
    return {
        "id": p.id,
        "user_id": p.user_id,
        "name": p.name,
        "description": p.description,
        "system_prompt": p.system_prompt,
        "dialect": p.dialect,
        "language_mix": p.language_mix,
        "voice_sample_path": p.voice_sample_path,
        "is_active": p.is_active,
    }
