"""Signals CRUD + fire endpoint (doc §5.2 signal studio)."""

import json
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.session import get_db
from app.models.signal import Signal
from app.services.motion.signal_planner import SignalPlanner
from app.services.motion.motion_guard import MotionGuard
from app.websocket.manager import manager

router = APIRouter()
_planner = SignalPlanner()
_guard = MotionGuard()


class SignalCreate(BaseModel):
    name: str
    description: str | None = None
    joint_commands_json: str = "[]"
    emotion_tag: str | None = None


@router.get("/", summary="List all signals")
async def list_signals(db: AsyncSession = Depends(get_db), _u=Depends(get_current_user)):
    r = await db.execute(select(Signal).order_by(Signal.name))
    return {"signals": [_s(s) for s in r.scalars()]}


@router.post("/", status_code=201, summary="Create a signal")
async def create_signal(body: SignalCreate, db: AsyncSession = Depends(get_db), _u=Depends(get_current_user)):
    sig = Signal(**body.model_dump())
    db.add(sig)
    await db.flush()
    await db.refresh(sig)
    return _s(sig)


@router.post("/{name}/fire", summary="Fire a named signal to the robot")
async def fire_signal(name: str, _u=Depends(get_current_user)):
    """Immediately send the named gesture to ESP32 (used from signal studio)."""
    commands = await _planner.resolve(name)
    if not commands:
        raise HTTPException(status_code=404, detail=f"Signal {name!r} not found")
    for cmd in commands:
        validated = _guard.validate_joint(cmd)
        if validated:
            await manager.send_to_esp(validated.model_dump())
    return {"fired": name, "commands_sent": len(commands)}


@router.delete("/{sid}", status_code=204)
async def delete_signal(sid: int, db: AsyncSession = Depends(get_db), _u=Depends(get_current_user)):
    s = await db.get(Signal, sid)
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(s)


def _s(s: Signal) -> dict:
    return {
        "id": s.id, "name": s.name, "description": s.description,
        "joint_commands": json.loads(s.joint_commands_json),
        "emotion_tag": s.emotion_tag,
    }
