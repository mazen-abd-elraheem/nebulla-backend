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
from app.core.threading import run_in_audio_thread

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
                await run_in_audio_thread(self._load)

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
            local_model = Path(settings.VOICETUT_MODEL_PATH).resolve()
            model_target = str(local_model) if local_model.exists() else "mohammedaly22/VoiceTut-TTS"
            logger.info(f"Loading VoiceTut-TTS from {model_target} on {device}…")
            VoiceTutProvider._shared_tts = VoiceTutTTS.from_pretrained(
                model_target,
                device=device,
                dtype="float32" if device == "cpu" else "float16",
            )
            VoiceTutProvider._shared_device = device
            logger.info(f"VoiceTut-TTS ready on {device.upper()} [OK]")
        except ImportError:
            logger.error("voicetut_tts not installed in environment.")
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
            "mazen", "ahmed", "ali", "hadeer", "hanan", "hassan", "karim", "mahmoud",
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
        guidance_scale: float | None = None,
        speed: float | None = None,
        language: str | None = None,
    ) -> bytes:
        from app.utils.masri_normalizer import clean_llm_output_for_speech
        clean_text = clean_llm_output_for_speech(text) or text.strip()

        await self._ensure_loaded()
        if self._tts == "disabled" or self._tts is None:
            logger.error("VoiceTut is not available or disabled")
            return _silent_wav()

        loop = asyncio.get_event_loop()
        res = await run_in_audio_thread(

            self._synth,
            clean_text,
            speaker,
            ref_audio,
            ref_text,
            num_step,
            guidance_scale,
            speed,
            language,
        )
        if not res or len(res) <= 1000:
            logger.warning("VoiceTut returned empty audio")
            return _silent_wav()
        return res

    async def clone_voice(
        self,
        reference_wav: str,
        text: str,
        language: str = "arz",
        ref_text: str | None = None,
        num_step: int | None = None,
        guidance_scale: float | None = None,
        speed: float | None = None,
    ) -> bytes:
        """Clone voice using reference audio sample with studio fidelity."""
        return await self.synthesize(
            text=text,
            ref_audio=reference_wav,
            ref_text=ref_text,
            num_step=num_step,
            guidance_scale=guidance_scale,
            speed=speed,
            language=language,
        )

    def _synth(
        self,
        text: str,
        speaker: str | None = None,
        ref_audio: str | None = None,
        ref_text: str | None = None,
        num_step: int | None = None,
        guidance_scale: float | None = None,
        speed: float | None = None,
        language: str | None = None,
    ) -> bytes:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            from pathlib import Path
            target_ref_audio = ref_audio
            if not target_ref_audio or not os.path.exists(target_ref_audio):
                default_ref = Path(settings.DEFAULT_VOICE_SAMPLE)
                if default_ref.exists():
                    target_ref_audio = str(default_ref)

            actual_ref_text = ref_text
            if not actual_ref_text and target_ref_audio:
                txt_file = Path(target_ref_audio).with_suffix(".txt")
                if txt_file.exists():
                    try:
                        actual_ref_text = txt_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass
                if not actual_ref_text:
                    default_txt = Path(settings.DEFAULT_VOICE_TRANSCRIPT)
                    if default_txt.exists():
                        try:
                            actual_ref_text = default_txt.read_text(encoding="utf-8").strip()
                        except Exception:
                            pass

            # Denoising steps from settings (defaults: 36 for Studio 99%, or override)
            default_steps = getattr(settings, "VOICETUT_NUM_STEPS", 36)
            steps = num_step or default_steps
            cfg = guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.2)
            spd = speed or getattr(settings, "VOICETUT_SPEED", 1.0)
            lang = language or getattr(settings, "VOICETUT_LANGUAGE", "arz")

            from voicetut_tts import GenerationParams
            params = GenerationParams(
                num_step=steps,
                guidance_scale=cfg,
                speed=spd,
                denoise=True,
            )

            with torch.inference_mode():
                if target_ref_audio and os.path.exists(target_ref_audio):
                    wav_samples = self._tts.synthesize(
                        text=text,
                        ref_audio=target_ref_audio,
                        ref_text=actual_ref_text,
                        language=lang,
                        normalize=True,
                        params=params,
                    )
                else:
                    spk = speaker or self._speaker
                    wav_samples = self._tts.synthesize(
                        text=text,
                        speaker=spk,
                        language=lang,
                        normalize=True,
                        params=params,
                    )

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            sr = getattr(self._tts, "sampling_rate", 24000)
            return _array_to_wav(wav_samples, sample_rate=sr)
        except Exception as e:
            logger.error(f"VoiceTut synthesis error: {e}")
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Retry once with fast 6 steps if CUDA memory was tight
            if target_ref_audio and os.path.exists(target_ref_audio):
                try:
                    logger.info("Retrying voice clone with 6 steps to fit in memory...")
                    from voicetut_tts import GenerationParams
                    fast_params = GenerationParams(num_step=6, guidance_scale=1.8, speed=1.0, denoise=True)
                    with torch.inference_mode():
                        wav_samples = self._tts.synthesize(
                            text=text,
                            ref_audio=target_ref_audio,
                            ref_text=actual_ref_text,
                            language="arz",
                            normalize=True,
                            params=fast_params,
                        )
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    sr = getattr(self._tts, "sampling_rate", 24000)
                    return _array_to_wav(wav_samples, sample_rate=sr)
                except Exception as retry_err:
                    logger.error(f"Voice clone retry failed: {retry_err}")

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
