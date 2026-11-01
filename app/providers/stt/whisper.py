"""
Whisper STT Provider — Fast, in-memory, thread-safe Speech-to-Text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses OpenAI's Whisper model (runs locally on CUDA GPU or CPU).
Features:
- Pure in-memory transcription directly from numpy arrays (avoids disk I/O and ffmpeg subprocesses).
- Thread-safety locks for concurrent multithreaded chunk processing.
- Automatic fallback to disk/ffmpeg only for exotic compressed formats.
"""

import asyncio
import io
import os
import sys
import tempfile
import threading
from pathlib import Path

import numpy as np
import soundfile as sf

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
    """Local OpenAI Whisper STT with CUDA acceleration, singleton caching, and in-memory execution."""

    _shared_model = None
    _shared_device = None
    _shared_lock = asyncio.Lock()
    _shared_thread_lock = threading.Lock()
    _shared_infer_lock = threading.Lock()

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
        with WhisperProvider._shared_thread_lock:
            if WhisperProvider._shared_model is not None:
                return
            try:
                import torch
                import whisper

                _ensure_ffmpeg()

                device = getattr(settings, "WHISPER_DEVICE", "cuda")
                if device == "cuda" and not torch.cuda.is_available():
                    logger.warning("CUDA requested for Whisper but not available. Falling back to CPU.")
                    device = "cpu"

                download_root = r"D:\models\whisper" if os.path.exists("D:\\") else None
                model_to_load = self._model_size
                if model_to_load in ("turbo", "large-v3-turbo") and download_root:
                    turbo_file = Path(download_root) / "large-v3-turbo.pt"
                    if not turbo_file.exists() or turbo_file.stat().st_size < 1500 * 1024 * 1024:
                        curr_mb = turbo_file.stat().st_size / (1024 * 1024) if turbo_file.exists() else 0
                        logger.info(f"Turbo model is downloading ({curr_mb:.0f}/1510 MB). Using fast high-accuracy 'small' model temporarily...")
                        model_to_load = "small"

                logger.info(f"Loading Whisper STT model '{model_to_load}' on {device}...")
                loaded_model = whisper.load_model(model_to_load, device=device, download_root=download_root)
                WhisperProvider._shared_model = loaded_model
                WhisperProvider._shared_device = device
                logger.info(f"Whisper STT model '{model_to_load}' ready on {device} ✓")
            except ImportError:
                logger.error("openai-whisper not installed. Run: pip install openai-whisper")
                WhisperProvider._shared_model = "disabled"
            except Exception as e:
                logger.error(f"Whisper load error: {e}")
                WhisperProvider._shared_model = "disabled"

    def transcribe_array(self, audio_array: np.ndarray, sample_rate: int = 16000) -> str:
        """
        Transcribe an in-memory numpy float32 audio array directly.
        Bypasses disk writes and ffmpeg subprocesses completely.
        """
        if self._model is None or self._model == "disabled":
            self._load()

        if len(audio_array) == 0:
            return ""

        if audio_array.ndim > 1:
            audio_array = audio_array.mean(axis=1)

        audio_array = audio_array.astype(np.float32)

        # Fast in-memory resample to 16,000 Hz using scipy (5ms vs 6s in librosa)
        if sample_rate != 16000:
            try:
                import scipy.signal
                audio_array = scipy.signal.resample_poly(audio_array, 16000, sample_rate).astype(np.float32)
            except Exception as resample_err:
                logger.debug(f"Resample warning: {resample_err}")

        lang = getattr(settings, "WHISPER_LANGUAGE", "ar")
        device = WhisperProvider._shared_device or "cpu"
        use_fp16 = (device == "cuda")

        with WhisperProvider._shared_infer_lock:
            result = self._model.transcribe(
                audio_array,
                language=lang,
                fp16=use_fp16,
                beam_size=1,
                best_of=1,
                temperature=0.0,
                condition_on_previous_text=False,
            )
        return result.get("text", "").strip()

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
        """Decode audio in memory and transcribe without subprocess calls."""
        _ensure_ffmpeg()

        # Try fast in-memory soundfile decoding first
        try:
            with io.BytesIO(audio_bytes) as bio:
                audio_array, sample_rate = sf.read(bio)
            return self.transcribe_array(audio_array, sample_rate)
        except Exception:
            pass

        # Fallback to temp file path for exotic compressed formats
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio_bytes)
                tmp_path = f.name

            lang = getattr(settings, "WHISPER_LANGUAGE", "ar")
            device = WhisperProvider._shared_device or "cpu"
            use_fp16 = (device == "cuda")

            with WhisperProvider._shared_infer_lock:
                result = self._model.transcribe(
                    tmp_path,
                    language=lang,
                    fp16=use_fp16,
                    beam_size=1,
                    best_of=1,
                    temperature=0.0,
                    condition_on_previous_text=False,
                )
            return result.get("text", "").strip()
        except Exception as e:
            logger.error(f"Whisper transcription error: {e}")
            raise RuntimeError(f"Whisper transcription failed: {e}")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
