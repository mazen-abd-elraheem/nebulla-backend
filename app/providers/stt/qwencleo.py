"""
QwenCleo ASR Provider — Egyptian Arabic Speech-to-Text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fine-tune of Qwen3-ASR-1.7B specialised for Egyptian Arabic.
WER ≈ 19.9 % on a 3,699-sentence Egyptian test set (doc §6.1).
License: Apache-2.0.

Requires an NVIDIA GPU (Ampere or newer) for real-time streaming.
Runs on CPU in a pinch but with higher latency.
"""

import asyncio

from app.providers.tts.base import BaseSTTProvider
from app.core.config import settings
from app.core.logger import get_logger
from app.core.threading import run_in_audio_thread

logger = get_logger(__name__)


class QwenCleoProvider(BaseSTTProvider):
    """Egyptian Arabic ASR via QwenCleo-ASR (Qwen3-ASR-1.7B fine-tune)."""

    def __init__(self):
        self._pipeline = None
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self):
        if self._pipeline is not None:
            return
        async with self._lock:
            if self._pipeline is None:
                loop = asyncio.get_event_loop()
                await run_in_audio_thread(self._load)

    def _load(self):
        try:
            from transformers import pipeline as hf_pipeline  # type: ignore[import]

            logger.info(f"Loading QwenCleo-ASR from {settings.QWENCLEO_MODEL_PATH}…")
            self._pipeline = hf_pipeline(
                task="automatic-speech-recognition",
                model=settings.QWENCLEO_MODEL_PATH,
                device=0 if settings.QWENCLEO_DEVICE == "cuda" else -1,
                chunk_length_s=30,
                stride_length_s=5,
                return_timestamps=False,
            )
            logger.info("QwenCleo-ASR ready ✓")
        except ImportError:
            logger.error("transformers not installed. Run: pip install transformers")
            self._pipeline = "disabled"
        except Exception as e:
            logger.error(f"QwenCleo load error: {e}")
            self._pipeline = "disabled"

    async def transcribe(self, audio_bytes: bytes) -> str:
        await self._ensure_loaded()
        if self._pipeline == "disabled":
            return ""

        loop = asyncio.get_event_loop()
        return await run_in_audio_thread(self._run, audio_bytes)

    def _run(self, audio_bytes: bytes) -> str:
        try:
            import numpy as np
            import soundfile as sf  # type: ignore[import]
            import io

            audio_array, sample_rate = sf.read(io.BytesIO(audio_bytes))
            if audio_array.ndim > 1:
                audio_array = audio_array.mean(axis=1)  # stereo → mono

            result = self._pipeline(
                {"raw": audio_array, "sampling_rate": sample_rate}
            )
            return result.get("text", "").strip()
        except Exception as e:
            logger.error(f"QwenCleo transcription error: {e}")
            return ""
