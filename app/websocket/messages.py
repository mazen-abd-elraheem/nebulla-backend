"""
WebSocket message schemas (doc §6 JSON messages table).

All messages share a "t" (type) discriminator field.
"""

from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field


# ── Phone → Backend ─────────────────────────────────────────────────────────

class AudioChunkMsg(BaseModel):
    """Binary audio sent over ws/phone — handled as raw bytes, not JSON."""
    pass  # raw bytes, no schema needed


class CameraFrameMsg(BaseModel):
    """Small JPEG frame from front camera. Sent as binary over ws/phone."""
    pass  # raw bytes


# ── Backend → Phone ──────────────────────────────────────────────────────────

class EyesMoodMsg(BaseModel):
    t: Literal["eyes"] = "eyes"
    mood: str  # "happy" | "surprised" | "sad" | "neutral" | "thinking"
    audio_url: Optional[str] = None  # URL of TTS audio chunk


class GazeMsg(BaseModel):
    """Tell the phone app where to point the eyes (doc §5.1 eye tracking)."""
    t: Literal["gaze"] = "gaze"
    x: float = Field(..., ge=-1.0, le=1.0)   # -1=left, +1=right
    y: float = Field(..., ge=-1.0, le=1.0)   # -1=down, +1=up


class TextStreamMsg(BaseModel):
    """Streaming LLM text token."""
    t: Literal["text_stream"] = "text_stream"
    token: str
    is_final: bool = False


# ── Desktop → Backend ────────────────────────────────────────────────────────

class DesktopCmdMsg(BaseModel):
    """Manual gesture/motion command from desktop control room (doc §5.2)."""
    t: Literal["cmd"] = "cmd"
    gesture: Optional[str] = None      # e.g. "like", "wave", "stop"
    joint_id: Optional[int] = None     # direct servo override
    angle: Optional[float] = None
    speed_ms: Optional[int] = None
    motor_left: Optional[int] = None   # PWM -255 to 255
    motor_right: Optional[int] = None


# ── Backend → ESP32 ──────────────────────────────────────────────────────────

class JointCmdMsg(BaseModel):
    """Move a single servo joint (doc §6 ws messages: {"t":"joint","id":3,"deg":90,"ms":300})."""
    t: Literal["joint"] = "joint"
    id: int            # servo index 0-11
    deg: float         # target angle in degrees
    ms: int = 300      # movement duration in milliseconds


class MotorCmdMsg(BaseModel):
    """Drive the wheel motors (tank-style differential, doc §7.7)."""
    t: Literal["motor"] = "motor"
    left: int = Field(..., ge=-255, le=255)   # PWM
    right: int = Field(..., ge=-255, le=255)


class StopMsg(BaseModel):
    t: Literal["stop"] = "stop"


class SignalMsg(BaseModel):
    """Play a named gesture sequence (doc §6 signal planner)."""
    t: Literal["signal"] = "signal"
    name: str   # e.g. "like", "wave"


# ── ESP32 → Backend ───────────────────────────────────────────────────────────

class TelemetryMsg(BaseModel):
    """ESP32 telemetry (doc §6: {"t":"tele","bat":7.6,"dist":85})."""
    t: Literal["tele"] = "tele"
    bat: float   # battery voltage
    dist: int    # distance sensor (cm)
    rssi: Optional[int] = None


class ErrorMsg(BaseModel):
    t: Literal["error"] = "error"
    code: str
    message: str


# ── Union type for routing ────────────────────────────────────────────────────
IncomingMsg = Union[
    DesktopCmdMsg,
    TelemetryMsg,
    EyesMoodMsg,
    GazeMsg,
    ErrorMsg,
]
