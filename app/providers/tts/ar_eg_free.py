"""
ar-EG Free TTS provider — free Arabic cloud service (doc §6.1 backup plan).
Uses high-quality Egyptian Arabic neural voice (edge-tts).
Zero GPU required — low latency, realistic Egyptian voice.
"""

import asyncio
import io
import subprocess
from app.providers.tts.base import BaseTTSProvider
from app.core.logger import get_logger
from app.core.threading import run_in_io_thread

logger = get_logger(__name__)

DEFAULT_VOICE = "ar-EG-SalmaNeural"  # Egyptian Arabic Neural Voice (Alternative: ar-EG-ShakirNeural)


class ArEgFreeProvider(BaseTTSProvider):
    """Free Egyptian Arabic TTS using edge-tts neural voice."""

    def __init__(self, voice: str = DEFAULT_VOICE):
        self.voice = voice

    async def synthesize(self, text: str) -> bytes:
        if not text or not text.strip():
            return b""

        # Try edge-tts (High quality Egyptian Neural voice)
        try:
            import edge_tts
            comm = edge_tts.Communicate(text, self.voice)
            mp3_data = bytearray()
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    mp3_data.extend(chunk["data"])

            if mp3_data:
                return await run_in_io_thread(_to_wav, bytes(mp3_data))
        except Exception as e:
            logger.error(f"edge-tts failed: {e}")

        return b""

    def synthesize_sync(self, text: str) -> bytes:
        """Synchronous synthesis safe to call from background worker threads."""
        if not text or not text.strip():
            return b""
        try:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return b""
                return loop.run_until_complete(self.synthesize(text))
            except RuntimeError:
                return asyncio.run(self.synthesize(text))
        except Exception as e:
            logger.error(f"Edge-TTS sync failed: {e}")
            return b""



def _to_wav(audio_data: bytes, sample_rate: int = 24000) -> bytes:
    """Convert MP3 audio bytes to standard WAV bytes using bundled imageio_ffmpeg."""
    try:
        import struct
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        proc = subprocess.run(
            [ffmpeg_exe, "-y", "-i", "pipe:0", "-f", "wav", "-ar", str(sample_rate), "-ac", "1", "pipe:1"],
            input=audio_data,
            capture_output=True,
            check=True,
        )
        wav = bytearray(proc.stdout)
        # Fix non-seekable pipe header (FFmpeg sets size to 0xFFFFFFFF for pipe:1)
        if len(wav) >= 44 and wav[:4] == b"RIFF":
            wav[4:8] = struct.pack("<I", len(wav) - 8)
            pos = wav.find(b"data")
            if pos != -1:
                wav[pos + 4 : pos + 8] = struct.pack("<I", len(wav) - (pos + 8))
        return bytes(wav)
    except Exception as e:
        logger.warning(f"WAV conversion failed: {e}, returning raw audio")
        return audio_data

ArEgFreeTTSProvider = ArEgFreeProvider
