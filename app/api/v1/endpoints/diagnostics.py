"""
Diagnostics endpoints — device hardware test panel (doc §5.2 "فحص الأجهزة").

Allows the desktop control room to:
  • Ping each servo individually
  • Test LED states
  • Fire the ultrasonic sensor
  • Read battery voltage
  • Check WebSocket channel health
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.jwt import get_current_user
from app.websocket.manager import manager

router = APIRouter()


class ServoTestRequest(BaseModel):
    servo_id: int
    angle: float = 90.0
    speed_ms: int = 500


class MotorTestRequest(BaseModel):
    left: int = 128    # half speed
    right: int = 128
    duration_ms: int = 1000


class LEDRequest(BaseModel):
    state: str = "on"   # "on" | "off" | "blink_slow" | "blink_fast" | "blink_double"


@router.get("/status", summary="Live backend + channel status")
async def full_status(_u=Depends(get_current_user)):
    """Returns connection state of all three WS channels."""
    return {
        "channels": manager.status(),
        "backend": "ok",
    }


@router.post("/servo/test", summary="Move a single servo to a test angle")
async def test_servo(body: ServoTestRequest, _u=Depends(get_current_user)):
    """Send a one-off servo command for hardware verification (doc §5.2)."""
    if not manager.esp_connected:
        raise HTTPException(status_code=503, detail="ESP32 not connected")
    cmd = {"t": "joint", "id": body.servo_id, "deg": body.angle, "ms": body.speed_ms}
    await manager.send_to_esp(cmd)
    return {"sent": cmd}


@router.post("/servo/home-all", summary="Send all servos to 90° (home position)")
async def home_all_servos(_u=Depends(get_current_user)):
    if not manager.esp_connected:
        raise HTTPException(status_code=503, detail="ESP32 not connected")
    for sid in range(12):
        await manager.send_to_esp({"t": "joint", "id": sid, "deg": 90, "ms": 800})
    return {"message": "All 12 servos sent to home (90°)"}


@router.post("/motor/test", summary="Run motors briefly for wheel test")
async def test_motors(body: MotorTestRequest, _u=Depends(get_current_user)):
    if not manager.esp_connected:
        raise HTTPException(status_code=503, detail="ESP32 not connected")
    await manager.send_to_esp({"t": "motor", "left": body.left, "right": body.right})
    import asyncio
    await asyncio.sleep(body.duration_ms / 1000)
    await manager.send_to_esp({"t": "motor", "left": 0, "right": 0})
    return {"message": f"Motor test done ({body.duration_ms}ms)"}


@router.post("/led", summary="Control the two blue LED indicators (doc §5.1)")
async def set_led(body: LEDRequest, _u=Depends(get_current_user)):
    """
    LED states map (doc §5.1 state table):
      on           → robot is active
      off          → standby
      blink_slow   → thinking / processing
      blink_fast   → emergency stop
      blink_double → low battery
    """
    if not manager.esp_connected:
        raise HTTPException(status_code=503, detail="ESP32 not connected")
    await manager.send_to_esp({"t": "led", "state": body.state})
    return {"led_state": body.state}


@router.get("/sensor/distance", summary="Request a distance reading from HC-SR04")
async def request_distance(_u=Depends(get_current_user)):
    """Tell ESP32 to send back the current ultrasonic sensor reading."""
    if not manager.esp_connected:
        raise HTTPException(status_code=503, detail="ESP32 not connected")
    await manager.send_to_esp({"t": "cmd", "action": "read_distance"})
    return {"message": "Distance read request sent — check telemetry stream"}


@router.post("/emergency-stop", summary="🚨 Immediate full stop of all movement")
async def emergency_stop(_u=Depends(get_current_user)):
    """
    Stops all motors and servos immediately.
    Safe to call at any time — always accepted by ESP32 regardless of state.
    """
    await manager.send_to_esp({"t": "stop"})
    await manager.send_to_phone({"t": "eyes", "mood": "alert"})
    await manager.broadcast_to_desks({"t": "event", "event": "emergency_stop"})
    return {"message": "Emergency stop sent to all channels"}
