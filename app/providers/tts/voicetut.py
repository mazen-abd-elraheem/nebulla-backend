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

    _shared_tts = None
    _shared_device = None
    _shared_lock = asyncio.Lock()

    def __init__(self, speaker: str = "Mohammed"):
        self._speaker = speaker

    @property
    def _tts(self):
        return VoiceTutProvider._shared_tts

    @_tts.setter
    def _tts(self, val):
        VoiceTutProvider._shared_tts = val

    @property
    def _device(self):
        return VoiceTutProvider._shared_device or "cpu"

    @_device.setter
    def _device(self, val):
        VoiceTutProvider._shared_device = val

    async def _ensure_loaded(self):
        if VoiceTutProvider._shared_tts is not None:
            return
        async with VoiceTutProvider._shared_lock:
            if VoiceTutProvider._shared_tts is None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._load)

    def _load(self):
        try:
            import os
            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
            from voicetut_tts import VoiceTutTTS
            import torch

            device = settings.VOICETUT_DEVICE
            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA requested for VoiceTut but not available. Falling back to CPU.")
                device = "cpu"

            if device == "cuda":
                torch.cuda.empty_cache()

            from pathlib import Path
            model_path = str(Path(settings.VOICETUT_MODEL_PATH).resolve())
            logger.info(f"Loading VoiceTut-TTS from {model_path} on {device}…")
            VoiceTutProvider._shared_tts = VoiceTutTTS.from_pretrained(
                model_path,
                device=device,
                dtype="float32" if device == "cpu" else "float16",
            )
            VoiceTutProvider._shared_device = device
            logger.info("VoiceTut-TTS ready [OK]")
        except ImportError:
            logger.error("voicetut_tts not installed.")
            VoiceTutProvider._shared_tts = "disabled"
        except Exception as e:
            logger.error(f"VoiceTut load error: {e} — falling back")
            VoiceTutProvider._shared_tts = "disabled"

    @classmethod
    def list_speakers(cls) -> list[str]:
        """Return available pre-built Egyptian speakers."""
        from pathlib import Path
        ref_dir = Path(settings.VOICETUT_MODEL_PATH) / "reference_speakers"
        if ref_dir.exists():
            wavs = [p.stem for p in ref_dir.glob("*.wav")]
            if wavs:
                return sorted(wavs)
        return [
            "ahmed", "ali", "hadeer", "hanan", "hassan", "karim", "mahmoud",
            "mariam", "mohammed", "mostafa", "ramy", "rana", "sarah", "shaker",
            "tarek", "yara", "yasmin", "yehia", "youssef"
        ]

    async def synthesize(
        self,
        text: str,
        speaker: str | None = None,
        ref_audio: str | None = None,
        ref_text: str | None = None,
        num_step: int | None = None,
    ) -> bytes:
        await self._ensure_loaded()
        if self._tts == "disabled" or self._tts is None:
            raise RuntimeError("VoiceTut-TTS model is not available or failed to load. Generic fallback voices are disabled.")

        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(None, self._synth, text, speaker, ref_audio, ref_text, num_step)
        if not res or len(res) <= 1000:
            raise RuntimeError("VoiceTut-TTS returned empty audio. Generic fallback voices are disabled.")
        return res

    def _synth(
        self,
        text: str,
        speaker: str | None = None,
        ref_audio: str | None = None,
        ref_text: str | None = None,
        num_step: int | None = None,
    ) -> bytes:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Denoising steps from settings (defaults: 6 for CPU, 10 for CUDA, or user override)
            default_steps = 6 if getattr(self, "_device", "cpu") == "cpu" else 10
            steps = num_step if (num_step and num_step > 0) else getattr(settings, "VOICETUT_NUM_STEPS", default_steps)
            if not steps or steps <= 0:
                steps = default_steps

            if not ref_audio:
                raise ValueError("ref_audio (cloned voice sample) is required. Pre-built speakers and fallbacks are disabled.")

            actual_ref_text = ref_text if (ref_text and ref_text.strip() and ref_text.strip() != "string") else None
            if not actual_ref_text:
                from pathlib import Path
                txt_file = Path(ref_audio).with_suffix(".txt")
                if txt_file.exists():
                    try:
                        actual_ref_text = txt_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass

            with torch.inference_mode():
                wav_samples = self._tts.synthesize(
                    text=text,
                    ref_audio=ref_audio,
                    ref_text=actual_ref_text,
                    num_step=steps,
                )
            sr = getattr(self._tts, "sampling_rate", 24000)
            return _array_to_wav(wav_samples, sample_rate=sr)
        except Exception as e:
            logger.error(f"VoiceTut synthesis error: {e}")
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Retry once with fast 4 steps if steps was > 4
            if ref_audio and steps != 4:
                try:
                    logger.info("Retrying voice clone with 4 steps to fit in GPU memory...")
                    with torch.inference_mode():
                        wav_samples = self._tts.synthesize(
                            text=text,
                            ref_audio=ref_audio,
                            ref_text=actual_ref_text,
                            num_step=4,
                        )
                    sr = getattr(self._tts, "sampling_rate", 24000)
                    return _array_to_wav(wav_samples, sample_rate=sr)
                except Exception as retry_err:
                    logger.error(f"Voice clone retry failed: {retry_err}")

            # NO FALLBACKS
            raise RuntimeError(f"Voice clone failed via VoiceTut: {e}")


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
