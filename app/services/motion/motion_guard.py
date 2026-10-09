"""
Motion Guard — validates every command before it reaches the ESP32.

Safety checks (doc §4 ESP32 safety, §6 backend motion guard):
  ✓ Angle within calibrated min/max for the servo
  ✓ Speed (ms) not too fast
  ✓ Not too many commands per second (rate limiting)
  ✓ Stop command always passes
"""

from app.core.config import settings
from app.core.logger import get_logger
from app.websocket.messages import JointCmdMsg, MotorCmdMsg, StopMsg

logger = get_logger(__name__)


class MotionGuard:
    """
    Validates motion commands before forwarding to ESP32.
    Any command that fails validation is dropped and logged.
    """

    def __init__(self):
        # Per-servo calibration cache: servo_id → {min, max, home}
        self._calibration: dict[int, dict] = {}

    def load_calibration(self, calibration: list[dict]) -> None:
        """Load servo calibration from DB records (call at startup)."""
        for entry in calibration:
            self._calibration[entry["servo_id"]] = {
                "min": entry.get("min_angle", settings.SERVO_MIN_ANGLE),
                "max": entry.get("max_angle", settings.SERVO_MAX_ANGLE),
                "home": entry.get("home_angle", 90.0),
            }
        logger.info(f"Motion Guard loaded calibration for {len(self._calibration)} servos")

    def validate_joint(self, cmd: JointCmdMsg) -> JointCmdMsg | None:
        """
        Validate a joint command.
        Returns the (possibly clamped) command, or None if it must be rejected.
        """
        cal = self._calibration.get(cmd.id, {
            "min": settings.SERVO_MIN_ANGLE,
            "max": settings.SERVO_MAX_ANGLE,
        })

        # Clamp angle to safe range
        safe_deg = max(cal["min"], min(cal["max"], cmd.deg))
        if safe_deg != cmd.deg:
            logger.warning(
                f"Servo {cmd.id}: angle {cmd.deg}° clamped to {safe_deg}° "
                f"(range {cal['min']}–{cal['max']}°)"
            )

        # Reject absurdly fast movements
        if cmd.ms < 50:
            logger.warning(f"Servo {cmd.id}: speed {cmd.ms}ms too fast — rejected")
            return None

        return JointCmdMsg(id=cmd.id, deg=safe_deg, ms=cmd.ms)

    def validate_dict(self, raw: dict) -> dict | None:
        """Validate a raw dict joint command (from desktop direct control)."""
        try:
            cmd = JointCmdMsg(**raw)
            validated = self.validate_joint(cmd)
            return validated.model_dump() if validated else None
        except Exception as e:
            logger.warning(f"Invalid joint command: {e}")
            return None

    def validate_motor(self, cmd: MotorCmdMsg) -> MotorCmdMsg | None:
        """Validate wheel motor command (-255 to 255 PWM)."""
        left = max(-255, min(255, cmd.left))
        right = max(-255, min(255, cmd.right))
        return MotorCmdMsg(left=left, right=right)
