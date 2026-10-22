"""
Devices REST endpoints
GET    /devices          — list all known devices + connection status
GET    /devices/{id}     — device detail
DELETE /devices/{id}     — remove a device record
GET    /devices/status   — live connection summary (phone, ESP32, desktops)
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user
from app.db.session import get_db
from app.models.device import Device
from app.websocket.manager import manager

router = APIRouter()


@router.get("/status", summary="Live connection status of all channels")
async def connection_status(_user: str = Depends(get_current_user)):
    st = manager.status()
    return {"channels": st, **st}


@router.get("/", summary="List all registered devices")
async def list_devices(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    result = await db.execute(select(Device).order_by(Device.created_at.desc()))
    devices = result.scalars().all()
    return {"devices": [_device_dict(d) for d in devices]}


@router.get("/{device_id}", summary="Get a specific device")
async def get_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    dev = await db.get(Device, device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return _device_dict(dev)


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(
    device_id: int,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    dev = await db.get(Device, device_id)
    if not dev:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    await db.delete(dev)


def _device_dict(d: Device) -> dict:
    return {
        "id": d.id,
        "device_id": d.device_id,
        "device_type": d.device_type,
        "name": d.name,
        "is_connected": d.is_connected,
        "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        "battery_voltage": d.battery_voltage,
        "distance_cm": d.distance_cm,
        "last_error": d.last_error,
    }
