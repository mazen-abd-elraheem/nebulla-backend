"""
Voice Clone Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

High-level service that manages:
  • Voice sample upload + validation
  • Personality ↔ reference-WAV binding
  • XTTS synthesis with the cloned voice
  • Streaming chunks back to the phone app

Used by the REST API (/api/v1/voice-clone/*) and by the AI pipeline.
"""

import io
import os
import subprocess
import tempfile
import uuid
import wave
from pathlib import Path
from typing import AsyncIterator

from fastapi import HTTPException, UploadFile, status

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.tts.xtts.provider import XTTSProvider

logger = get_logger(__name__)

_SAMPLES_DIR = Path("data/voice_samples")
_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

_MIN_DURATION_S = 1.5    # minimum acceptable sample length (supports quick voice notes)
_MAX_DURATION_S = 120.0  # cap to avoid huge uploads


class VoiceCloneService:
    """
    Manages voice samples and drives XTTS synthesis.
    One XTTSProvider is shared and the reference wav is swapped per request.
    """

    def __init__(self):
        self._xtts = XTTSProvider()
        from app.providers.tts.voicetut import VoiceTutProvider
        self._voicetut = VoiceTutProvider()
        self._personality_voice_map: dict[int, str] = {}  # personality_id → wav path

    # ── Sample management ─────────────────────────────────────────────────────

    async def upload_sample(
        self,
        personality_id: int,
        file: UploadFile,
        transcript: str | None = None,
    ) -> str:
        """
        Receive an audio or video upload (WAV or MP4), convert to standard WAV,
        validate duration, save it, and bind it to a personality.

        Returns the saved file path.
        Accepted formats: .wav, .mp4, .m4a, .mp3, .webm, .ogg, .aac, .opus, .flac, .3gp, .amr, .wma
        """
        if not file.filename:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Filename is missing.",
            )

        ext = Path(file.filename).suffix.lower()
        allowed_exts = {
            ".wav", ".mp4", ".m4a", ".mp3", ".webm", ".ogg",
            ".aac", ".opus", ".flac", ".3gp", ".wma", ".amr"
        }
        if ext not in allowed_exts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported format '{ext}'. Accepted formats: {', '.join(sorted(allowed_exts))}",
            )

        raw = await file.read()
        dest = _SAMPLES_DIR / f"personality_{personality_id}.wav"

        duration = _save_and_convert_to_wav(raw, ext, dest)

        if duration < _MIN_DURATION_S:
            if dest.exists():
                dest.unlink()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Sample too short ({duration:.1f}s). Minimum is {_MIN_DURATION_S}s.",
            )
        if duration > _MAX_DURATION_S:
            if dest.exists():
                dest.unlink()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Sample too long ({duration:.1f}s). Maximum is {_MAX_DURATION_S}s.",
            )

        txt_dest = dest.with_suffix(".txt")
        if transcript and transcript.strip():
            txt_dest.write_text(transcript.strip(), encoding="utf-8")
            logger.info(f"Saved transcript for personality {personality_id}")
        elif txt_dest.exists():
            txt_dest.unlink()

        self._personality_voice_map[personality_id] = str(dest)
        logger.info(f"Voice sample saved for personality {personality_id}: {dest} ({duration:.1f}s)")
        await self._sync_db_voice_sample(personality_id, str(dest))
        return str(dest)

    async def _sync_db_voice_sample(self, personality_id: int, path: str | None) -> None:
        """Synchronize voice sample path with database personality record."""
        try:
            from app.db.session import AsyncSessionLocal
            from app.models.personality import Personality
            async with AsyncSessionLocal() as session:
                p = await session.get(Personality, personality_id)
                if p:
                    p.voice_sample_path = path
                    await session.commit()
                    logger.info(f"Updated DB personality {personality_id} voice_sample_path -> {path}")
        except Exception as exc:
            logger.warning(f"Could not sync voice_sample_path with DB: {exc}")

    def get_latest_sample_path(self) -> str | None:
        """Return the most recently saved or modified voice sample path."""
        samples = list(_SAMPLES_DIR.glob("personality_*.wav"))
        if samples:
            samples.sort(key=lambda s: s.stat().st_mtime, reverse=True)
            return str(samples[0])
        any_wavs = list(_SAMPLES_DIR.glob("*.wav"))
        if any_wavs:
            any_wavs.sort(key=lambda s: s.stat().st_mtime, reverse=True)
            return str(any_wavs[0])
        return None

    def get_sample_path(self, personality_id: int | None = None) -> str | None:
        """Return the stored WAV path for a personality, or latest available sample if None."""
        if personality_id is not None:
            # Check in-memory map first
            if personality_id in self._personality_voice_map:
                p = Path(self._personality_voice_map[personality_id])
                if p.exists():
                    return str(p)
            # Fall back to disk
            p = _SAMPLES_DIR / f"personality_{personality_id}.wav"
            if p.exists():
                self._personality_voice_map[personality_id] = str(p)
                return str(p)
            return None
        # If personality_id is None, fallback to the latest uploaded sample
        return self.get_latest_sample_path()

    def list_samples(self) -> list[dict]:
        """List all stored voice samples."""
        results = []
        for wav in sorted(_SAMPLES_DIR.glob("personality_*.wav")):
            pid_str = wav.stem.replace("personality_", "")
            try:
                pid = int(pid_str)
                duration = _wav_duration(wav.read_bytes())
                results.append({
                    "personality_id": pid,
                    "filename": wav.name,
                    "duration_s": round(duration, 2),
                    "size_bytes": wav.stat().st_size,
                })
            except Exception:
                pass
        return results

    async def delete_sample(self, personality_id: int) -> bool:
        """Delete a stored voice sample."""
        p = _SAMPLES_DIR / f"personality_{personality_id}.wav"
        txt_p = p.with_suffix(".txt")
        deleted = False
        if p.exists():
            p.unlink()
            deleted = True
        if txt_p.exists():
            txt_p.unlink()
            deleted = True
        if deleted:
            self._personality_voice_map.pop(personality_id, None)
            logger.info(f"Deleted voice sample for personality {personality_id}")
            await self._sync_db_voice_sample(personality_id, None)
            return True
        return False

    # ── Synthesis ─────────────────────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        personality_id: int | None = None,
        reference_wav: str | None = None,
        language: str = "ar",
        ref_text: str | None = None,
        num_step: int | None = None,
    ) -> bytes:
        """
        Synthesise *text* strictly in the cloned voice using VoiceTut zero-shot cloning.
        Retrieves the voice sample from the specified personality, DB active personality,
        or latest uploaded recording.
        No generic speakers or fallback models allowed.

        Returns WAV bytes.
        """
        wav_path = reference_wav or self.get_sample_path(personality_id)

        # If not found yet, check active personality in DB
        if not wav_path or not os.path.exists(wav_path):
            try:
                from app.db.session import AsyncSessionLocal
                from app.models.personality import Personality
                from sqlalchemy import select
                async with AsyncSessionLocal() as session:
                    res = await session.execute(
                        select(Personality).where(Personality.is_active == True).limit(1)  # noqa: E712
                    )
                    active_p = res.scalar_one_or_none()
                    if active_p and active_p.voice_sample_path and os.path.exists(active_p.voice_sample_path):
                        wav_path = active_p.voice_sample_path
            except Exception as db_err:
                logger.debug(f"DB active personality check: {db_err}")

        # Fallback to latest uploaded sample
        if not wav_path or not os.path.exists(wav_path):
            wav_path = self.get_latest_sample_path()

        if not wav_path or not os.path.exists(wav_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="لا توجد عينة صوتية مستنسخة محفوظة للنظام أو للشخصية المطلوبة. يرجى رفع ملف الصوت أولاً عبر POST /api/v1/voice-clone/upload.",
            )

        logger.info(f"Synthesizing text strictly using cloned voice sample: {wav_path}")
        res = await self._voicetut.synthesize(
            text=text,
            ref_audio=wav_path,
            ref_text=ref_text,
            num_step=num_step,
        )
        if not res or len(res) <= 1000:
            raise RuntimeError("فشل توليد الصوت المستنسخ بواسطة VoiceTut ولم يتم إنتاج إشارة صوتية كافية.")

        return res

    async def synthesize_stream(
        self,
        text: str,
        personality_id: int | None = None,
        reference_wav: str | None = None,
        language: str = "ar",
    ) -> AsyncIterator[bytes]:
        """Streaming variant — yields WAV chunks for low-latency playback."""
        wav_bytes = await self.synthesize(text, personality_id, reference_wav, language)
        chunk_size = 4096
        for i in range(0, len(wav_bytes), chunk_size):
            yield wav_bytes[i : i + chunk_size]

    # ── Singleton ─────────────────────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "VoiceCloneService":
        """Return the process-level singleton."""
        if not hasattr(cls, "_instance"):
            cls._instance = cls()
        return cls._instance


# ── Internal helpers ──────────────────────────────────────────────────────────

def _wav_duration(raw: bytes) -> float:
    """Return the duration of a WAV file in seconds."""
    try:
        with wave.open(io.BytesIO(raw)) as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


def _save_and_convert_to_wav(raw: bytes, ext: str, dest: Path) -> float:
    """
    Save incoming audio/video bytes to standard WAV (16-bit PCM, 24kHz, mono).
    If it's already a clean WAV, save directly.
    If it's MP4, M4A, or non-standard WAV, convert using ffmpeg.
    Returns audio duration in seconds.
    """
    if ext == ".wav":
        try:
            with wave.open(io.BytesIO(raw), "rb") as wf:
                dur = wf.getnframes() / wf.getframerate()
                # Only use directly if it is strictly 24kHz mono 16-bit PCM (otherwise resample with ffmpeg)
                if dur > 0 and wf.getnchannels() == 1 and wf.getframerate() == 24000 and wf.getsampwidth() == 2:
                    dest.write_bytes(raw)
                    return dur
        except Exception:
            pass  # Fallback to ffmpeg conversion if WAV format is compressed or corrupt

    # Convert via FFmpeg (handles MP4, M4A, AAC, and any WAV variants)
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        logger.error(f"Cannot get ffmpeg executable: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server audio conversion component is not available.",
        )

    # Write temporary file to pass to ffmpeg
    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
        tmp_name = tmp.name
        tmp.write(raw)

    try:
        cmd = [
            ffmpeg_exe,
            "-y",
            "-i", tmp_name,
            "-vn",                   # Strip video track (in case of MP4 video)
            "-acodec", "pcm_s16le",  # Standard 16-bit PCM
            "-ar", "24000",          # 24kHz sample rate (XTTS native)
            "-ac", "1",              # Mono audio
            str(dest),
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", errors="ignore")
            logger.error(f"FFmpeg conversion failed: {err}")
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Could not extract audio track from file. Please ensure it has a valid audio stream.",
            )

        duration = _wav_duration(dest.read_bytes())
        return duration
    finally:
        if os.path.exists(tmp_name):
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
