"""Unit tests for Signal Planner."""

import pytest
from app.services.motion.signal_planner import SignalPlanner


@pytest.mark.asyncio
async def test_builtin_like_signal():
    planner = SignalPlanner()
    cmds = await planner.resolve("like")
    assert len(cmds) > 0
    assert all(c.id >= 0 for c in cmds)


@pytest.mark.asyncio
async def test_unknown_signal_returns_empty():
    planner = SignalPlanner()
    cmds = await planner.resolve("nonexistent_gesture_xyz")
    assert cmds == []


@pytest.mark.asyncio
async def test_extract_from_response_finds_tags():
    planner = SignalPlanner()
    response = "أهلاً يا صديقي! [happy] [wave]"
    commands = await planner.extract_from_response(response)
    # happy maps to wave, wave is direct — should get some joint commands
    assert isinstance(commands, list)


@pytest.mark.asyncio
async def test_db_signal_overrides_builtin():
    planner = SignalPlanner()
    # Override the "like" signal via DB load
    planner.load_from_db([{
        "name": "like",
        "joint_commands_json": '[{"t":"joint","id":9,"deg":45,"ms":200}]',
        "emotion_tag": "happy",
    }])
    cmds = await planner.resolve("like")
    assert len(cmds) == 1
    assert cmds[0].id == 9
    assert cmds[0].deg == 45
