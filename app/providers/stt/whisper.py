"""
Whisper STT provider.
Not the primary choice for Egyptian Arabic (QwenCleo outperforms it by 64 % WER
on Egyptian test sets — doc §6.1), but useful as a backup.
"""

import asyncio
from app.providers.tts.base import BaseSTTProvider
from app.core.logger import get_logger
from app.core.threading import run_in_audio_thread

logger = get_logger(__name__)


class WhisperProvider(BaseSTTProvider):
    """OpenAI Whisper large-v3 STT provider."""

    def __init__(self):
        self._model = None
        self._lock = asyncio.Lock()

    async def _ensure_loaded(self):
        if self._model is not None:
            return
        async with self._lock:
            if self._model is None:
                import asyncio as _asyncio
                loop = _asyncio.get_event_loop()
                await run_in_audio_thread(self._load)

    def _load(self):
        try:
            import whisper  # type: ignore[import]
            self._model = whisper.load_model("large-v3")
            logger.info("Whisper large-v3 loaded ✓")
        except ImportError:
            logger.error("openai-whisper not installed. Run: pip install openai-whisper")
            self._model = "disabled"

    async def transcribe(self, audio_bytes: bytes) -> str:
        await self._ensure_loaded()
        if self._model == "disabled":
            return ""

        import tempfile, os
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name
        try:
            loop = asyncio.get_event_loop()
            result = await run_in_audio_thread(self._model.transcribe, tmp, language="ar")



            return result.get("text", "").strip()
        finally:
            os.unlink(tmp)
