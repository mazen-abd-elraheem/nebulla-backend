"""
Groq STT Provider — Ultra-low latency Cloud Speech-to-Text (<200ms)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Uses Groq's LPU inference running Whisper Large v3 Turbo.
Free tier available at console.groq.com.
"""

import io
import httpx

from app.providers.tts.base import BaseSTTProvider
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


class GroqSTTProvider(BaseSTTProvider):
    """Ultra-fast cloud ASR using Groq Whisper API."""

    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or getattr(settings, "GROQ_API_KEY", "") or getattr(settings, "LLM_API_KEY", "")
        self._base_url = "https://api.groq.com/openai/v1/audio/transcriptions"

    async def transcribe(self, audio_bytes: bytes) -> str:
        if not self._api_key:
            logger.warning("GROQ_API_KEY not set, falling back to local Whisper STT.")
            from app.providers.stt.whisper import WhisperProvider
            return await WhisperProvider().transcribe(audio_bytes)

        try:
            files = {
                "file": ("audio.wav", io.BytesIO(audio_bytes), "audio/wav"),
            }
            data = {
                "model": "whisper-large-v3-turbo",
                "language": getattr(settings, "WHISPER_LANGUAGE", "ar"),
                "temperature": 0.0,
            }
            headers = {
                "Authorization": f"Bearer {self._api_key}",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self._base_url, headers=headers, data=data, files=files)
                resp.raise_for_status()
                result = resp.json()
                return result.get("text", "").strip()
        except Exception as e:
            logger.error(f"Groq STT transcription error: {e} — falling back to local Whisper")
            from app.providers.stt.whisper import WhisperProvider
            return await WhisperProvider().transcribe(audio_bytes)

