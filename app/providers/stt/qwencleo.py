"""
QwenCleo ASR Provider — Egyptian Arabic Speech-to-Text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fine-tune of Qwen3-ASR-1.7B specialised for Egyptian Arabic.
WER ≈ 19.9 % on a 3,699-sentence Egyptian test set (doc §6.1).
License: Apache-2.0.

Optimised with:
  • Multithreading (ThreadPoolExecutor) for concurrent chunk processing
  • Overlapping chunk-based ASR pipeline for low latency
  • Energy-based silence trimming to eliminate empty recording lag ("الريك الفاضي")
"""

import asyncio
import concurrent.futures
import io
import os
from pathlib import Path
from typing import List, Tuple

import numpy as np

# Resolve Python 3.12 torchvision circular import bug before any transformers sub-imports
try:
    import torchvision  # noqa: F401
except Exception:
    pass

from app.providers.tts.base import BaseSTTProvider
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Dedicated multithreading worker pool for ASR chunk processing
_stt_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=min(4, os.cpu_count() or 2),
    thread_name_prefix="qwencleo_stt",
)


def _trim_silence_array(
    audio: np.ndarray,
    sr: int,
    threshold_factor: float = 0.025,
    pad_ms: int = 80,
) -> Tuple[np.ndarray, bool]:
    """
    Trim leading and trailing silence from an audio array.
    Eliminates dead silence lag ("الريك فاضي") while preserving speech onsets.
    Returns (trimmed_audio, is_pure_silence).
    """
    if len(audio) == 0:
        return audio, True

    mono = audio.mean(axis=1) if audio.ndim > 1 else audio

    frame_size = max(1, int(sr * 0.02))  # 20ms frames
    num_frames = len(mono) // frame_size
    if num_frames == 0:
        return audio, False

    frames = mono[: num_frames * frame_size].reshape(num_frames, frame_size)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    peak_rms = float(np.max(rms))

    # If peak volume is below audible speech threshold (empty recording)
    if peak_rms < 1e-4:
        return np.array([], dtype=audio.dtype), True

    threshold = max(0.002, peak_rms * threshold_factor)
    active = np.where(rms > threshold)[0]
    if len(active) == 0:
        return np.array([], dtype=audio.dtype), True

    pad_samples = int(sr * (pad_ms / 1000.0))
    start_idx = max(0, active[0] * frame_size - pad_samples)
    end_idx = min(len(audio), (active[-1] + 1) * frame_size + pad_samples)

    return audio[start_idx:end_idx], False


def _split_into_chunks(
    audio: np.ndarray,
    sr: int,
    chunk_s: float = 10.0,
    stride_s: float = 1.0,
) -> List[np.ndarray]:
    """
    Split audio into overlapping chunks for parallel multithreaded processing.
    """
    total_samples = len(audio)
    chunk_samples = int(chunk_s * sr)
    stride_samples = int(stride_s * sr)
    step_samples = chunk_samples - stride_samples

    if total_samples <= chunk_samples:
        return [audio]

    chunks = []
    idx = 0
    while idx < total_samples:
        end = min(total_samples, idx + chunk_samples)
        chunk = audio[idx:end]
        if len(chunk) > int(sr * 0.5):  # keep chunks > 0.5s
            chunks.append(chunk)
        idx += step_samples

    return chunks


def _merge_transcripts(transcripts: List[str]) -> str:
    """Merge transcribed text chunks, deduplicating overlapping boundary tokens."""
    if not transcripts:
        return ""
    clean = [t.strip() for t in transcripts if t and t.strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]

    merged_words = clean[0].split()
    for nxt in clean[1:]:
        nxt_words = nxt.split()
        if not nxt_words:
            continue
        # Check overlap of 1-3 words at boundary
        matched = 0
        for k in range(min(4, len(merged_words), len(nxt_words)), 0, -1):
            if merged_words[-k:] == nxt_words[:k]:
                matched = k
                break
        merged_words.extend(nxt_words[matched:])

    return " ".join(merged_words)


class QwenCleoProvider(BaseSTTProvider):
    """
    Egyptian Arabic ASR via QwenCleo-ASR (Qwen3-ASR-1.7B fine-tune).
    Accelerated with multithreading, chunk processing, and early VAD silence gating.
    """

    _shared_pipeline = None
    _shared_lock = asyncio.Lock()
    _shared_error: str | None = None

    async def _ensure_loaded(self):
        if QwenCleoProvider._shared_pipeline is not None:
            return
        async with QwenCleoProvider._shared_lock:
            if QwenCleoProvider._shared_pipeline is None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(_stt_executor, self._load)

    def _load(self):
        try:
            try:
                import torchvision  # noqa: F401
            except Exception:
                pass

            import torch

            model_path = settings.QWENCLEO_MODEL_PATH
            # If local relative path doesn't exist, use Hugging Face repo
            if not Path(model_path).exists():
                logger.info(f"Local QwenCleo model not found at '{model_path}'. Using 'mohammedaly22/QwenCleo-ASR'...")
                model_path = "mohammedaly22/QwenCleo-ASR"

            device_idx = -1
            if settings.QWENCLEO_DEVICE == "cuda":
                if torch.cuda.is_available():
                    device_idx = 0
                else:
                    logger.warning("CUDA requested for QwenCleo but not available. Using CPU.")

            logger.info(f"Loading QwenCleo-ASR from {model_path} (device={device_idx})…")

            try:
                from transformers import pipeline as hf_pipeline  # type: ignore[import]
                QwenCleoProvider._shared_pipeline = hf_pipeline(
                    task="automatic-speech-recognition",
                    model=model_path,
                    device=device_idx,
                    chunk_length_s=15,
                    stride_length_s=2,
                    batch_size=4,
                    return_timestamps=False,
                    trust_remote_code=True,
                )
            except Exception as pipe_err:
                logger.warning(
                    f"Direct pipeline creation encountered error ({pipe_err}). "
                    "Loading via AutoModelForSpeechSeq2Seq and AutoProcessor..."
                )
                from transformers import (
                    AutoModelForSpeechSeq2Seq,
                    AutoProcessor,
                    pipeline as hf_pipeline,
                )
                device_str = f"cuda:{device_idx}" if device_idx >= 0 else "cpu"
                torch_dtype = torch.float16 if device_idx >= 0 else torch.float32
                model = AutoModelForSpeechSeq2Seq.from_pretrained(
                    model_path,
                    torch_dtype=torch_dtype,
                    low_cpu_mem_usage=True,
                    trust_remote_code=True,
                )
                if device_idx >= 0:
                    model = model.to(device_str)
                processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
                QwenCleoProvider._shared_pipeline = hf_pipeline(
                    task="automatic-speech-recognition",
                    model=model,
                    tokenizer=processor.tokenizer,
                    feature_extractor=processor.feature_extractor,
                    device=device_idx,
                    chunk_length_s=15,
                    stride_length_s=2,
                    batch_size=4,
                    return_timestamps=False,
                )

            QwenCleoProvider._shared_error = None
            logger.info("QwenCleo-ASR ready (multithreaded chunks enabled) ✓")
        except Exception as e:
            err_msg = f"Failed to load QwenCleo-ASR: {e}"
            logger.error(err_msg, exc_info=True)
            QwenCleoProvider._shared_error = err_msg
            raise RuntimeError(err_msg) from e

    async def transcribe(self, audio_bytes: bytes) -> str:
        await self._ensure_loaded()
        if QwenCleoProvider._shared_pipeline is None:
            raise RuntimeError(
                f"QwenCleo-ASR is unavailable. Error: {QwenCleoProvider._shared_error}"
            )

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_stt_executor, self._run, audio_bytes)

    def _run_single_chunk(self, chunk: np.ndarray, sample_rate: int) -> str:
        """Transcribe an individual audio chunk through the pipeline."""
        try:
            result = QwenCleoProvider._shared_pipeline(
                {"raw": chunk, "sampling_rate": sample_rate}
            )
            return result.get("text", "").strip()
        except Exception as exc:
            logger.warning(f"Error transcribing chunk: {exc}")
            return ""

    def _run(self, audio_bytes: bytes) -> str:
        import io
        import soundfile as sf  # type: ignore[import]

        try:
            audio_array, sample_rate = sf.read(io.BytesIO(audio_bytes))
            if audio_array.ndim > 1:
                audio_array = audio_array.mean(axis=1)  # stereo → mono

            # 1. Early silence trimming: remove long empty pauses at start/end
            trimmed_audio, is_silent = _trim_silence_array(audio_array, sample_rate)
            if is_silent or len(trimmed_audio) < int(sample_rate * 0.3):
                logger.debug("Audio recording is silent or empty. Returning empty transcript.")
                return ""

            dur_s = len(trimmed_audio) / sample_rate

            # 2. Short audio (< 8s): transcribe in one pass
            if dur_s <= 8.0:
                result = QwenCleoProvider._shared_pipeline(
                    {"raw": trimmed_audio, "sampling_rate": sample_rate}
                )
                return result.get("text", "").strip()

            # 3. Longer audio (> 8s): multithreaded chunk processing
            chunks = _split_into_chunks(trimmed_audio, sample_rate, chunk_s=8.0, stride_s=1.0)
            if len(chunks) == 1:
                result = QwenCleoProvider._shared_pipeline(
                    {"raw": chunks[0], "sampling_rate": sample_rate}
                )
                return result.get("text", "").strip()

            # Process chunks in parallel using multithreading executor
            futures = [
                _stt_executor.submit(self._run_single_chunk, chunk, sample_rate)
                for chunk in chunks
            ]
            transcripts = [f.result() for f in futures]
            return _merge_transcripts(transcripts)

        except Exception as e:
            logger.error(f"QwenCleo transcription execution error: {e}", exc_info=True)
            raise RuntimeError(f"QwenCleo transcription error: {e}") from e
