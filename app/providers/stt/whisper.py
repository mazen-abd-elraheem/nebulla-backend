"""
Whisper STT Provider — Fast and accurate Speech-to-Text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses OpenAI's Whisper model (runs locally on CUDA GPU or CPU).
Optimized for low latency on local hardware with Arabic support.
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from app.providers.tts.base import BaseSTTProvider
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


def _ensure_ffmpeg():
    """Ensure ffmpeg executable is available in PATH for Whisper."""
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        ffmpeg_dir = os.path.dirname(ffmpeg_exe)
        current_path = os.environ.get("PATH", "")
        if ffmpeg_dir not in current_path:
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path

        # Also add venv Scripts directory
        venv_scripts = str(Path(sys.prefix) / "Scripts")
        if os.path.isdir(venv_scripts) and venv_scripts not in os.environ["PATH"]:
            os.environ["PATH"] = venv_scripts + os.pathsep + os.environ["PATH"]
    except Exception as exc:
        logger.debug(f"Could not auto-configure ffmpeg path: {exc}")


class WhisperProvider(BaseSTTProvider):
    """Local OpenAI Whisper STT with CUDA acceleration and singleton caching."""

    _shared_model = None
    _shared_device = None
    _shared_lock = asyncio.Lock()

    def __init__(self, model_size: str | None = None):
        self._model_size = model_size or getattr(settings, "WHISPER_MODEL", "base")
        _ensure_ffmpeg()

    @property
    def _model(self):
        return WhisperProvider._shared_model

    @_model.setter
    def _model(self, val):
        WhisperProvider._shared_model = val

    async def _ensure_loaded(self):
        if WhisperProvider._shared_model is not None:
            return
        async with WhisperProvider._shared_lock:
            if WhisperProvider._shared_model is None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._load)

    def _load(self):
        try:
            import torch
            import whisper

            _ensure_ffmpeg()

            device = getattr(settings, "WHISPER_DEVICE", "cuda")
            if device == "cuda" and not torch.cuda.is_available():
                logger.warning("CUDA requested for Whisper but not available. Falling back to CPU.")
                device = "cpu"

            logger.info(f"Loading Whisper STT model '{self._model_size}' on {device}...")
            loaded_model = whisper.load_model(self._model_size, device=device)
            WhisperProvider._shared_model = loaded_model
            WhisperProvider._shared_device = device
            logger.info(f"Whisper STT model '{self._model_size}' ready on {device} ✓")
        except ImportError:
            logger.error("openai-whisper not installed. Run: pip install openai-whisper")
            WhisperProvider._shared_model = "disabled"
        except Exception as e:
            logger.error(f"Whisper load error: {e}")
            WhisperProvider._shared_model = "disabled"

    async def transcribe(self, audio_bytes: bytes) -> str:
        """Transcribe raw audio bytes to text."""
        await self._ensure_loaded()
        if self._model == "disabled" or self._model is None:
            raise RuntimeError("Whisper STT model failed to load. Check GPU / package installation.")

        if not audio_bytes or len(audio_bytes) < 100:
            return ""

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_transcription, audio_bytes)

    def _run_transcription(self, audio_bytes: bytes) -> str:
        _ensure_ffmpeg()

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name

            lang = getattr(settings, "WHISPER_LANGUAGE", "ar")
            device = WhisperProvider._shared_device or "cpu"
            use_fp16 = (device == "cuda")

            result = self._model.transcribe(
                tmp_path,
                language=lang,
                fp16=use_fp16,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
            )
            text = result.get("text", "").strip()
            return text
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            raise RuntimeError(f"Whisper transcription failed: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
