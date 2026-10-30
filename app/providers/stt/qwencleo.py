"""
QwenCleo ASR Provider — Egyptian Arabic Speech-to-Text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fine-tune of Qwen3-ASR-1.7B specialised for Egyptian Arabic.
WER ≈ 19.9 % on a 3,699-sentence Egyptian test set (doc §6.1).
License: Apache-2.0.
"""

import asyncio
from pathlib import Path

from app.providers.tts.base import BaseSTTProvider
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class QwenCleoProvider(BaseSTTProvider):
    """Egyptian Arabic ASR via QwenCleo-ASR (Qwen3-ASR-1.7B fine-tune)."""

    _shared_pipeline = None
    _shared_lock = asyncio.Lock()
    _shared_error: str | None = None

    async def _ensure_loaded(self):
        if QwenCleoProvider._shared_pipeline is not None:
            return
        async with QwenCleoProvider._shared_lock:
            if QwenCleoProvider._shared_pipeline is None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._load)

    def _load(self):
        try:
            import torch
            from transformers import pipeline as hf_pipeline  # type: ignore[import]

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
            QwenCleoProvider._shared_pipeline = hf_pipeline(
                task="automatic-speech-recognition",
                model=model_path,
                device=device_idx,
                chunk_length_s=30,
                stride_length_s=5,
                return_timestamps=False,
                trust_remote_code=True,
            )
            QwenCleoProvider._shared_error = None
            logger.info("QwenCleo-ASR ready ✓")
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
        return await loop.run_in_executor(None, self._run, audio_bytes)

    def _run(self, audio_bytes: bytes) -> str:
        import io
        import soundfile as sf  # type: ignore[import]

        try:
            audio_array, sample_rate = sf.read(io.BytesIO(audio_bytes))
            if audio_array.ndim > 1:
                audio_array = audio_array.mean(axis=1)  # stereo → mono

            result = QwenCleoProvider._shared_pipeline(
                {"raw": audio_array, "sampling_rate": sample_rate}
            )
            text = result.get("text", "").strip()
            return text
        except Exception as e:
            logger.error(f"QwenCleo transcription execution error: {e}", exc_info=True)
            raise RuntimeError(f"QwenCleo transcription error: {e}") from e

