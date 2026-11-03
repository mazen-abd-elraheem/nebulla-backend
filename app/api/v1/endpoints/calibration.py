"""Servo calibration endpoints (doc §5.2 calibration screen)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_optional_user
from app.db.session import get_db
from app.models.calibration import ServoCalibration

router = APIRouter()


class CalibrationUpdate(BaseModel):
    label: str | None = None
    min_angle: float | None = None
    max_angle: float | None = None
    home_angle: float | None = None


@router.get("/", summary="List all servo calibrations")
async def list_calibrations(db: AsyncSession = Depends(get_db), _u=Depends(get_optional_user)):
    r = await db.execute(select(ServoCalibration).order_by(ServoCalibration.servo_id))
    return {"calibrations": [_c(c) for c in r.scalars()]}


@router.put("/{servo_id}", summary="Create or update a servo calibration")
async def upsert_calibration(
    servo_id: int,
    body: CalibrationUpdate,
    db: AsyncSession = Depends(get_db),
    _u=Depends(get_optional_user),
):
    cal = await db.get(ServoCalibration, servo_id)
    if not cal:
        cal = ServoCalibration(servo_id=servo_id, label=body.label or f"servo_{servo_id}")
        db.add(cal)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(cal, k, v)
    await db.flush()
    await db.commit()
    return _c(cal)


@router.post("/reset", summary="Reset all servos to home position via ESP32")
async def reset_to_home(_u=Depends(get_optional_user)):
    """Send every servo to its home angle."""
    from app.websocket.manager import manager
    if manager.esp_connected:
        for sid in range(12):
            cmd = {"t": "joint", "id": sid, "deg": 90, "ms": 800}
            await manager.send_to_esp(cmd)
    return {"message": "Home command sent to all servos", "esp_connected": manager.esp_connected}


def _c(c: ServoCalibration) -> dict:
    return {
        "servo_id": c.servo_id, "label": c.label,
        "min_angle": c.min_angle, "max_angle": c.max_angle,
        "home_angle": c.home_angle,
    }
