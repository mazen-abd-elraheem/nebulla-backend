"""
Unit tests for VoiceTut-TTS optimization:
  - Non-destructive silence/SNR reference conditioning (5-9s sweet spot)
  - VoiceClonePrompt RAM + .vcp.pt disk caching
  - Parallel CPU chunk normalization & OmniVoice GPU micro-batching
  - True progressive sentence-level streaming (RIFF header + TTFA chunking)
  - Thread-safe concurrent synthesis execution
  - Unified Masri lexicon preservation (no comma injection for VoiceTut)
"""

from __future__ import annotations

import asyncio
import io
import math
import struct
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import soundfile as sf
import torch

from app.providers.tts.xtts.provider import (
    XTTSProvider,
    _build_streaming_wav_header,
    _fast_postprocess_chunk,
    _install_omnivoice_reliability_shims,
    prepare_optimized_reference_wav,
)
from app.utils.masri_normalizer import (
    MASRI_DIACRITICS_LEXICON,
    clean_llm_output_for_speech,
)


def _write_test_wav(path: Path, segments: list[tuple[str, float]], sr: int = 24000, amp: float = 0.04) -> None:
    """Build synthetic WAV from [('sil', sec), ('tone', sec), ...] segments."""
    chunks = []
    for kind, dur_s in segments:
        n = int(sr * dur_s)
        if kind == "sil":
            chunks.append(np.random.normal(0.0, 0.0005, size=n).astype(np.float32))
        else:
            t = np.arange(n, dtype=np.float32) / sr
            chunks.append((amp * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32))
    audio = np.concatenate(chunks)
    sf.write(str(path), audio, sr, format="WAV", subtype="PCM_16")


def test_clean_llm_output_for_voicetut_preserves_codeswitch_flow():
    """VoiceTut mode should detach Arabic clitics without inserting artificial commas after English words."""
    raw = "<think>ok</think> [happy] عندي meeting مهمة في الAPI دلوقتي"
    cleaned = clean_llm_output_for_speech(raw, for_voicetut=True)
    assert "meeting مهمة" in cleaned
    assert "meeting،" not in cleaned
    assert "ال API" in cleaned
    assert "دِلْوَقْتِي" not in cleaned  # left plain so VoiceTut normalizer handles harakat cleanly
    assert "علشان" in MASRI_DIACRITICS_LEXICON


def test_prepare_optimized_reference_compacts_silence_without_dropping_short_clauses(tmp_path):
    """A ~12s recording containing ~8s speech and 4s dead gaps should compact below 9.5s cleanly."""
    wav_path = tmp_path / "personality_test.wav"
    _write_test_wav(
        wav_path,
        [
            ("sil", 1.1),
            ("tone", 2.2),
            ("sil", 1.3),
            ("tone", 2.6),
            ("sil", 1.6),
            ("tone", 2.8),
            ("sil", 0.5),
        ],
        amp=0.035,
    )
    ref_text = "السلام عليكم انا اسمي مازن ودي تجربة صوت."
    opt_wav, opt_txt, needs_retranscribe = prepare_optimized_reference_wav(str(wav_path), ref_text)

    assert opt_wav != str(wav_path)
    assert opt_wav.endswith(".opt.wav")
    assert Path(opt_wav).exists()
    assert wav_path.exists()  # original preserved non-destructively
    assert opt_txt == ref_text
    assert needs_retranscribe is False  # no speech clauses dropped -> full ref_text still valid!

    info = sf.info(opt_wav)
    assert 6.5 <= info.duration <= 9.5
    samples, _ = sf.read(opt_wav, dtype="float32")
    rms = float(np.sqrt(np.mean(samples ** 2)))
    assert rms > 0.06  # gently boosted from weak 0.035 input without clipping
    assert float(np.max(np.abs(samples))) <= 0.96


def test_prepare_optimized_reference_trims_overlong_multi_clause_audio(tmp_path):
    """A 18s+ recording of pure speech across multiple clauses trims safely to 5.5-8.5s and flags retranscribe."""
    wav_path = tmp_path / "personality_long.wav"
    _write_test_wav(
        wav_path,
        [
            ("tone", 3.5),
            ("sil", 0.5),
            ("tone", 4.0),
            ("sil", 0.5),
            ("tone", 4.0),
            ("sil", 0.5),
            ("tone", 4.0),
        ],
        amp=0.09,
    )
    opt_wav, _, needs_retranscribe = prepare_optimized_reference_wav(str(wav_path), "نص طويل كامل")
    assert Path(opt_wav).exists()
    assert needs_retranscribe is True
    assert sf.info(opt_wav).duration <= 9.5


@pytest.mark.asyncio
async def test_prompt_caching_and_parallel_batched_generation_and_streaming(tmp_path):
    """Verify VoiceClonePrompt disk+RAM cache, multi-sentence batching, concurrent safety & progressive streaming."""
    from omnivoice.models.omnivoice import VoiceClonePrompt

    ref_wav = tmp_path / "sample.wav"
    _write_test_wav(ref_wav, [("tone", 3.0)], amp=0.1)
    ref_txt = tmp_path / "sample.txt"
    ref_txt.write_text("ازيك يا صاحبي.", encoding="utf-8")

    class _FakeNormalizer:
        def normalize(self, t: str) -> str:
            return t.strip()

    class _FakeModel:
        def __init__(self):
            self.prompt_calls = 0
            self.generate_batches = []

        def create_voice_clone_prompt(self, ref_audio, ref_text=None, preprocess_prompt=True):
            self.prompt_calls += 1
            return VoiceClonePrompt(
                ref_audio_tokens=torch.zeros((8, 60), dtype=torch.long),
                ref_text=ref_text or "ازيك يا صاحبي.",
                ref_rms=0.1,
            )

        def generate(self, text, language=None, voice_clone_prompt=None, speed=None, generation_config=None, normalize_text=False):
            items = text if isinstance(text, list) else [text]
            self.generate_batches.append(items)
            # Generate 0.4s audible sine per item
            sr = 24000
            t = np.arange(int(sr * 0.4), dtype=np.float32) / sr
            return [(0.25 * np.sin(2.0 * np.pi * 300.0 * t)).astype(np.float32) for _ in items]

    fake_model = _FakeModel()
    fake_tts = MagicMock()
    fake_tts.sampling_rate = 24000
    fake_tts.model = fake_model
    fake_tts.normalizer = _FakeNormalizer()
    fake_tts.registry = None

    provider = XTTSProvider(reference_wav=str(ref_wav), device="cpu")
    provider.invalidate_prompt_cache()

    with patch.object(XTTSProvider, "_shared_tts", fake_tts), \
         patch.object(XTTSProvider, "_shared_device", "cpu"), \
         patch("app.core.config.settings.VOICETUT_PREFER_MICROSERVICE", False):
        # 1. Multi-sentence call -> batched GPU call + prompt built once
        wav1 = await provider.synthesize(
            "أهلاً بيك في نيبولا. إحنا شغالين دلوقتي تمام. يلا بينا نبدأ!",
            ref_audio=str(ref_wav),
        )
        assert fake_model.prompt_calls == 1
        assert len(fake_model.generate_batches) == 1
        assert len(fake_model.generate_batches[0]) == 3  # all 3 sentences batched in parallel!
        with wave.open(io.BytesIO(wav1), "rb") as wf:
            assert wf.getnframes() > 24000  # >1.0s concatenated audio

        # 2. Second request reuses cached VoiceClonePrompt -> zero prompt rebuilds
        wav2 = await provider.synthesize("أهلاً تاني.", ref_audio=str(ref_wav))
        assert fake_model.prompt_calls == 1
        assert len(wav2) > 1000

        # 3. Simulate restart clearing RAM cache -> loads `.vcp.pt` from disk cleanly!
        provider.invalidate_prompt_cache(str(ref_wav))
        assert ref_wav.with_suffix(".vcp.pt").exists()
        wav3 = await provider.synthesize("تجربة من الكاش.", ref_audio=str(ref_wav))
        assert fake_model.prompt_calls == 1

        # 4. Concurrent async requests run safely without errors
        results = await asyncio.gather(
            provider.synthesize("جملة أولى.", ref_audio=str(ref_wav)),
            provider.synthesize("جملة تانية.", ref_audio=str(ref_wav)),
            provider.synthesize("جملة تالتة.", ref_audio=str(ref_wav)),
        )
        assert all(len(r) > 1000 for r in results)

        # 5. True progressive streaming emits RIFF header first + chunk 0 before remaining batch
        fake_model.generate_batches.clear()
        stream_chunks = []
        async for chunk in provider.synthesize_stream(
            "دي الجملة الأولى. ودي الجملة التانية. ودي التالتة!",
            ref_audio=str(ref_wav),
        ):
            stream_chunks.append(chunk)

        assert stream_chunks[0][:4] == b"RIFF"
        assert len(stream_chunks[0]) == 44
        assert len(stream_chunks) >= 3  # header + chunk 0 + chunk(s) 1..2
        assert len(fake_model.generate_batches[0]) == 1  # sentence 0 streamed standalone for low TTFA!
        assert len(fake_model.generate_batches[1]) == 2  # remaining sentences batched together!
        assert provider.last_metrics.get("ttfa_ms", 0) > 0

        # 6. Repeat-phrase WAV cache returns instantaneously without touching GPU
        batches_before = len(fake_model.generate_batches)
        wav3_cached = await provider.synthesize("تجربة من الكاش.", ref_audio=str(ref_wav))
        assert wav3_cached == wav3
        assert len(fake_model.generate_batches) == batches_before
        assert provider.last_metrics.get("cached") is True


def test_reliability_shims_and_fast_postprocess_preserve_tail():
    """Verify duration headroom shim, quiet consonant preservation, and comma-clause streaming split."""
    class _DummyModel:
        def _estimate_target_tokens(self, text, ref_text, num_ref_audio_tokens, speed=1.0):
            return 25

    dummy = _DummyModel()
    _install_omnivoice_reliability_shims(dummy)
    _install_omnivoice_reliability_shims(dummy)  # idempotent
    assert dummy._estimate_target_tokens("أهلاً", "مرحب", 50, speed=1.0) == 31
    assert dummy._estimate_target_tokens("أهلاً " * 15, "مرحب", 50, speed=1.15) == 33

    # Leading 0.5s silence + 0.3s burst + 0.5s trailing silence -> retains 140ms safety tail without clipping end
    sr = 24000
    t = np.arange(int(sr * 0.3), dtype=np.float32) / sr
    burst = (0.2 * np.sin(2.0 * np.pi * 250.0 * t)).astype(np.float32)
    raw = np.concatenate([np.zeros(int(sr * 0.5), dtype=np.float32), burst, np.zeros(int(sr * 0.5), dtype=np.float32)])
    trimmed = _fast_postprocess_chunk(raw, sample_rate=sr)
    assert len(trimmed) < len(raw)
    assert len(trimmed) >= len(burst) + int(sr * 0.14)

    fake_tts = MagicMock()
    fake_tts.normalizer.normalize.side_effect = lambda s: s.strip()
    provider = XTTSProvider(device="cpu")
    long_clause = "بقولكم ايه يا جماعة الخير النهاردة، إحنا عندنا شغل مهم جداً لازم يخلص حالاً"
    chunks = provider._prepare_chunks_parallel(fake_tts, long_clause, max_chars=170, first_chunk_max_chars=55)
    assert len(chunks) == 2
    assert chunks[0].endswith("،")


