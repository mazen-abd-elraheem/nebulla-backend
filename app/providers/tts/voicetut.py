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
import os
from pathlib import Path
import wave
import torch
from app.providers.tts.base import BaseTTSProvider
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class VoiceTutProvider(BaseTTSProvider):
    """VoiceTut-TTS: OmniVoice fine-tuned on Egyptian Arabic podcasts."""

    _shared_tts = None
    _shared_device = None
    _shared_lock = asyncio.Lock()

    def __init__(self, speaker: str | None = None):
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
        """Return available cloned Egyptian speakers."""
        from pathlib import Path
        samples_dir = Path("data/voice_samples")
        speakers: list[str] = []
        if samples_dir.exists():
            for wav in sorted(samples_dir.glob("personality_*.wav")):
                pid = wav.stem.replace("personality_", "")
                speakers.append(f"personality_{pid}")
            for wav in sorted(samples_dir.glob("*.wav")):
                stem = wav.stem
                if (
                    not stem.startswith("personality_")
                    and not stem.startswith("api_")
                    and stem not in ("cloned_test", "mazen_test_result", "latest_synthesized")
                ):
                    speakers.append(stem)

        if not speakers:
            speakers = ["mazen", "personality_1"]
        elif "personality_1" in speakers and "mazen" not in speakers:
            speakers.insert(0, "mazen")

        return sorted(list(set(speakers)))

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
            raise RuntimeError(
                "VoiceTut-TTS engine is unavailable or disabled. Check logs for initialization errors."
            )

        loop = asyncio.get_event_loop()
        res = await loop.run_in_executor(
            None,
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
            raise RuntimeError(
                f"VoiceTut-TTS returned empty or corrupt audio ({len(res) if res else 0} bytes)."
            )
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

            # Resolve speaker to cloned audio sample if ref_audio was not explicitly provided
            if not target_ref_audio:
                spk = speaker or self._speaker
                if spk:
                    spk_str = str(spk).strip()
                    if os.path.exists(spk_str):
                        target_ref_audio = spk_str
                    else:
                        samples_dir = Path("data/voice_samples")
                        if samples_dir.exists():
                            if spk_str.isdigit():
                                cand = samples_dir / f"personality_{spk_str}.wav"
                                if cand.exists():
                                    target_ref_audio = str(cand)
                            elif spk_str.startswith("personality_"):
                                cand = samples_dir / f"{spk_str}.wav"
                                if cand.exists():
                                    target_ref_audio = str(cand)
                            elif spk_str.lower() == "mazen":
                                cand = samples_dir / "personality_1.wav"
                                if cand.exists():
                                    target_ref_audio = str(cand)
                            else:
                                cand = samples_dir / f"{spk_str}.wav"
                                if cand.exists():
                                    target_ref_audio = str(cand)

            if not target_ref_audio or not os.path.exists(target_ref_audio):
                default_ref = Path(settings.DEFAULT_VOICE_SAMPLE)
                if default_ref.exists():
                    target_ref_audio = str(default_ref.resolve())

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

            # Denoising steps from settings (defaults: 48 for Studio quality)
            default_steps = getattr(settings, "VOICETUT_NUM_STEPS", 48)
            steps = num_step or default_steps
            cfg = guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.6)
            spd = speed or getattr(settings, "VOICETUT_SPEED", 1.15)
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
                    spk = speaker or self._speaker or "Mohammed"
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
            logger.error(f"VoiceTut synthesis error: {e}", exc_info=True)
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise RuntimeError(f"VoiceTut-TTS synthesis execution failed: {e}") from e


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

