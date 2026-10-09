"""
ar-EG Free TTS provider — free Arabic cloud service (doc §6.1 backup plan).
Used when no GPU is available for VoiceTut/XTTS.
"""

import asyncio
import httpx
from app.providers.tts.base import BaseTTSProvider
from app.core.logger import get_logger

logger = get_logger(__name__)

# Google Translate TTS (ar-EG) — public, no API key, rate-limited
_GTTS_URL = "https://translate.google.com/translate_tts"


class ArEgFreeProvider(BaseTTSProvider):
    """Fallback TTS using Google TTS ar-EG voice (no GPU needed)."""

    async def synthesize(self, text: str) -> bytes:
        try:
            from gtts import gTTS  # type: ignore[import]
            import io

            loop = asyncio.get_event_loop()
            mp3_bytes = await loop.run_in_executor(None, self._synth, text)
            return mp3_bytes
        except ImportError:
            logger.error("gTTS not installed. Run: pip install gTTS")
            return b""

    def _synth(self, text: str) -> bytes:
        from gtts import gTTS
        import io
        tts = gTTS(text=text, lang="ar", tld="com.eg")
        buf = io.BytesIO()
        tts.write_to_fp(buf)
        return buf.getvalue()
