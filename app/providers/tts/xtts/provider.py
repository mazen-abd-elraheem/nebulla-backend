"""
XTTS Voice Clone Provider — Powered exclusively by VoiceTut-TTS (Egyptian Arabic)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Primary voice cloning engine fine-tuned for Egyptian Arabic (arz).
Provides high-fidelity zero-shot voice cloning, fast streaming synthesis,
and instant (0ms) pre-cached connection greetings with the cloned voice.
"""

from __future__ import annotations

import asyncio
import io
import os
import wave
from pathlib import Path
from typing import AsyncIterator, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.tts.base import BaseTTSProvider
from app.utils.masri_normalizer import clean_llm_output_for_speech

logger = get_logger(__name__)


def _array_to_wav(samples, sample_rate: int = 24000) -> bytes:
    """Convert float numpy array to 16-bit PCM WAV bytes."""
    import numpy as np

    pcm = (samples * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


class XTTSProvider(BaseTTSProvider):
    """
    Primary Zero-Shot Voice Cloning TTS Provider for Nebula.
    Powered strictly by VoiceTut-TTS with full Egyptian Arabic dialect and code-switching support.
    """

    _shared_tts = None
    _shared_device = None
    _shared_lock = asyncio.Lock()

    def __init__(
        self,
        reference_wav: Optional[str] = None,
        language: str = "arz",
        device: Optional[str] = None,
        speaker: Optional[str] = None,
    ):
        self._reference_wav = reference_wav or str(
            Path("data/voice_samples/personality_1.wav").resolve()
        )
        self._language = language or "arz"
        self._device = device or getattr(settings, "VOICETUT_DEVICE", "cuda")
        self._speaker = speaker or getattr(settings, "VOICETUT_SPEAKER", "mazen")

    # ── Greeting Cache Management ─────────────────────────────────────────────

    @staticmethod
    def get_greeting_cache_path(personality_id: int) -> Path:
        """Returns the file path for pre-cached cloned greeting audio."""
        return Path("data/voice_samples") / f"greeting_personality_{personality_id}.wav"

    def get_cached_greeting(self, personality_id: int) -> Optional[bytes]:
        """Fetch pre-cached greeting audio if available on disk (0ms latency)."""
        cache_file = self.get_greeting_cache_path(personality_id)
        if cache_file.exists():
            try:
                return cache_file.read_bytes()
            except Exception as e:
                logger.warning(f"Could not read greeting cache: {e}")
        return None

    async def precache_greeting(
        self,
        personality_id: int,
        text: str,
        sample_path: Optional[str] = None,
    ) -> bytes:
        """
        Synthesize greeting with the cloned speaker voice and persist to disk cache.
        """
        ref_wav = sample_path or str(Path("data/voice_samples") / f"personality_{personality_id}.wav")
        clean_text = clean_llm_output_for_speech(text) or text.strip()
        logger.info(f"Pre-caching cloned voice greeting for personality {personality_id}...")
        wav_bytes = await self.synthesize(
            text=clean_text,
            ref_audio=ref_wav,
            speaker=self._speaker,
            language=self._language,
        )
        try:
            cache_file = self.get_greeting_cache_path(personality_id)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(wav_bytes)
            logger.info(f"Cloned greeting successfully cached at {cache_file} ({len(wav_bytes)} bytes)")
        except Exception as e:
            logger.warning(f"Failed to persist greeting cache to disk: {e}")
        return wav_bytes

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    @staticmethod
    def _is_service_ready(host: str = "127.0.0.1", port: int = 8001) -> bool:
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                return s.connect_ex((host, port)) == 0
        except Exception:
            return False

    @staticmethod
    def _ensure_service_running() -> bool:
        if XTTSProvider._is_service_ready():
            return True
        tut_dir = Path(r"C:\Users\L0Q\Desktop\tut-voice")
        python_exe = tut_dir / ".venv" / "Scripts" / "python.exe"
        uvicorn_exe = tut_dir / ".venv" / "Scripts" / "uvicorn.exe"
        cmd = None
        if python_exe.exists():
            cmd = [str(python_exe), "-m", "uvicorn", "server:app", "--host", "127.0.0.1", "--port", "8001"]
        elif uvicorn_exe.exists():
            cmd = [str(uvicorn_exe), "server:app", "--host", "127.0.0.1", "--port", "8001"]

        if cmd:
            try:
                import subprocess
                logger.info("Auto-starting VoiceTut GPU microservice on http://127.0.0.1:8001 ...")
                subprocess.Popen(
                    cmd,
                    cwd=str(tut_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                return True
            except Exception as e:
                logger.error(f"Failed to auto-start VoiceTut microservice: {e}")
        return False

    @classmethod
    async def _wait_for_service(cls, timeout: float = 15.0) -> bool:
        """Check if microservice is ready, or start it and wait up to timeout seconds."""
        if cls._is_service_ready():
            return True
        if cls._ensure_service_running():
            import time
            start = time.time()
            while time.time() - start < timeout:
                if cls._is_service_ready():
                    return True
                await asyncio.sleep(0.5)
        return cls._is_service_ready()

    async def load(self) -> None:
        """Ensure microservice or in-process model is loaded and ready."""
        if await self._wait_for_service(timeout=15.0):
            return
        await self._ensure_in_process_loaded()

    async def _ensure_in_process_loaded(self) -> None:
        """Load in-process VoiceTut model if not already instantiated."""
        if XTTSProvider._shared_tts is not None and not isinstance(XTTSProvider._shared_tts, str):
            return
        async with XTTSProvider._shared_lock:
            if XTTSProvider._shared_tts is None or isinstance(XTTSProvider._shared_tts, str):
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._load_sync)

    def _load_sync(self) -> None:
        """Load VoiceTut-TTS model in background executor thread."""
        try:
            import os
            import torch

            os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
            try:
                import omnivoice  # noqa: F401
            except Exception:
                pass
            from voicetut_tts import VoiceTutTTS

            device = self._device
            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA requested for XTTS/VoiceTut but unavailable. Using CPU.")
                device = "cpu"

            if device == "cuda":
                torch.cuda.empty_cache()

            candidate_paths = [
                Path(getattr(settings, "VOICETUT_MODEL_PATH", "models/voicetut-tts")),
                Path("models/voicetut-tts"),
                Path(r"D:\models\voicetut-tts"),
                Path(r"C:\Users\L0Q\Desktop\tut-voice\models\voicetut-tts"),
            ]
            model_target = "mohammedaly22/VoiceTut-TTS"
            for cp in candidate_paths:
                if cp.exists() and (cp / "model.safetensors").exists():
                    model_target = str(cp.resolve())
                    break

            logger.info(f"Loading XTTS (VoiceTut-TTS engine) from {model_target} on {device.upper()}…")
            XTTSProvider._shared_tts = VoiceTutTTS.from_pretrained(
                model_target,
                device=device,
                dtype="float32" if device == "cpu" else "bfloat16",
            )
            if device == "cpu" and hasattr(XTTSProvider._shared_tts, "model"):
                try:
                    XTTSProvider._shared_tts.model.float()
                except Exception:
                    pass
            XTTSProvider._shared_device = device
            logger.info(f"XTTS (VoiceTut-TTS) ready on {device.upper()} [OK]")
        except Exception as e:
            err_str = str(e).lower()
            if device != "cpu" and ("out of memory" in err_str or "cuda" in err_str):
                logger.warning(f"CUDA memory insufficient for VoiceTut ({e}). Falling back to CPU...")
                try:
                    import torch
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    XTTSProvider._shared_tts = VoiceTutTTS.from_pretrained(
                        model_target,
                        device="cpu",
                        dtype="float32",
                    )
                    XTTSProvider._shared_device = "cpu"
                    logger.info("XTTS (VoiceTut-TTS) ready on CPU [OK]")
                    return
                except Exception as cpu_err:
                    logger.error(f"Failed to load VoiceTut on CPU fallback: {cpu_err}", exc_info=True)
            logger.error(f"Failed to load in-process XTTS (VoiceTut-TTS): {e}", exc_info=True)
            XTTSProvider._shared_tts = None

    # ── BaseTTSProvider Interface ─────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        speaker: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        speed: Optional[float] = None,
        language: Optional[str] = None,
    ) -> bytes:
        """
        Synthesize text using the cloned speaker voice.
        Returns raw WAV bytes ready for streaming to client.
        """
        clean_text = clean_llm_output_for_speech(text) or text.strip()

        # Primary: VoiceTut-TTS GPU microservice (runs isolated on port 8001)
        if await self._wait_for_service(timeout=1.5):
            try:
                from app.providers.tts.voicetut_microservice import VoiceTutMicroserviceProvider
                svc = VoiceTutMicroserviceProvider()
                return await svc.synthesize(
                    text=clean_text,
                    speaker=speaker or self._speaker,
                    ref_audio=ref_audio or self._reference_wav,
                    ref_text=ref_text,
                    num_step=num_step,
                    guidance_scale=guidance_scale,
                    speed=speed,
                    language=language or self._language,
                )
            except Exception as svc_err:
                logger.warning(f"VoiceTut microservice call failed: {svc_err}. Attempting in-process fallback...")

        # Secondary: In-process fallback
        await self._ensure_in_process_loaded()

        if XTTSProvider._shared_tts is not None and not isinstance(XTTSProvider._shared_tts, str):
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None,
                self._synth_sync,
                clean_text,
                speaker,
                ref_audio,
                ref_text,
                num_step,
                guidance_scale,
                speed,
                language,
            )

        # Tertiary: VoiceTutMicroservice fallback (gTTS / Windows SAPI Arabic voice generator)
        from app.providers.tts.voicetut_microservice import VoiceTutMicroserviceProvider
        svc = VoiceTutMicroserviceProvider()
        return await svc.synthesize(
            text=clean_text,
            speaker=speaker or self._speaker,
            ref_audio=ref_audio or self._reference_wav,
            ref_text=ref_text,
            num_step=num_step,
            guidance_scale=guidance_scale,
            speed=speed,
            language=language or self._language,
        )

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Streaming synthesis yielding WAV chunks."""
        wav_bytes = await self.synthesize(text)
        chunk_size = 4096
        for i in range(0, len(wav_bytes), chunk_size):
            yield wav_bytes[i : i + chunk_size]
            await asyncio.sleep(0)

    # ── Voice Cloning Helpers ─────────────────────────────────────────────────

    async def clone_voice(
        self,
        reference_wav: str,
        text: str,
        language: str = "arz",
        ref_text: Optional[str] = None,
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        speed: Optional[float] = None,
    ) -> bytes:
        """Clone voice from specified reference audio."""
        return await self.synthesize(
            text=text,
            ref_audio=reference_wav,
            ref_text=ref_text,
            num_step=num_step,
            guidance_scale=guidance_scale,
            speed=speed,
            language=language,
        )

    def set_reference_voice(self, wav_path: str) -> None:
        """Update active speaker reference voice."""
        p = Path(wav_path)
        if not p.exists():
            raise FileNotFoundError(f"Reference voice audio not found: {wav_path}")
        self._reference_wav = str(p.resolve())
        logger.info(f"XTTS reference voice updated → {self._reference_wav}")

    # ── Internal Synthesis Routine ───────────────────────────────────────────

    def _synth_sync(
        self,
        text: str,
        speaker: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        speed: Optional[float] = None,
        language: Optional[str] = None,
    ) -> bytes:
        try:
            import torch
            try:
                import omnivoice  # noqa: F401
            except Exception:
                pass
            from voicetut_tts import GenerationParams

            if XTTSProvider._shared_tts is None or isinstance(XTTSProvider._shared_tts, str):
                raise RuntimeError("In-process VoiceTut-TTS engine is not instantiated.")

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Resolve target reference audio
            target_ref_audio = ref_audio or self._reference_wav
            if not target_ref_audio or not os.path.exists(target_ref_audio):
                default_ref = Path("data/voice_samples/personality_1.wav")
                if default_ref.exists():
                    target_ref_audio = str(default_ref.resolve())

            # Attempt to read transcript for reference audio if available
            actual_ref_text = ref_text
            if not actual_ref_text and target_ref_audio:
                txt_file = Path(target_ref_audio).with_suffix(".txt")
                if txt_file.exists():
                    try:
                        actual_ref_text = txt_file.read_text(encoding="utf-8").strip()
                    except Exception:
                        pass

            steps = num_step or getattr(settings, "VOICETUT_NUM_STEPS", 32)
            cfg = guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.2)
            spd = speed or getattr(settings, "VOICETUT_SPEED", 1.0)
            lang = language or self._language or getattr(settings, "VOICETUT_LANGUAGE", "arz")

            params = GenerationParams(
                num_step=steps,
                guidance_scale=cfg,
                speed=spd,
                denoise=True,
            )

            if XTTSProvider._shared_device == "cpu" and hasattr(XTTSProvider._shared_tts, "model"):
                try:
                    XTTSProvider._shared_tts.model.float()
                except Exception:
                    pass

            with torch.inference_mode():
                if target_ref_audio and os.path.exists(target_ref_audio):
                    wav_samples = XTTSProvider._shared_tts.synthesize(
                        text=text,
                        ref_audio=target_ref_audio,
                        ref_text=actual_ref_text,
                        language=lang,
                        normalize=True,
                        params=params,
                    )
                else:
                    spk = speaker or self._speaker or "Mohammed"
                    wav_samples = XTTSProvider._shared_tts.synthesize(
                        text=text,
                        speaker=spk,
                        language=lang,
                        normalize=True,
                        params=params,
                    )

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            sr = getattr(XTTSProvider._shared_tts, "sampling_rate", 24000)
            return _array_to_wav(wav_samples, sample_rate=sr)
        except Exception as e:
            logger.error(f"XTTS synthesis error: {e}", exc_info=True)
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            raise RuntimeError(f"XTTS synthesis execution failed: {e}") from e
