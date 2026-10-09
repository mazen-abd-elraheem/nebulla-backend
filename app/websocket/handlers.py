"""
WebSocket message handlers for each channel.
Each handler runs in a loop receiving messages and dispatching to services.
"""

import asyncio
import json

from fastapi import WebSocket

from app.core.logger import get_logger
from app.services.ai.pipeline import AIPipeline
from app.services.vision.face_service import FaceService
from app.services.motion.motion_guard import MotionGuard
from app.services.motion.signal_planner import SignalPlanner
from app.websocket.manager import manager
from app.websocket.messages import TelemetryMsg, DesktopCmdMsg

logger = get_logger(__name__)

# Service singletons (lazily initialised on first message)
_ai_pipeline: AIPipeline | None = None
_face_service: FaceService | None = None
_motion_guard: MotionGuard | None = None
_signal_planner: SignalPlanner | None = None


def _get_ai_pipeline() -> AIPipeline:
    global _ai_pipeline
    if _ai_pipeline is None:
        _ai_pipeline = AIPipeline()
    return _ai_pipeline


def _get_face_service() -> FaceService:
    global _face_service
    if _face_service is None:
        _face_service = FaceService()
    return _face_service


def _get_motion_guard() -> MotionGuard:
    global _motion_guard
    if _motion_guard is None:
        _motion_guard = MotionGuard()
    return _motion_guard


def _get_signal_planner() -> SignalPlanner:
    global _signal_planner
    if _signal_planner is None:
        _signal_planner = SignalPlanner()
    return _signal_planner


async def phone_handler(ws: WebSocket) -> None:
    """
    Handle messages from the phone app.
    - Binary messages: audio (PCM) → STT → LLM → TTS pipeline
    - JSON messages: camera frames (JPEG) → UniFace → gaze
    """
    pipeline = _get_ai_pipeline()
    face_service = _get_face_service()

    while True:
        message = await ws.receive()

        if "bytes" in message and message["bytes"]:
            raw = message["bytes"]

            if raw[:2] in (b"\xff\xd8", b"\xff\xe0", b"\xff\xe1"):
                # JPEG camera frame → vision pipeline
                await face_service.process_frame(raw)
            else:
                # Audio chunk → full AI pipeline (STT → LLM → TTS)
                await pipeline.process_audio_chunk(raw)

        elif "text" in message and message["text"]:
            try:
                data = json.loads(message["text"])
                msg_type = data.get("t")
                if msg_type == "status":
                    await ws.send_json(manager.status())
            except json.JSONDecodeError:
                logger.warning("Phone sent invalid JSON")


async def desk_handler(ws: WebSocket) -> None:
    """
    Handle messages from the desktop control room.
    - JSON: gesture commands, servo control, STOP, settings
    """
    guard = _get_motion_guard()
    planner = _get_signal_planner()

    while True:
        message = await ws.receive()

        if "text" in message and message["text"]:
            try:
                data = json.loads(message["text"])
                msg_type = data.get("t")

                if msg_type == "cmd":
                    cmd = DesktopCmdMsg(**data)

                    if cmd.gesture == "stop" or (cmd.gesture is None and not cmd.joint_id):
                        await manager.send_to_esp({"t": "stop"})
                    elif cmd.gesture:
                        # Named gesture → signal planner → motion guard → ESP32
                        commands = await planner.resolve(cmd.gesture)
                        for joint_cmd in commands:
                            safe = guard.validate_joint(joint_cmd)
                            if safe:
                                await manager.send_to_esp(joint_cmd.model_dump())
                    elif cmd.joint_id is not None:
                        # Direct servo control
                        joint = {"t": "joint", "id": cmd.joint_id,
                                 "deg": cmd.angle, "ms": cmd.speed_ms or 300}
                        validated = guard.validate_dict(joint)
                        if validated:
                            await manager.send_to_esp(validated)

                elif msg_type == "status":
                    await ws.send_json(manager.status())

            except Exception as e:
                logger.error(f"Desk handler error: {e}")


async def esp_handler(ws: WebSocket) -> None:
    """
    Handle messages from the ESP32 board.
    - JSON telemetry → update device record, broadcast to desks
    """
    while True:
        message = await ws.receive()

        if "text" in message and message["text"]:
            try:
                data = json.loads(message["text"])
                msg_type = data.get("t")

                if msg_type == "tele":
                    tele = TelemetryMsg(**data)
                    # Broadcast telemetry to all connected desktops
                    await manager.broadcast_to_desks({
                        "t": "telemetry",
                        "bat": tele.bat,
                        "dist": tele.dist,
                    })
                    # Also update the phone LED state
                    if tele.dist < 20:  # obstacle too close
                        await manager.send_to_esp({"t": "stop"})
                        await manager.send_to_phone({"t": "eyes", "mood": "alert"})

                elif msg_type == "error":
                    logger.error(f"ESP32 error: {data}")
                    await manager.broadcast_to_desks(data)

            except Exception as e:
                logger.error(f"ESP32 handler error: {e}")
