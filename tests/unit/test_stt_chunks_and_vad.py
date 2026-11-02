import numpy as np
import pytest
from app.providers.stt.qwencleo import _trim_silence_array, _split_into_chunks, _merge_transcripts
from app.services.voice_clone.voice_clone_service import trim_audio_silence


def test_silence_array_trimming():
    sr = 16000
    silence = np.zeros(sr * 3, dtype=np.float32)
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 2, sr * 2, dtype=np.float32))
    combined = np.concatenate([silence, tone, silence])
    trimmed, is_silent = _trim_silence_array(combined, sr)
    assert not is_silent, "Should not be detected as silent"
    dur = len(trimmed) / sr
    assert 1.8 <= dur <= 2.3, f"Expected ~2s audio, got {dur}"


def test_chunking_and_multithreading_support():
    sr = 16000
    tone = 0.5 * np.sin(2 * np.pi * 440 * np.linspace(0, 2, sr * 2, dtype=np.float32))
    long_tone = np.tile(tone, 10)  # 20 seconds
    chunks = _split_into_chunks(long_tone, sr, chunk_s=8.0, stride_s=1.0)
    assert len(chunks) >= 3, "20s audio should be partitioned into at least 3 chunks"


def test_merge_transcripts():
    chunks_txt = ["أهلاً بيك", "بيك في نيبولا", "في نيبولا يا صديقي"]
    merged = _merge_transcripts(chunks_txt)
    assert merged == "أهلاً بيك في نيبولا يا صديقي"


def test_pure_silence_detection():
    sr = 16000
    pure_silence = np.zeros(sr * 4, dtype=np.float32)
    trimmed, is_silent = _trim_silence_array(pure_silence, sr)
    assert is_silent is True
    assert len(trimmed) == 0

