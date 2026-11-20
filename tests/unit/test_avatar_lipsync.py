"""Unit tests for Acoustic Lipsync & Synchronized Avatar Action Engine."""

import io
import math
import numpy as np
import pytest
import scipy.io.wavfile as wavfile

from app.services.avatar.lipsync import AcousticLipsyncService, get_lipsync_service


def _build_test_wav(duration_s: float = 1.0, sr: int = 22050) -> bytes:
    """Generate synthetic speech-like WAV bytes with modulated amplitude and silences."""
    t = np.linspace(0, duration_s, int(sr * duration_s), endpoint=False)
    # 200 Hz carrier modulated at 3 Hz
    modulation = 0.5 + 0.5 * np.sin(2 * np.pi * 3 * t)
    audio = (np.sin(2 * np.pi * 200 * t) * modulation).astype(np.float32)
    # Add 100ms silence at start and end
    silence_samples = int(sr * 0.1)
    audio[:silence_samples] = 0.0
    audio[-silence_samples:] = 0.0

    buf = io.BytesIO()
    wavfile.write(buf, sr, (audio * 32767).astype(np.int16))
    return buf.getvalue()


def test_lipsync_singleton():
    s1 = get_lipsync_service()
    s2 = AcousticLipsyncService.get_instance()
    assert s1 is s2


def test_lipsync_analyze_wav_metrics():
    svc = get_lipsync_service()
    wav_bytes = _build_test_wav(duration_s=1.2, sr=22050)

    res = svc.analyze_wav(wav_bytes, expression="happy", face_emoji="😊")

    assert res["duration_ms"] >= 1150
    assert res["fps"] == 40  # 25ms interval
    assert res["frame_count"] > 30
    assert "viseme_timeline" in res
    assert "eye_timeline" in res
    assert res["max_jaw"] > 0.15
    assert res["avg_jaw"] > 0.02


def test_lipsync_viseme_timeline_structure():
    svc = get_lipsync_service()
    wav_bytes = _build_test_wav(duration_s=0.8, sr=22050)

    res = svc.analyze_wav(wav_bytes, expression="laugh", face_emoji="😂")
    timeline = res["viseme_timeline"]

    assert len(timeline) > 10
    first_frame = timeline[0]
    assert "t_ms" in first_frame
    assert "jaw" in first_frame
    assert "level" in first_frame
    assert "viseme" in first_frame
    assert first_frame["level"] in (0, 1, 2, 3)
    assert first_frame["viseme"] in ("sil", "fricative", "smile_e", "round_o", "open_a")

    # Final frame should return towards closed mouth
    last_frame = timeline[-1]
    assert last_frame["jaw"] <= 0.05
    assert last_frame["level"] == 0


def test_lipsync_eye_timeline_wink():
    svc = get_lipsync_service()
    eye_frames = svc.generate_eye_timeline(duration_ms=1600, expression="wink", face_emoji="😉")

    assert len(eye_frames) >= 3
    wink_frames = [f for f in eye_frames if f.get("wink", 0.0) > 0.5]
    assert len(wink_frames) > 0, "Expected wink keyframe for wink expression"


def test_lipsync_eye_timeline_sleepy():
    svc = get_lipsync_service()
    eye_frames = svc.generate_eye_timeline(duration_ms=1200, expression="sleepy", face_emoji="😴")

    assert len(eye_frames) >= 2
    for frame in eye_frames:
        assert frame["blink"] >= 0.80, "Expected sleepy eyelids to stay heavily drooped"


def test_lipsync_estimate_cadence():
    svc = get_lipsync_service()
    res = svc.estimate_cadence(duration_ms=1000, expression="neutral", face_emoji="😐")

    assert res["duration_ms"] == 1000
    assert res["frame_count"] == 40
    assert len(res["viseme_timeline"]) == 40
    assert len(res["eye_timeline"]) > 0
