"""
WebSocket Hub — FastAPI router that exposes the three WS channels.

Channels (doc §6):
  GET /ws/phone — Flutter phone app audio + camera frames
  GET /ws/desk  — Flutter desktop app (control room)
  GET /ws/esp   — ESP32 firmware telemetry + command reception

Design: ESP32 connects TO the backend (not the other way around).
If the network address changes, the ESP32 reconnects on its own.
"""

import json
import re

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.core.logger import get_logger
from app.core.security import verify_pairing_code
from app.websocket.manager import manager
from app.websocket.handlers import phone_handler, desk_handler, esp_handler
from app.services.phone_action import get_phone_action_service

logger = get_logger(__name__)
router = APIRouter()


def _is_origin_allowed(websocket: WebSocket) -> bool:
    """Validate Origin header to protect against Cross-Site WebSocket Hijacking (CSWSH)."""
    origin = websocket.headers.get("origin")
    if not origin:
        # Native client (ESP32 firmware, Flutter desktop/mobile native socket)
        return True

    # Permit local playground and explicitly allowed web origins
    if origin in ("http://localhost:8000", "http://127.0.0.1:8000", "null"):
        return True

    allowed = set(settings.CORS_ORIGINS)
    if origin in allowed:
        return True

    # Check for private network RFC 1918 addresses
    if re.match(r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$", origin):
        return True

    logger.warning(f"Rejected untrusted WebSocket origin: {origin}")
    return False


@router.websocket("/ws/phone")
async def phone_ws(
    websocket: WebSocket,
    pairing_code: str = Query(..., description="Pairing code for this robot session"),
):
    """
    Phone app channel.
    - Receives: binary audio chunks, binary JPEG camera frames
    - Sends:    JSON eye/mood messages, JSON gaze messages, binary TTS audio
    """
    if not _is_origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    if not verify_pairing_code(pairing_code):
        await websocket.close(code=1008, reason="Invalid pairing code")
        return

    await manager.connect_phone(websocket)
    try:
        await phone_handler(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_phone(websocket)
        get_phone_action_service().reset_call_state()


@router.websocket("/ws/desk")
async def desk_ws(
    websocket: WebSocket,
    pairing_code: str = Query(..., description="Pairing code for this robot session"),
):
    """
    Desktop control room channel.
    - Receives: JSON command messages (gestures, direct servo control, STOP)
    - Sends:    JSON status updates, live conversation, telemetry
    """
    if not _is_origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    if not verify_pairing_code(pairing_code):
        await websocket.close(code=1008, reason="Invalid pairing code")
        return

    await manager.connect_desk(websocket)
    try:
        await desk_handler(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_desk(websocket)


@router.websocket("/ws/esp")
async def esp_ws(
    websocket: WebSocket,
    pairing_code: str = Query(..., description="Pairing code burned into ESP32 firmware"),
):
    """
    ESP32 firmware channel.
    - Receives: JSON telemetry ({"t":"tele","bat":7.6,"dist":85})
    - Sends:    JSON joint commands, motor commands, stop commands
    """
    if not _is_origin_allowed(websocket):
        await websocket.close(code=1008, reason="Origin not allowed")
        return

    if not verify_pairing_code(pairing_code):
        await websocket.close(code=1008, reason="Invalid pairing code")
        return

    await manager.connect_esp(websocket)
    try:
        await esp_handler(websocket)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect_esp(websocket)
