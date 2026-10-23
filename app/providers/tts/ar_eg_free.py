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
            raw_audio = await loop.run_in_executor(None, self._synth, text)
            return raw_audio
        except ImportError:
            logger.error("gTTS not installed. Run: pip install gTTS")
            from app.providers.tts.voicetut import _silent_wav
            return _silent_wav()

    def _synth(self, text: str) -> bytes:
        try:
            from gtts import gTTS
            import io
            import tempfile
            import subprocess
            import imageio_ffmpeg

            tts = gTTS(text=text, lang="ar", tld="com.eg")
            mp3_buf = io.BytesIO()
            tts.write_to_fp(mp3_buf)
            mp3_bytes = mp3_buf.getvalue()

            # Convert to standard WAV using imageio_ffmpeg
            ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as in_f:
                in_f.write(mp3_bytes)
                in_path = in_f.name

            out_path = in_path.replace(".mp3", ".wav")
            try:
                cmd = [
                    ffmpeg_exe, "-y", "-i", in_path,
                    "-acodec", "pcm_s16le", "-ar", "24000", "-ac", "1",
                    out_path
                ]
                subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
                with open(out_path, "rb") as out_f:
                    return out_f.read()
            finally:
                import os
                for p in (in_path, out_path):
                    if os.path.exists(p):
                        try:
                            os.unlink(p)
                        except OSError:
                            pass
        except Exception as e:
            logger.warning(f"gTTS audio generation / conversion error: {e}")
            from app.providers.tts.voicetut import _silent_wav
            return _silent_wav()


ArEgFreeTTSProvider = ArEgFreeProvider
