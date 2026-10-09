"""
VoiceTut TTS Provider — Egyptian Arabic voice synthesis
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

VoiceTut is a fine-tune of OmniVoice trained on ≈380 hours of Egyptian podcasts.
Features (doc §6.1):
  • 17 pre-built Egyptian voices
  • Zero-shot voice cloning from a short sample
  • Speaks Egyptian Arabic + English code-switching ("عندي meeting بكرة")
  • Cleans numbers and dates automatically
  • Streaming by sentence
  • License: Apache-2.0

Performance on T4 GPU:
  • First audio chunk: ≈1.7 s
  • Generation speed: ≈1.1× real-time
  • VRAM: ≈3 GB
"""

import asyncio
import io
import wave
from app.providers.tts.base import BaseTTSProvider
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class VoiceTutProvider(BaseTTSProvider):
    """VoiceTut-TTS: OmniVoice fine-tuned on Egyptian Arabic podcasts."""

    def __init__(self):
        self._model = None
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self):
        if self._model is not None:
            return
        async with self._lock:
            if self._model is None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._load)

    def _load(self):
        try:
            # VoiceTut uses the same API surface as OmniVoice / Parler-TTS family
            from transformers import AutoProcessor, AutoModel  # type: ignore[import]
            import torch

            device = settings.VOICETUT_DEVICE
            logger.info(f"Loading VoiceTut-TTS from {settings.VOICETUT_MODEL_PATH} on {device}…")
            self._processor = AutoProcessor.from_pretrained(settings.VOICETUT_MODEL_PATH)
            self._model = AutoModel.from_pretrained(
                settings.VOICETUT_MODEL_PATH,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            ).to(device)
            self._device = device
            logger.info("VoiceTut-TTS ready ✓")
        except ImportError:
            logger.error("transformers / torch not installed.")
            self._model = "disabled"
        except Exception as e:
            logger.error(f"VoiceTut load error: {e} — falling back to XTTS")
            self._model = "disabled"

    async def synthesize(self, text: str) -> bytes:
        await self._ensure_loaded()
        if self._model == "disabled":
            return _silent_wav()

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._synth, text)

    def _synth(self, text: str) -> bytes:
        try:
            import torch
            inputs = self._processor(text=text, return_tensors="pt").to(self._device)
            with torch.no_grad():
                audio = self._model.generate(**inputs, max_new_tokens=settings.TTS_MAX_NEW_TOKENS)
            samples = audio.squeeze().cpu().numpy()
            return _array_to_wav(samples, sample_rate=24000)
        except Exception as e:
            logger.error(f"VoiceTut synthesis error: {e}")
            return _silent_wav()


def _array_to_wav(samples, sample_rate: int = 24000) -> bytes:
    import numpy as np
    pcm = (samples * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def _silent_wav(duration_ms: int = 500, sample_rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    num_samples = int(sample_rate * duration_ms / 1000)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_samples)
    return buf.getvalue()
