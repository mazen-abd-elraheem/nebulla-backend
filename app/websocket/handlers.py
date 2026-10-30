"""
WebSocket message handlers for each channel.
Each handler runs in a loop receiving messages and dispatching to services.
Features decoupled multi-threaded processing so video frames and audio chunks
do not block the WebSocket connection or each other.
"""

from __future__ import annotations

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

# Concurrency semaphore to throttle concurrent heavy AI inferences (DoS mitigation)
_pipeline_semaphore = asyncio.Semaphore(4)


async def _safe_process_text(pipeline: AIPipeline, text: str) -> None:
    async with _pipeline_semaphore:
        await pipeline.process_text(text)


def get_ai_pipeline() -> AIPipeline:
    global _ai_pipeline
    if _ai_pipeline is None:
        _ai_pipeline = AIPipeline()
    return _ai_pipeline


_get_ai_pipeline = get_ai_pipeline


def get_face_service() -> FaceService:
    global _face_service
    if _face_service is None:
        _face_service = FaceService()
    return _face_service


_get_face_service = get_face_service


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


async def _vision_frame_worker(queue: asyncio.Queue[bytes], face_service: FaceService) -> None:
    """
    Background worker consuming camera frames from bounded queue.
    Ensures vision model inference never blocks the WebSocket receive loop.
    """
    while True:
        try:
            frame_bytes = await queue.get()
            try:
                await face_service.process_frame(frame_bytes)
            finally:
                queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Vision frame worker error: {e}")


async def _audio_chunk_worker(queue: asyncio.Queue[bytes], pipeline: AIPipeline) -> None:
    """
    Background worker consuming audio PCM chunks sequentially.
    Ensures VAD and STT pipeline execution runs independently of camera frames.
    """
    while True:
        try:
            audio_bytes = await queue.get()
            try:
                await pipeline.process_audio_chunk(audio_bytes)
            finally:
                queue.task_done()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Audio chunk worker error: {e}")


async def phone_handler(ws: WebSocket) -> None:
    """
    Handle messages from the phone app with decoupled multi-threaded processing.
    - Camera frames are buffered in a latest-frame queue (drop-frame on congestion).
    - Audio chunks stream continuously through an independent audio worker queue.
    """
    pipeline = _get_ai_pipeline()
    face_service = _get_face_service()

    # Bounded queue with size 1 for freshest-frame tracking
    frame_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1)
    # Bounded audio queue (up to ~12 seconds of buffered audio chunks)
    audio_queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=120)

    vision_worker = asyncio.create_task(_vision_frame_worker(frame_queue, face_service))
    audio_worker = asyncio.create_task(_audio_chunk_worker(audio_queue, pipeline))

    try:
        while True:
            message = await ws.receive()

            if "bytes" in message and message["bytes"]:
                raw = message["bytes"]

                if raw[:2] in (b"\xff\xd8", b"\xff\xe0", b"\xff\xe1"):
                    # JPEG camera frame: keep latest frame only
                    if frame_queue.full():
                        try:
                            frame_queue.get_nowait()
                            frame_queue.task_done()
                        except (asyncio.QueueEmpty, ValueError):
                            pass
                    try:
                        frame_queue.put_nowait(raw)
                    except asyncio.QueueFull:
                        pass
                else:
                    # Audio chunk: buffer for pipeline
                    try:
                        audio_queue.put_nowait(raw)
                    except asyncio.QueueFull:
                        try:
                            audio_queue.get_nowait()
                            audio_queue.task_done()
                        except (asyncio.QueueEmpty, ValueError):
                            pass
                        audio_queue.put_nowait(raw)

            elif "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                    msg_type = data.get("t")
                    if msg_type == "status":
                        await ws.send_json(manager.status())
                    elif msg_type == "chat":
                        user_text = data.get("text", "")
                        if user_text.strip():
                            asyncio.create_task(_safe_process_text(pipeline, user_text.strip()))
                except json.JSONDecodeError:
                    logger.warning("Phone sent invalid JSON")
    finally:
        vision_worker.cancel()
        audio_worker.cancel()
        await asyncio.gather(vision_worker, audio_worker, return_exceptions=True)


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
                        joint = {
                            "t": "joint",
                            "id": cmd.joint_id,
                            "deg": cmd.angle,
                            "ms": cmd.speed_ms or 300,
                        }
                        validated = guard.validate_dict(joint)
                        if validated:
                            await manager.send_to_esp(validated)

                elif msg_type == "status":
                    await ws.send_json(manager.status())
                elif msg_type == "chat":
                    user_text = data.get("text", "")
                    if user_text.strip():
                        pipeline = _get_ai_pipeline()
                        asyncio.create_task(_safe_process_text(pipeline, user_text.strip()))

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
