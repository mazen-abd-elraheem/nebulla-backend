"""
SpeakerVerificationService — voiceprint enrolment & matching
(benefits_section.docx §14.3, "التحقق بالصوت").

Design (agreed in /grill-me):
  * A dedicated speaker-embedding model (SpeechBrain ECAPA-TDNN) runs in a
    worker thread IN PARALLEL with STT, so it adds no latency to the turn.
  * Only the mean L2-normalised embedding is stored — never the recordings.
  * FAILS CLOSED: if the model can't load, verification is disabled, or nobody is
    enrolled, no speaker is ever reported as verified → only Level-0 actions run.

Audio contract: raw PCM16 mono @ SPEAKER_SAMPLE_RATE (as sent by the phone), or a
PCM16 WAV file (enrolment uploads).
"""

import asyncio
import io
import threading
import wave
from dataclasses import dataclass
from typing import Dict, List, Optional, Protocol

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.voiceprint import Voiceprint

logger = get_logger(__name__)


# ── audio decoding ───────────────────────────────────────────────────────────

class AudioDecodeError(ValueError):
    pass


def decode_audio(data: bytes, target_sr: Optional[int] = None) -> np.ndarray:
    """PCM16 WAV or raw PCM16 mono → float32 [-1, 1] at `target_sr`."""
    sr_target = target_sr or settings.SPEAKER_SAMPLE_RATE
    src_sr = sr_target
    if data[:4] == b"RIFF":
        try:
            with wave.open(io.BytesIO(data)) as w:
                if w.getsampwidth() != 2:
                    raise AudioDecodeError("Only 16-bit PCM WAV is supported")
                src_sr = w.getframerate()
                channels = w.getnchannels()
                frames = w.readframes(w.getnframes())
        except wave.Error as e:
            raise AudioDecodeError(f"Invalid WAV: {e}") from e
        pcm = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
        if channels > 1:
            pcm = pcm[: len(pcm) - (len(pcm) % channels)].reshape(-1, channels).mean(axis=1)
    else:
        usable = len(data) - (len(data) % 2)
        pcm = np.frombuffer(data[:usable], dtype="<i2").astype(np.float32) / 32768.0
    if src_sr != sr_target and len(pcm) > 1:
        n_out = int(round(len(pcm) * sr_target / src_sr))
        pcm = np.interp(
            np.linspace(0, len(pcm) - 1, n_out), np.arange(len(pcm)), pcm
        ).astype(np.float32)
    return pcm


def _unit(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype=np.float32).reshape(-1)
    n = float(np.linalg.norm(v))
    if n == 0.0 or not np.isfinite(n):
        raise ValueError("degenerate embedding")
    return v / n


# ── embedding backend ────────────────────────────────────────────────────────

class EmbeddingBackend(Protocol):
    model_id: str

    def available(self) -> bool: ...
    def embed(self, samples: np.ndarray) -> np.ndarray: ...


class SpeechBrainBackend:
    """ECAPA-TDNN speaker encoder, loaded lazily and only once."""

    def __init__(self) -> None:
        self.model_id = settings.SPEAKER_MODEL_SOURCE
        self._model = None
        self._failed = False
        self._lock = threading.Lock()

    def _load(self) -> None:
        with self._lock:
            if self._model is not None or self._failed:
                return
            try:
                try:
                    from speechbrain.inference.speaker import EncoderClassifier
                except ImportError:  # speechbrain < 1.0
                    from speechbrain.pretrained import EncoderClassifier  # type: ignore
                self._model = EncoderClassifier.from_hparams(
                    source=settings.SPEAKER_MODEL_SOURCE,
                    savedir=settings.SPEAKER_MODEL_DIR,
                    run_opts={"device": settings.SPEAKER_DEVICE},
                )
                logger.info("Speaker encoder loaded (%s)", settings.SPEAKER_MODEL_SOURCE)
            except Exception as e:  # noqa: BLE001 — any failure ⇒ fail closed
                self._failed = True
                logger.error("Speaker encoder unavailable — voice verification fails closed: %s", e)

    def available(self) -> bool:
        if self._model is None and not self._failed:
            self._load()
        return self._model is not None

    def embed(self, samples: np.ndarray) -> np.ndarray:
        if not self.available():
            raise RuntimeError("speaker encoder unavailable")
        import torch

        wav = torch.from_numpy(samples.astype(np.float32)).unsqueeze(0)
        with torch.no_grad():
            emb = self._model.encode_batch(wav)  # type: ignore[union-attr]
        return emb.squeeze().detach().cpu().numpy()


# ── results ──────────────────────────────────────────────────────────────────

@dataclass
class VerificationResult:
    """What the Guard needs to know about *who* just spoke."""
    available: bool = False          # encoder usable
    enrolled: bool = False           # at least one voiceprint exists
    score: Optional[float] = None    # best cosine similarity (None = not scored)
    user_id: Optional[int] = None
    speaker_name: Optional[str] = None
    max_level: int = 0
    audio_seconds: float = 0.0
    passed_l1: bool = False
    passed_l2: bool = False


@dataclass
class _Entry:
    vector: np.ndarray
    speaker_name: str
    max_level: int


class VoiceprintError(ValueError):
    pass


class SpeakerVerificationService:
    def __init__(self, backend: Optional[EmbeddingBackend] = None) -> None:
        self._backend: EmbeddingBackend = backend or SpeechBrainBackend()
        self._cache: Optional[Dict[int, _Entry]] = None
        self._cache_lock = asyncio.Lock()

    # ── cache ────────────────────────────────────────────────────────────

    def invalidate(self) -> None:
        self._cache = None

    async def _entries(self, session_factory=None) -> Dict[int, _Entry]:
        if self._cache is not None:
            return self._cache
        async with self._cache_lock:
            if self._cache is None:
                if session_factory is None:
                    from app.db.session import AsyncSessionLocal as session_factory  # noqa: N813
                entries: Dict[int, _Entry] = {}
                async with session_factory() as db:
                    rows = (await db.execute(select(Voiceprint))).scalars().all()
                for r in rows:
                    try:
                        vec = _unit(np.frombuffer(r.embedding, dtype=np.float32))
                    except ValueError:
                        logger.warning("Skipping corrupt voiceprint for user %s", r.user_id)
                        continue
                    entries[r.user_id] = _Entry(vec, r.speaker_name, int(r.max_level))
                self._cache = entries
        return self._cache

    # ── verification ─────────────────────────────────────────────────────

    async def verify(self, audio: bytes, *, session_factory=None) -> VerificationResult:
        """Score `audio` against every enrolled voiceprint. Never raises."""
        if not settings.SPEAKER_VERIFICATION_ENABLED:
            return VerificationResult()
        try:
            entries = await self._entries(session_factory)
            if not entries:
                return VerificationResult(available=True, enrolled=False)
            if not await asyncio.to_thread(self._backend.available):
                return VerificationResult(available=False, enrolled=True)

            samples = decode_audio(audio)
            seconds = len(samples) / float(settings.SPEAKER_SAMPLE_RATE)
            res = VerificationResult(available=True, enrolled=True, audio_seconds=seconds)
            if seconds < settings.SPEAKER_MIN_AUDIO_SECONDS:
                return res  # too short to score reliably → not verified (fail closed)

            emb = _unit(await asyncio.to_thread(self._backend.embed, samples))
            best_uid, best = None, -1.0
            for uid, entry in entries.items():
                s = float(np.dot(emb, entry.vector))
                if s > best:
                    best_uid, best = uid, s
            entry = entries[best_uid]  # type: ignore[index]
            res.score = best
            res.user_id = best_uid
            res.speaker_name = entry.speaker_name
            res.max_level = entry.max_level
            res.passed_l1 = best >= settings.SPEAKER_THRESHOLD_L1
            res.passed_l2 = best >= settings.SPEAKER_THRESHOLD_L2
            return res
        except Exception as e:  # noqa: BLE001
            logger.warning("Speaker verification failed (treated as unverified): %s", e)
            return VerificationResult(available=False, enrolled=True)

    async def score_for_user(self, audio: bytes, user_id: int, *, session_factory=None) -> Optional[float]:
        """Cosine similarity to one user's voiceprint (calibration tool)."""
        entries = await self._entries(session_factory)
        entry = entries.get(user_id)
        if entry is None or not await asyncio.to_thread(self._backend.available):
            return None
        samples = decode_audio(audio)
        if len(samples) / float(settings.SPEAKER_SAMPLE_RATE) < 0.5:
            return None
        emb = _unit(await asyncio.to_thread(self._backend.embed, samples))
        return float(np.dot(emb, entry.vector))

    # ── enrolment ────────────────────────────────────────────────────────

    async def enroll(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        speaker_name: str,
        samples: List[bytes],
        max_level: int = 2,
    ) -> Voiceprint:
        """
        Build and store a voiceprint from consented enrolment samples.
        The raw audio is discarded after the embedding is computed.
        """
        if not (0 <= max_level <= 3):
            raise VoiceprintError("max_level must be between 0 and 3")
        if not (settings.SPEAKER_ENROLL_MIN_SAMPLES <= len(samples) <= settings.SPEAKER_ENROLL_MAX_SAMPLES):
            raise VoiceprintError(
                f"Provide {settings.SPEAKER_ENROLL_MIN_SAMPLES}–{settings.SPEAKER_ENROLL_MAX_SAMPLES} samples"
            )
        if not await asyncio.to_thread(self._backend.available):
            raise VoiceprintError("Speaker model is not available on this server")

        vectors: List[np.ndarray] = []
        for i, raw in enumerate(samples):
            try:
                pcm = decode_audio(raw)
            except AudioDecodeError as e:
                raise VoiceprintError(f"Sample {i + 1}: {e}") from e
            secs = len(pcm) / float(settings.SPEAKER_SAMPLE_RATE)
            if not (1.5 <= secs <= 20.0):
                raise VoiceprintError(f"Sample {i + 1}: length must be 1.5–20 s (got {secs:.1f}s)")
            vectors.append(_unit(await asyncio.to_thread(self._backend.embed, pcm)))

        # Quality gate: drop samples that disagree with the rest (noise / other speaker)
        kept = _drop_outliers(vectors)
        if len(kept) < settings.SPEAKER_ENROLL_MIN_SAMPLES:
            raise VoiceprintError(
                "Samples are inconsistent (different speakers or too noisy). "
                "Re-record in a quiet room."
            )
        mean = _unit(np.mean(np.stack(kept), axis=0))

        existing = (
            await db.execute(select(Voiceprint).where(Voiceprint.user_id == user_id))
        ).scalar_one_or_none()
        blob = mean.astype(np.float32).tobytes()
        if existing:
            existing.speaker_name = speaker_name
            existing.embedding = blob
            existing.embedding_dim = int(mean.shape[0])
            existing.samples_count = len(kept)
            existing.model_id = self._backend.model_id
            existing.max_level = max_level
            row = existing
        else:
            row = Voiceprint(
                user_id=user_id,
                speaker_name=speaker_name,
                embedding=blob,
                embedding_dim=int(mean.shape[0]),
                samples_count=len(kept),
                model_id=self._backend.model_id,
                max_level=max_level,
            )
            db.add(row)
        await db.flush()
        self.invalidate()
        return row

    async def delete(self, db: AsyncSession, user_id: int) -> bool:
        row = (
            await db.execute(select(Voiceprint).where(Voiceprint.user_id == user_id))
        ).scalar_one_or_none()
        if not row:
            return False
        await db.delete(row)
        await db.flush()
        self.invalidate()
        return True


def _drop_outliers(vectors: List[np.ndarray], floor: float = 0.45) -> List[np.ndarray]:
    """Keep vectors whose similarity to the leave-one-out centroid is ≥ floor."""
    if len(vectors) < 3:
        return vectors
    stack = np.stack(vectors)
    total = stack.sum(axis=0)
    kept = []
    for v in vectors:
        loo = total - v
        n = np.linalg.norm(loo)
        if n == 0:
            continue
        if float(np.dot(v, loo / n)) >= floor:
            kept.append(v)
    return kept


_service: Optional[SpeakerVerificationService] = None


def get_speaker_service() -> SpeakerVerificationService:
    global _service
    if _service is None:
        _service = SpeakerVerificationService()
    return _service
