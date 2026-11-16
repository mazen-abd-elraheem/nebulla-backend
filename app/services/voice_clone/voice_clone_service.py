"""
Voice Clone Service
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

High-level service that manages:
  • Voice sample upload + validation
  • Personality ↔ reference-WAV binding
  • XTTS / VoiceTut synthesis with the cloned voice
  • Streaming chunks back to the phone app
  • QwenCleo Egyptian Arabic STT auto-transcription (multithreaded chunks)
  • Automatic VAD silence trimming to remove leading empty pause ("الريك الفاضي")

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
from app.utils.masri_normalizer import clean_llm_output_for_speech

logger = get_logger(__name__)

_SAMPLES_DIR = Path("data/voice_samples")
_SAMPLES_DIR.mkdir(parents=True, exist_ok=True)

_MIN_DURATION_S = 1.5    # minimum acceptable sample length (supports quick voice notes)
_MAX_DURATION_S = 120.0  # cap to avoid huge uploads


class VoiceCloneService:
    """
    Manages voice samples and drives VoiceTut/XTTS synthesis.
    Swaps reference audio per personality and applies Egyptian dialect normalizer.
    """

    def __init__(self):
        from app.providers.tts.xtts.provider import XTTSProvider
        self._xtts = XTTSProvider()
        self._voicetut = self._xtts
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
        trim leading/trailing dead silence, validate duration, save it,
        auto-transcribe using QwenCleo STT (multithreaded chunks), and bind it to a personality.

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

        # Convert and automatically trim leading and trailing dead silence ("الريك الفاضي")
        duration = _save_and_convert_to_wav(raw, ext, dest)

        if duration < _MIN_DURATION_S:
            if dest.exists():
                dest.unlink()
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"مدة الصوت الفعلي قصيرة جداً ({duration:.1f} ثانية). الحد الأدنى هو {_MIN_DURATION_S} ثانية من الكلام البشري.",
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
        else:
            # Auto-transcribe using QwenCleo Egyptian Arabic STT (multithreaded chunks processing)
            try:
                from app.providers.stt.factory import get_stt_provider
                stt = get_stt_provider("qwencleo")
                auto_txt = await stt.transcribe(dest.read_bytes())
                if auto_txt and auto_txt.strip():
                    txt_dest.write_text(auto_txt.strip(), encoding="utf-8")
                    logger.info(f"Auto-transcribed reference audio with QwenCleo: {auto_txt.strip()[:60]}...")
            except Exception as stt_err:
                logger.warning(f"Could not auto-transcribe reference audio with QwenCleo: {stt_err}")

        self._personality_voice_map[personality_id] = str(dest)
        logger.info(f"Voice sample saved for personality {personality_id}: {dest} ({duration:.1f}s)")
        await self._sync_db_voice_sample(personality_id, str(dest))
        # Trigger background pre-caching of greeting with the new cloned voice
        import asyncio
        asyncio.create_task(self.generate_and_cache_greeting(personality_id))
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
        """
        Return the stored WAV path strictly for a specific personality.
        Does NOT fall back to other personalities' voices to prevent voice mixing.
        """
        if personality_id is not None:
            # Check in-memory map first
            if personality_id in self._personality_voice_map:
                p = Path(self._personality_voice_map[personality_id])
                if p.exists() and p.stat().st_size > 1000:
                    return str(p)
            # Fall back to disk strictly for this personality
            p = _SAMPLES_DIR / f"personality_{personality_id}.wav"
            if p.exists() and p.stat().st_size > 1000:
                self._personality_voice_map[personality_id] = str(p)
                return str(p)
            # Personality has no dedicated voice sample
            return None

        # Only if personality_id is None (general system call), use the latest available sample
        return self.get_latest_sample_path()
        return self.get_latest_sample_path()

    def has_voice_sample(self, personality_id: int | None = None) -> bool:
        """Check whether a specific personality has an existing voice sample."""
        if personality_id is None:
            return False
        if personality_id in self._personality_voice_map:
            p = Path(self._personality_voice_map[personality_id])
            if p.exists() and p.stat().st_size > 1000:
                return True
        p = _SAMPLES_DIR / f"personality_{personality_id}.wav"
        if p.exists() and p.stat().st_size > 1000:
            self._personality_voice_map[personality_id] = str(p)
            return True
        return False

    async def get_user_voice_sample(self, user_id: int) -> tuple[int | None, str | None]:
        """
        Lookup the user's active personality and its voice sample path.
        Returns (personality_id, voice_sample_path) or (None, None).
        """
        try:
            from app.db.session import AsyncSessionLocal
            from sqlalchemy import select
            from app.models.personality import Personality
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(Personality)
                    .where(Personality.user_id == user_id, Personality.is_active == True)
                    .limit(1)
                )
                p = res.scalar_one_or_none()
                if not p:
                    res = await session.execute(
                        select(Personality)
                        .where(Personality.user_id == user_id)
                        .order_by(Personality.id.asc())
                        .limit(1)
                    )
                    p = res.scalar_one_or_none()

                if p:
                    disk_sample = self.get_sample_path(p.id)
                    if disk_sample:
                        return p.id, disk_sample
                    if p.voice_sample_path and os.path.exists(p.voice_sample_path):
                        return p.id, p.voice_sample_path
                    return p.id, None
        except Exception as err:
            logger.warning(f"Error fetching voice sample for user {user_id}: {err}")
        return None, None

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

    def list_speakers(self) -> list[dict]:
        """List available speaker voices via the VoiceTut / XTTS engine."""
        return self._xtts.list_speakers()

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
            greet_p = self._xtts.get_greeting_cache_path(personality_id)
            if greet_p.exists():
                try:
                    greet_p.unlink()
                except Exception:
                    pass
            await self._sync_db_voice_sample(personality_id, None)
            return True
        return False

    # ── Cloned Greeting Caching ───────────────────────────────────────────────

    def get_cached_greeting(self, personality_id: int | None = None) -> bytes | None:
        """Fetch pre-cached greeting audio if available on disk (0ms instant playback)."""
        pid = personality_id if personality_id is not None else 1
        return self._xtts.get_cached_greeting(pid)

    async def generate_and_cache_greeting(
        self,
        personality_id: int | None = None,
        text: str | None = None,
    ) -> str | None:
        """Pre-synthesize greeting with the cloned voice and persist to cache."""
        pid = personality_id if personality_id is not None else 1
        greeting_text = text
        if not greeting_text:
            try:
                from app.db.session import AsyncSessionLocal
                from sqlalchemy import select
                from app.models.personality import Personality
                async with AsyncSessionLocal() as session:
                    res = await session.execute(
                        select(Personality).where(Personality.id == pid)
                    )
                    p = res.scalar_one_or_none()
                    if p and getattr(p, "greeting", None) and p.greeting.strip():
                        greeting_text = p.greeting.strip()
            except Exception as e:
                logger.debug(f"Could not load personality greeting: {e}")

        if not greeting_text:
            greeting_text = "أهلاً بيك، أنا نيبولا توأمك الرقمي، جاهز أساعدك في أي وقت"

        sample_path = self.get_sample_path(pid)
        if not sample_path or not os.path.exists(sample_path):
            sample_path = str(Path("data/voice_samples/personality_1.wav").resolve())
            if not os.path.exists(sample_path):
                return None

        try:
            await self._xtts.precache_greeting(
                personality_id=pid,
                text=greeting_text,
                sample_path=sample_path,
            )
            cache_path = self._xtts.get_greeting_cache_path(pid)
            return str(cache_path)
        except Exception as e:
            logger.warning(f"Failed to pre-cache greeting for personality {pid}: {e}")
            return None

    # ── Synthesis ─────────────────────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        personality_id: int | None = None,
        reference_wav: str | None = None,
        language: str = "arz",
        ref_text: str | None = None,
        num_step: int | None = None,
        guidance_scale: float | None = None,
        speed: float | None = None,
    ) -> bytes:
        """
        Synthesise *text* in the cloned voice after applying Masri dialect normalization.

        Priority of voice reference:
          1. Explicit reference_wav path (override)
          2. Personality-bound sample (personality_id lookup)
          3. Default provider synthesis
        """
        clean_text = clean_llm_output_for_speech(text)
        if not clean_text or not clean_text.strip():
            logger.debug("clean_llm_output_for_speech resulted in empty text, returning empty audio bytes.")
            return b""

        wav_path = reference_wav
        if not wav_path and personality_id is not None:
            wav_path = self.get_sample_path(personality_id)
            if not wav_path or not os.path.exists(wav_path):
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"الشخصية رقم {personality_id} ملهاش بصمة صوت مسجلة حتى الآن. يرجى رفع أو تسجيل عينة صوت للشخصية أولاً لتفعيل الرد الصوتي الخاص بيها.",
                )
        elif not wav_path:
            wav_path = self.get_latest_sample_path()

        # Validate that the file is a readable WAV format
        import soundfile as sf
        is_valid_wav = False
        if wav_path and os.path.exists(wav_path):
            try:
                with sf.SoundFile(wav_path) as sf_chk:
                    if sf_chk.frames > 0:
                        is_valid_wav = True
            except Exception:
                is_valid_wav = False

        if not is_valid_wav:
            default_built_in = Path("models/voicetut-tts/reference_speakers/ahmed.wav")
            if default_built_in.exists():
                wav_path = str(default_built_in.resolve())
                if not ref_text:
                    ref_text = "يعني كل ما تيجي تفكر ان الدنيا بايظة و ان الحياة مش قد كدة، اِفتكر ان ربنا موجود و انه قادر على كل شئ."
            else:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="يرجى تسجيل عينة صوتك لتفعيل الرد الصوتي المستنسخ.",
                )

        if not ref_text and wav_path:
            txt_path = Path(wav_path).with_suffix(".txt")
            if txt_path.exists():
                try:
                    ref_text = txt_path.read_text(encoding="utf-8").strip()
                except Exception:
                    pass

        steps = num_step or getattr(settings, "VOICETUT_NUM_STEPS", 48)
        cfg = guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.2)
        spd = speed or getattr(settings, "VOICETUT_SPEED", 1.0)

        # Primary VoiceTut-powered XTTS synthesis
        try:
            return await self._xtts.synthesize(
                clean_text,
                ref_audio=wav_path,
                ref_text=ref_text,
                num_step=steps,
                guidance_scale=cfg,
                speed=spd,
                language=language,
            )
        except Exception as exc:
            logger.error(f"XTTS synthesis error: {exc}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Voice synthesis failed: {exc}",
            ) from exc

    async def synthesize_stream(
        self,
        text: str,
        personality_id: int | None = None,
        reference_wav: str | None = None,
        language: str = "arz",
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

def trim_audio_silence(
    raw_wav_bytes: bytes,
    threshold_ratio: float = 0.025,
    pad_ms: int = 80,
) -> tuple[bytes, float, bool]:
    """
    Trim leading and trailing silence from WAV audio.
    Eliminates the empty waiting delay ('الريك فاضي') at the start/end of recordings,
    while retaining a natural 80ms cushion for smooth voice onset.
    Returns (trimmed_bytes, duration_seconds, is_completely_silent).
    """
    import io
    import numpy as np
    import soundfile as sf

    try:
        audio, sr = sf.read(io.BytesIO(raw_wav_bytes))
        if len(audio) == 0:
            return raw_wav_bytes, 0.0, True

        mono = audio.mean(axis=1) if audio.ndim > 1 else audio
        frame_size = max(1, int(sr * 0.02))  # 20ms frames
        num_frames = len(mono) // frame_size
        if num_frames == 0:
            dur = len(audio) / sr
            return raw_wav_bytes, dur, False

        frames = mono[: num_frames * frame_size].reshape(num_frames, frame_size)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))
        peak_rms = float(np.max(rms))

        # Peak RMS check for empty/silent recording
        if peak_rms < 1e-4:
            return raw_wav_bytes, len(audio) / sr, True

        threshold = max(0.002, peak_rms * threshold_ratio)
        active = np.where(rms > threshold)[0]
        if len(active) == 0:
            return raw_wav_bytes, len(audio) / sr, True

        pad_samples = int(sr * (pad_ms / 1000.0))
        start_idx = max(0, active[0] * frame_size - pad_samples)
        end_idx = min(len(audio), (active[-1] + 1) * frame_size + pad_samples)

        trimmed_audio = audio[start_idx:end_idx]
        out_buf = io.BytesIO()
        sf.write(out_buf, trimmed_audio, sr, format="WAV", subtype="PCM_16")
        dur = len(trimmed_audio) / sr
        return out_buf.getvalue(), dur, False
    except Exception as exc:
        logger.warning(f"Silence trimming notice (retaining original): {exc}")
        return raw_wav_bytes, _wav_duration(raw_wav_bytes), False


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
    Supports WAV, MP3, OGG, FLAC via Python-native SoundFile & Scipy (zero FFmpeg dependency).
    Falls back to Torchaudio and FFmpeg if available.
    Trims leading and trailing silence ("الريك الفاضي") so voice starts instantly.
    Returns trimmed audio duration in seconds.
    """
    converted = False

    # 1. Primary: Python-native SoundFile + Scipy (supports WAV, MP3, OGG, FLAC)
    try:
        import soundfile as sf
        import numpy as np
        from scipy import signal

        data, sr = sf.read(io.BytesIO(raw))
        if data.size > 0:
            if data.ndim > 1:
                data = data.mean(axis=1)
            if sr != 24000:
                num_samples = int(len(data) * 24000 / sr)
                data = signal.resample(data, num_samples)
            buf = io.BytesIO()
            sf.write(buf, data, 24000, subtype="PCM_16", format="WAV")
            dest.write_bytes(buf.getvalue())
            converted = True
    except Exception as sfe:
        logger.debug(f"SoundFile audio conversion notice: {sfe}")

    # 2. Secondary: Torchaudio converter
    if not converted:
        try:
            import torchaudio
            waveform, sr = torchaudio.load(io.BytesIO(raw))
            if waveform.numel() > 0:
                if waveform.shape[0] > 1:
                    waveform = waveform.mean(dim=0, keepdim=True)
                if sr != 24000:
                    resampler = torchaudio.transforms.Resample(orig_freq=sr, new_freq=24000)
                    waveform = resampler(waveform)
                buf = io.BytesIO()
                torchaudio.save(buf, waveform, 24000, format="wav", encoding="PCM_S", bits_per_sample=16)
                dest.write_bytes(buf.getvalue())
                converted = True
        except Exception as tae:
            logger.debug(f"Torchaudio audio conversion notice: {tae}")

    # 3. Tertiary: FFmpeg if installed
    if not converted:
        import shutil
        ffmpeg_exe = shutil.which("ffmpeg")
        if not ffmpeg_exe:
            try:
                import imageio_ffmpeg
                ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
            except Exception:
                ffmpeg_exe = None

        if ffmpeg_exe:
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                tmp_name = tmp.name
                tmp.write(raw)

            try:
                cmd = [
                    ffmpeg_exe,
                    "-y",
                    "-i", tmp_name,
                    "-vn",
                    "-acodec", "pcm_s16le",
                    "-ar", "24000",
                    "-ac", "1",
                    str(dest),
                ]
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if res.returncode == 0 and dest.exists():
                    converted = True
            finally:
                if os.path.exists(tmp_name):
                    try:
                        os.unlink(tmp_name)
                    except OSError:
                        pass

    if not converted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="صيغة الملف الصوتي غير مدعومة أو تالفة. يرجى رفع ملف صوتي بصيغة WAV أو MP3 أو OGG.",
        )

    # Trim leading and trailing silence so recordings never start with long empty delays
    raw_out = dest.read_bytes()
    trimmed_bytes, duration, is_silent = trim_audio_silence(raw_out)
    if is_silent:
        if dest.exists():
            dest.unlink()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="التسجيل الصوتي فارغ أو صامت تماماً. يرجى التحدث بوضوح في الميكروفون ثم إعادة المحاولة.",
        )
    dest.write_bytes(trimmed_bytes)
    return duration
