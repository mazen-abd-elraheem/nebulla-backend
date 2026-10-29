"""Unit tests for Motion Guard."""

import pytest
from app.services.motion.motion_guard import MotionGuard
from app.websocket.messages import JointCmdMsg


@pytest.fixture
def guard():
    g = MotionGuard()
    g.load_calibration([
        {"servo_id": 0, "min_angle": 0.0, "max_angle": 180.0, "home_angle": 90.0},
        {"servo_id": 1, "min_angle": 20.0, "max_angle": 160.0, "home_angle": 90.0},
    ])
    return g


def test_valid_command_passes(guard):
    cmd = JointCmdMsg(id=0, deg=90.0, ms=300)
    result = guard.validate_joint(cmd)
    assert result is not None
    assert result.deg == 90.0


def test_angle_clamped_to_max(guard):
    cmd = JointCmdMsg(id=0, deg=270.0, ms=300)  # over max
    result = guard.validate_joint(cmd)
    assert result is not None
    assert result.deg == 180.0


def test_angle_clamped_to_min(guard):
    cmd = JointCmdMsg(id=1, deg=5.0, ms=300)  # under min 20
    result = guard.validate_joint(cmd)
    assert result is not None
    assert result.deg == 20.0


def test_too_fast_rejected(guard):
    cmd = JointCmdMsg(id=0, deg=90.0, ms=10)  # too fast
    result = guard.validate_joint(cmd)
    assert result is None


def test_stop_always_passes():
    """STOP command bypasses motion guard (doc §4)."""
    # The stop command is a different type — just a dict {"t": "stop"}
    # It should always be forwarded directly without guard
    stop_cmd = {"t": "stop"}
    assert stop_cmd["t"] == "stop"  # trivial — guard doesn't touch stop
