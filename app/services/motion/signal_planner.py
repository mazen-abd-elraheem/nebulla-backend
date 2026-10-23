"""
Signal Planner — converts gesture/emotion keywords from LLM output into ESP32 commands.

Workflow (doc §6 backend):
  LLM response contains emotion tags like [like], [wave], [greet]
  → Signal Planner looks up the named signal in DB
  → Returns a list of JointCmdMsg to send to ESP32

Also responsible for loading pre-recorded gesture sequences from the DB.
"""

import json
import re
from typing import Iterator

from app.core.logger import get_logger
from app.websocket.messages import JointCmdMsg

logger = get_logger(__name__)

# Built-in gesture sequences (fallback if DB is empty)
_BUILTIN_SIGNALS: dict[str, list[dict]] = {
    "like": [
        # Thumb up — all fingers close, thumb extends
        {"t": "joint", "id": 0, "deg": 180, "ms": 300},  # thumb extend
        {"t": "joint", "id": 1, "deg": 0,   "ms": 200},  # index close
        {"t": "joint", "id": 2, "deg": 0,   "ms": 200},  # mid+ring+pinky close
    ],
    "wave": [
        {"t": "joint", "id": 5, "deg": 60,  "ms": 400},  # shoulder up
        {"t": "joint", "id": 5, "deg": 30,  "ms": 300},  # shoulder mid
        {"t": "joint", "id": 5, "deg": 60,  "ms": 300},  # shoulder up
        {"t": "joint", "id": 5, "deg": 90,  "ms": 400},  # shoulder neutral
    ],
    "greet": [
        {"t": "joint", "id": 5, "deg": 45,  "ms": 500},  # raise arm
        {"t": "joint", "id": 0, "deg": 180, "ms": 300},  # open hand
        {"t": "joint", "id": 5, "deg": 90,  "ms": 600},  # lower arm
    ],
    "ok": [
        {"t": "joint", "id": 0, "deg": 90,  "ms": 300},  # thumb
        {"t": "joint", "id": 1, "deg": 90,  "ms": 200},  # index curl
    ],
    "stop": [
        {"t": "stop"},
    ],
}

# Emotion-to-gesture mapping (doc §5.1)
_EMOTION_GESTURES: dict[str, str | None] = {
    "happy": "wave",
    "فرحان": "wave",
    "سعيد": "wave",
    "surprised": "greet",
    "متفاجئ": "greet",
    "like": "like",
    "إعجاب": "like",
    "greet": "greet",
    "تحية": "greet",
    "wave": "wave",
    "تلويح": "wave",
    "sad": None,
    "حزين": None,
    "neutral": None,
}

# Regex to extract [gesture] tags from LLM output (supports Arabic and English)
_TAG_RE = re.compile(r"\[([\w\u0600-\u06FF]+)\]")


class SignalPlanner:
    """
    Resolves named gestures and emotion tags to ESP32 joint commands.
    DB-backed signals override built-ins.
    """

    def __init__(self):
        self._db_signals: dict[str, list[dict]] = {}  # name → joint commands

    def load_from_db(self, signals: list[dict]) -> None:
        """Load signal definitions from the database at startup."""
        for sig in signals:
            try:
                cmds = json.loads(sig.get("joint_commands_json", "[]"))
                self._db_signals[sig["name"]] = cmds
            except Exception as e:
                logger.warning(f"Bad signal JSON for {sig.get('name')}: {e}")
        logger.info(f"Signal Planner loaded {len(self._db_signals)} DB signals")

    async def resolve(self, gesture_name: str) -> list[JointCmdMsg]:
        """
        Return the list of JointCmdMsg for a named gesture.
        DB signals take priority over built-ins.
        """
        raw_cmds = (
            self._db_signals.get(gesture_name)
            or _BUILTIN_SIGNALS.get(gesture_name)
        )
        if not raw_cmds:
            logger.warning(f"Unknown gesture: {gesture_name!r}")
            return []

        result = []
        for cmd in raw_cmds:
            if cmd.get("t") == "joint":
                try:
                    result.append(JointCmdMsg(
                        id=cmd["id"],
                        deg=cmd["deg"],
                        ms=cmd.get("ms", 300),
                    ))
                except Exception as e:
                    logger.warning(f"Bad joint command in signal {gesture_name!r}: {e}")
        return result

    async def extract_from_response(self, llm_response: str) -> list[dict]:
        """
        Parse [tag] markers from an LLM response and convert to ESP32 commands.
        Deduplicates gestures so overlapping tags (e.g. [wave] [happy]) do not
        flood the ESP32 with duplicate motor sequences.
        """
        tags = _TAG_RE.findall(llm_response)
        commands: list[dict] = []
        executed_gestures: set[str] = set()

        for tag in tags:
            tag_lower = tag.lower()

            target_gesture = tag_lower
            if target_gesture in _EMOTION_GESTURES:
                mapped = _EMOTION_GESTURES[target_gesture]
                if mapped:
                    target_gesture = mapped
                else:
                    continue

            if target_gesture in executed_gestures:
                continue

            gestures = await self.resolve(target_gesture)
            if gestures:
                executed_gestures.add(target_gesture)
                for g in gestures:
                    commands.append(g.model_dump())

        return commands
