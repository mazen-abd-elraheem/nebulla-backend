"""
XTTS v2 Voice Clone Provider
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Uses Coqui XTTS v2 (TTS library) for zero-shot voice cloning:
  - Takes a short reference audio sample (3–10 s is enough)
  - Synthesises speech in the same voice in Egyptian Arabic
  - Supports streaming by sentence for low latency (doc §6.3 target: ~1.7 s first audio)

Install:
    pip install TTS==0.22.0   # Coqui TTS with XTTS v2

Usage:
    provider = XTTSProvider()
    await provider.load()
    audio = await provider.synthesize("أهلاً يا صديقي", reference_wav="samples/my_voice.wav")

Voice cloning workflow (doc §6.1):
    1. Record a clean 30–60 s sample of the user's voice
    2. Store as data/voice_samples/<personality_id>.wav
    3. Pass the path as reference_wav when synthesising
    4. The robot speaks with the user's own voice

Notes:
    • XTTS v2 requires ~3 GB VRAM on GPU or runs (slower) on CPU
    • For Egyptian Arabic: set language="ar" — the model handles code-switching
      (Egyptian + English mix like "عندي meeting بكرة") because it was trained on
      multilingual data with Arabic dialects included
    • OmniVoice / VoiceTut from the doc is a different fine-tune; XTTS v2 gives
      better zero-shot cloning if you have the VRAM budget
"""

import asyncio
import io
import wave
from pathlib import Path
from typing import AsyncIterator

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.tts.base import BaseTTSProvider

logger = get_logger(__name__)

_XTTS_MODEL_NAME = "tts_models/multilingual/multi-dataset/xtts_v2"
_DEFAULT_LANGUAGE = "ar"   # Arabic — model handles Egyptian dialect


class XTTSProvider(BaseTTSProvider):
    """
    Zero-shot voice cloning TTS using Coqui XTTS v2.

    Attributes
    ----------
    reference_wav : str
        Path to the speaker reference audio file (.wav, 3-30 s of clean speech).
    language : str
        BCP-47 language code. Use "ar" for Egyptian Arabic.
    device : str
        "cuda" or "cpu".
    """

    def __init__(
        self,
        reference_wav: str | None = None,
        language: str = _DEFAULT_LANGUAGE,
        device: str | None = None,
    ):
        self._reference_wav = reference_wav or str(
            Path(settings.VOICETUT_MODEL_PATH).parent.parent
            / "voice_samples"
            / "default_voice.wav"
        )
        self._language = language
        self._device = device or settings.VOICETUT_DEVICE
        self._model = None
        self._lock = asyncio.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def load(self) -> None:
        """Lazy-load XTTS v2. Safe to call multiple times."""
        if self._model is not None:
            return
        async with self._lock:
            if self._model is None:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._load_sync)

    def _load_sync(self) -> None:
        """Blocking model load — runs in thread pool."""
        try:
            from TTS.api import TTS  # type: ignore[import]

            logger.info(f"Loading XTTS v2 on {self._device}…")
            self._model = TTS(
                model_name=_XTTS_MODEL_NAME,
                progress_bar=False,
            ).to(self._device)
            logger.info("XTTS v2 ready ✓")
        except ImportError:
            logger.error(
                "Coqui TTS not installed. Run: pip install TTS==0.22.0\n"
                "XTTS voice cloning is DISABLED."
            )
            self._model = "disabled"
        except Exception as exc:
            logger.error(f"XTTS load failed: {exc}")
            self._model = "disabled"

    # ── BaseTTSProvider interface ─────────────────────────────────────────────

    async def synthesize(self, text: str) -> bytes:
        """
        Synthesise *text* in the cloned voice.
        Returns raw WAV bytes ready to stream to the phone.

        Latency note (doc §6.3):
            Keep the first sentence ≤ 8 words so TTS starts within ~1.7 s.
            The pipeline calls this once per sentence, not for the whole response.
        """
        await self.load()

        if self._model == "disabled":
            logger.warning("XTTS disabled — using ar-EG fallback TTS to generate speech")
            from app.providers.tts.ar_eg_free import ArEgFreeProvider
            res = await ArEgFreeProvider().synthesize(text)
            if res and len(res) > 2000:
                return res
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, _fallback_tts_wav, text)

        loop = asyncio.get_event_loop()
        wav_bytes = await loop.run_in_executor(None, self._synth_sync, text)
        return wav_bytes

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """
        Streaming synthesis — yields WAV chunks as they are produced.
        XTTS v2 supports streaming via tts_to_file; we simulate chunking here.
        A true streaming approach requires the 'stream_chunk_size' parameter.
        """
        wav_bytes = await self.synthesize(text)
        chunk_size = 4096
        for i in range(0, len(wav_bytes), chunk_size):
            yield wav_bytes[i : i + chunk_size]
            await asyncio.sleep(0)  # yield control

    # ── Voice cloning helpers ─────────────────────────────────────────────────

    async def clone_voice(
        self,
        reference_wav_path: str,
        text: str,
        language: str | None = None,
    ) -> bytes:
        await self.load()
        if self._model == "disabled" or self._model is None:
            raise RuntimeError("XTTS model is disabled or not installed")
        original_ref = self._reference_wav
        original_lang = self._language
        try:
            self._reference_wav = reference_wav_path
            self._language = language or self._language
            return await self.synthesize(text)
        finally:
            self._reference_wav = original_ref
            self._language = original_lang

    async def set_reference_voice(self, wav_path: str) -> None:
        """
        Swap the active speaker reference at runtime (e.g., personality change).
        Validates that the file exists before accepting it.
        """
        p = Path(wav_path)
        if not p.exists():
            raise FileNotFoundError(f"Reference wav not found: {wav_path}")
        if p.suffix.lower() not in (".wav", ".mp3", ".flac", ".ogg"):
            raise ValueError(f"Unsupported audio format: {p.suffix}")
        self._reference_wav = str(p)
        logger.info(f"XTTS reference voice updated → {wav_path}")

    # ── Private sync helpers ──────────────────────────────────────────────────

    def _synth_sync(self, text: str) -> bytes:
        """Runs in executor thread. Returns WAV bytes."""
        buf = io.BytesIO()
        try:
            wav_array = self._model.tts(
                text=text,
                speaker_wav=self._reference_wav,
                language=self._language,
                split_sentences=True,   # split internally to reduce latency
            )
            # Convert numpy float array → WAV bytes
            import numpy as np
            import struct

            samples = (np.array(wav_array) * 32767).astype(np.int16)
            sample_rate = 24000   # XTTS v2 native sample rate

            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(sample_rate)
                wf.writeframes(samples.tobytes())

        except Exception as exc:
            logger.error(f"XTTS synthesis error: {exc} — using ar-EG fallback")
            try:
                from app.providers.tts.ar_eg_free import ArEgFreeProvider
                return ArEgFreeProvider().synthesize_sync(text)
            except Exception:
                return _silent_wav()

        return buf.getvalue()


# ── Utilities ─────────────────────────────────────────────────────────────────

def _fallback_tts_wav(text: str, language: str = "ar") -> bytes:
    """
    Fallback TTS when XTTS v2 is disabled or not installed.
    Uses high quality Egyptian neural voice (ArEgFreeProvider) with gTTS fallback.
    """
    try:
        from app.providers.tts.ar_eg_free import ArEgFreeProvider
        res = ArEgFreeProvider().synthesize_sync(text)
        if res and len(res) > 2000:
            return res
    except Exception as exc:
        logger.warning(f"ArEgFreeProvider sync failed: {exc}, trying gTTS...")

    try:
        import subprocess
        from gtts import gTTS
        import imageio_ffmpeg

        # Determine language code for gTTS
        lang = language if language in ("ar", "en", "fr") else "ar"
        tld = "com.eg" if lang == "ar" else "com"

        tts = gTTS(text=text, lang=lang, tld=tld)
        mp3_io = io.BytesIO()
        tts.write_to_fp(mp3_io)
        mp3_bytes = mp3_io.getvalue()

        if not mp3_bytes:
            return _silent_wav()

        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        proc = subprocess.Popen(
            [
                ffmpeg_exe,
                "-y",
                "-i", "pipe:0",
                "-f", "wav",
                "-acodec", "pcm_s16le",
                "-ar", "24000",
                "-ac", "1",
                "pipe:1",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        wav_out, err = proc.communicate(input=mp3_bytes)
        if proc.returncode == 0 and len(wav_out) > 0:
            try:
                import soundfile as sf
                data, sr = sf.read(io.BytesIO(wav_out))
                fixed_buf = io.BytesIO()
                sf.write(fixed_buf, data, sr, format="WAV", subtype="PCM_16")
                return fixed_buf.getvalue()
            except Exception:
                return wav_out

        logger.error(f"FFmpeg fallback conversion failed: {err.decode('utf-8', errors='ignore')}")
    except Exception as exc:
        logger.error(f"Fallback TTS failed: {exc}")

    return _silent_wav()


def _silent_wav(duration_ms: int = 500, sample_rate: int = 24000) -> bytes:
    """Return a WAV buffer containing silence — used as a fallback."""
    num_samples = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b"\x00\x00" * num_samples)
    return buf.getvalue()
