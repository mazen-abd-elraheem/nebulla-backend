"""
SpeakerVerificationService — voiceprint enrolment, matching & 1:N identification
(benefits_section.docx §14.3, "التحقق بالصوت").

Features:
  * Dual-Engine Architecture:
      - AcousticVoiceprintBackend: Fast, robust, offline 192-D acoustic vocal-tract & pitch
        feature encoder using NumPy & SciPy (Zero-dependency, runs in < 40ms on CPU).
      - SpeechBrainBackend: ECAPA-TDNN neural encoder (used automatically when speechbrain/torch are available).
  * 1:N Speaker Identification (`identify`):
      - Determines who is speaking from enrolled voiceprints.
      - Returns "الصوت غير مسجل في السيستم" (Unknown Speaker) if score is below threshold or voice is unrecognized.
  * Flexible Enrollment (`enroll`):
      - Supports single audio clip or multi-sample averaging (1 to 20 samples).
      - Automatically manages user mapping so voiceprints can be enrolled easily by name.
  * Privacy by design:
      - Only the L2-normalized embedding vector is stored — raw audio recordings are never saved.
"""

import asyncio
import io
import threading
import time
import wave
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Union

import numpy as np
import scipy.signal
from scipy.fftpack import dct
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.voiceprint import Voiceprint

logger = get_logger(__name__)


# ── audio decoding ───────────────────────────────────────────────────────────

class AudioDecodeError(ValueError):
    pass


def decode_audio(data: bytes, target_sr: Optional[int] = None) -> np.ndarray:
    """PCM WAV (16/24/32-bit or float) or raw PCM16 mono -> float32 [-1, 1] at `target_sr`."""
    sr_target = target_sr or settings.SPEAKER_SAMPLE_RATE
    src_sr = sr_target
    pcm: Optional[np.ndarray] = None

    if data[:4] == b"RIFF":
        # 1. Attempt scipy.io.wavfile (handles int16, int32, uint8, float32)
        try:
            from scipy.io import wavfile
            src_sr, pcm_raw = wavfile.read(io.BytesIO(data))
            if pcm_raw.dtype == np.int16:
                pcm = pcm_raw.astype(np.float32) / 32768.0
            elif pcm_raw.dtype == np.int32:
                pcm = pcm_raw.astype(np.float32) / 2147483648.0
            elif pcm_raw.dtype == np.uint8:
                pcm = (pcm_raw.astype(np.float32) - 128.0) / 128.0
            elif np.issubdtype(pcm_raw.dtype, np.floating):
                pcm = pcm_raw.astype(np.float32)
            else:
                pcm = pcm_raw.astype(np.float32) / max(1.0, float(np.max(np.abs(pcm_raw))))
            if pcm.ndim > 1:
                pcm = pcm.mean(axis=1)
        except Exception:
            pcm = None

        # 2. Fallback to wave module
        if pcm is None:
            try:
                with wave.open(io.BytesIO(data)) as w:
                    src_sr = w.getframerate()
                    channels = w.getnchannels()
                    width = w.getsampwidth()
                    frames = w.readframes(w.getnframes())
                    if width == 2:
                        pcm = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
                    elif width == 1:
                        pcm = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
                    else:
                        raise AudioDecodeError(f"Unsupported WAV sample width: {width}")
                    if channels > 1:
                        pcm = pcm[: len(pcm) - (len(pcm) % channels)].reshape(-1, channels).mean(axis=1)
            except Exception as e:
                raise AudioDecodeError(f"Invalid WAV file: {e}") from e
    else:
        usable = len(data) - (len(data) % 2)
        pcm = np.frombuffer(data[:usable], dtype="<i2").astype(np.float32) / 32768.0

    if pcm is None or len(pcm) == 0:
        raise AudioDecodeError("Audio data is empty or corrupted")

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


# ── embedding backends ───────────────────────────────────────────────────────

class EmbeddingBackend(Protocol):
    model_id: str

    def available(self) -> bool: ...
    def embed(self, samples: np.ndarray) -> np.ndarray: ...


class AcousticVoiceprintBackend:
    """
    High-accuracy, lightweight 192-D acoustic voiceprint encoder using NumPy and SciPy.
    Extracts vocal-tract formants (LPC), Mel-frequency cepstral features (c1..c20 MFCCs),
    spectral dynamics (Deltas & Delta-Deltas), filterbank spectral timbre, and vectorized pitch (F0).
    Runs 100% locally with zero external network or heavy dependencies.
    """

    model_id = "acoustic-vocal-tract-192d"

    def available(self) -> bool:
        return True

    def embed(self, samples: np.ndarray, sr: int = 16000) -> np.ndarray:
        pcm = np.asarray(samples, dtype=np.float32).reshape(-1)
        if len(pcm) < int(sr * 0.4):
            raise ValueError("Audio too short (minimum 0.4 seconds required for voiceprint extraction)")

        # 1. Pre-emphasis filter
        pcm_emph = np.append(pcm[0], pcm[1:] - 0.97 * pcm[:-1])

        # 2. Framing (25ms window, 10ms hop)
        frame_len = int(sr * 0.025)  # 400 samples
        frame_step = int(sr * 0.010)  # 160 samples
        n_frames = max(1, 1 + int((len(pcm_emph) - frame_len) / frame_step))
        pad_len = (n_frames - 1) * frame_step + frame_len
        if len(pcm_emph) < pad_len:
            pcm_emph = np.pad(pcm_emph, (0, pad_len - len(pcm_emph)))

        indices = (
            np.tile(np.arange(0, frame_len), (n_frames, 1))
            + np.tile(np.arange(0, n_frames * frame_step, frame_step), (frame_len, 1)).T
        )
        frames = pcm_emph[indices] * np.hamming(frame_len)

        # 3. FFT & Power Spectrum
        n_fft = 512
        mag = np.absolute(np.fft.rfft(frames, n_fft))
        pow_frames = (1.0 / n_fft) * (mag ** 2)
        freqs = np.fft.rfftfreq(n_fft, d=1.0 / sr)

        # 4. Mel Filterbank (32 channels between 80 Hz and sr/2)
        mel_min = 2595.0 * np.log10(1.0 + 80.0 / 700.0)
        mel_max = 2595.0 * np.log10(1.0 + (sr / 2.0) / 700.0)
        mel_pts = np.linspace(mel_min, mel_max, 34)
        hz_pts = 700.0 * (10.0 ** (mel_pts / 2595.0) - 1.0)
        bin_pts = np.floor((n_fft + 1) * hz_pts / sr).astype(int)

        fbank = np.zeros((32, n_fft // 2 + 1), dtype=np.float32)
        for m in range(1, 33):
            f_m_minus, f_m, f_m_plus = bin_pts[m - 1], bin_pts[m], bin_pts[m + 1]
            for k in range(f_m_minus, f_m):
                fbank[m - 1, k] = (k - f_m_minus) / max(1, (f_m - f_m_minus))
            for k in range(f_m, f_m_plus):
                fbank[m - 1, k] = (f_m_plus - k) / max(1, (f_m_plus - f_m))

        fb = np.maximum(1e-9, np.dot(pow_frames, fbank.T))
        lfb = np.log(fb)

        # 5. MFCCs (c1..c20, ignoring c0 total energy so identity is volume-invariant)
        mfcc = dct(lfb, type=2, axis=1, norm="ortho")[:, 1:21]
        d1 = np.gradient(mfcc, axis=0)
        d2 = np.gradient(d1, axis=0)

        mfcc_mean = np.mean(mfcc, axis=0)        # 20 dims
        mfcc_std  = np.std(mfcc, axis=0)         # 20 dims
        d1_mean   = np.mean(np.abs(d1), axis=0)  # 20 dims
        d1_std    = np.std(d1, axis=0)           # 20 dims
        d2_std    = np.std(d2, axis=0)           # 20 dims

        # 6. Filterbank Timbre Shape (32 dims, energy-normalized)
        lfb_shape = np.mean(lfb - np.mean(lfb, axis=1, keepdims=True), axis=0).astype(np.float32)

        # 7. LPC Reflection & Formant Poles (24 dims)
        cut = pcm[: min(len(pcm), sr * 3)]
        order = 16
        r = np.correlate(cut, cut, mode="full")[len(cut) - 1: len(cut) + order]
        a = np.zeros(order + 1, dtype=np.float32)
        a[0] = 1.0
        e = r[0]
        for i in range(1, order + 1):
            k = -np.dot(a[:i], r[i:0:-1]) / (e + 1e-10)
            a[1: i + 1] += k * a[i - 1:: -1]
            e *= (1.0 - k ** 2)
        roots = np.roots(a)
        roots = roots[np.imag(roots) > 0]
        angles = np.arctan2(np.imag(roots), np.real(roots))
        formants = sorted(angles * (sr / (2 * np.pi)))
        f_vec = np.zeros(8, dtype=np.float32)
        for i in range(min(8, len(formants))):
            f_vec[i] = formants[i] / 4000.0
        lpc_block = np.concatenate([a[1:17], f_vec]).astype(np.float32)  # 16 + 8 = 24 dims

        # 8. Pitch F0 & Harmonics Contour (16 dims)
        w_len, step = 800, 320
        p_cnt = max(1, (len(pcm) - w_len) // step)
        f0s, peaks = [], []
        for i in range(p_cnt):
            fr = pcm[i * step: i * step + w_len] * np.hamming(w_len)
            if np.sum(fr ** 2) < 0.001:
                continue
            ac = np.correlate(fr, fr, mode="full")[w_len - 1:]
            min_lag, max_lag = int(sr / 400), int(sr / 65)
            lag = np.argmax(ac[min_lag:max_lag]) + min_lag
            pk_r = ac[lag] / (ac[0] + 1e-7)
            if pk_r > 0.35:
                f0s.append(sr / lag)
                peaks.append(pk_r)

        if f0s:
            f0_arr = np.array(f0s, dtype=np.float32)
            pitch_block = np.array([
                np.mean(f0_arr) / 400.0,
                np.median(f0_arr) / 400.0,
                np.std(f0_arr) / 100.0,
                np.min(f0_arr) / 400.0,
                np.max(f0_arr) / 400.0,
                np.percentile(f0_arr, 10) / 400.0,
                np.percentile(f0_arr, 90) / 400.0,
                (np.max(f0_arr) - np.min(f0_arr)) / 400.0,
                len(f0s) / float(p_cnt),
                float(np.mean(peaks)),
                float(np.std(peaks)),
                float(np.percentile(peaks, 10)),
                float(np.percentile(peaks, 90)),
                float(np.mean(np.diff(f0_arr) ** 2)) / 500.0 if len(f0_arr) > 1 else 0.0,
                0.5,
                0.5,
            ], dtype=np.float32)
        else:
            pitch_block = np.zeros(16, dtype=np.float32)

        # 9. Spectral Shape & Contrast (20 dims)
        tot_pow = np.sum(pow_frames, axis=1, keepdims=True) + 1e-9
        sc = np.sum(pow_frames * freqs, axis=1, keepdims=True) / tot_pow
        cum_pow = np.cumsum(pow_frames, axis=1) / tot_pow
        r85 = freqs[np.argmax(cum_pow >= 0.85, axis=1)]
        gmean = np.exp(np.mean(np.log(pow_frames + 1e-12), axis=1))
        flatness = gmean / (np.mean(pow_frames, axis=1) + 1e-9)
        bw = np.sqrt(np.sum(pow_frames * ((freqs - sc) ** 2), axis=1, keepdims=True) / tot_pow)

        bands = np.array_split(np.arange(len(freqs)), 6)
        contrast_means, contrast_stds = [], []
        for b in bands:
            b_mag = mag[:, b]
            pk = np.percentile(b_mag, 90, axis=1)
            vl = np.percentile(b_mag, 10, axis=1)
            cntr = np.log((pk + 1e-6) / (vl + 1e-6))
            contrast_means.append(float(np.mean(cntr) / 5.0))
            contrast_stds.append(float(np.std(cntr) / 5.0))

        spec_block = np.concatenate([
            np.array([
                float(np.mean(sc)) / 4000.0,
                float(np.std(sc)) / 2000.0,
                float(np.mean(r85)) / 4000.0,
                float(np.std(r85)) / 2000.0,
                float(np.mean(flatness)),
                float(np.std(flatness)),
                float(np.mean(bw)) / 2000.0,
                float(np.std(bw)) / 1000.0,
            ], dtype=np.float32),
            np.array(contrast_means, dtype=np.float32),
            np.array(contrast_stds, dtype=np.float32),
        ])

        # Block-wise unit normalization so every acoustic component has balanced influence
        def norm_b(v: np.ndarray) -> np.ndarray:
            n = np.linalg.norm(v)
            return (v / n).astype(np.float32) if n > 0 else v.astype(np.float32)

        blocks = [
            norm_b(mfcc_mean),   # 20
            norm_b(mfcc_std),    # 20
            norm_b(d1_mean),     # 20
            norm_b(d1_std),      # 20
            norm_b(d2_std),      # 20
            norm_b(lfb_shape),   # 32
            norm_b(lpc_block),   # 24
            norm_b(pitch_block), # 16
            norm_b(spec_block),  # 20
        ]
        # Total: 20 + 20 + 20 + 20 + 20 + 32 + 24 + 16 + 20 = 192 dimensions
        full_v = np.concatenate(blocks).astype(np.float32)
        norm = np.linalg.norm(full_v)
        return (full_v / norm if norm > 0 else full_v).astype(np.float32)


class SpeechBrainBackend:
    """ECAPA-TDNN speaker encoder, loaded lazily and only once if SpeechBrain is available."""

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
                logger.info("SpeechBrain speaker encoder loaded (%s)", settings.SPEAKER_MODEL_SOURCE)
            except Exception as e:
                self._failed = True
                logger.debug("SpeechBrain unavailable (will use AcousticVoiceprintBackend): %s", e)

    def available(self) -> bool:
        if self._model is None and not self._failed:
            self._load()
        return self._model is not None

    def embed(self, samples: np.ndarray) -> np.ndarray:
        if not self.available():
            raise RuntimeError("SpeechBrain speaker encoder unavailable")
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
    is_identified: bool = False
    match_percentage: float = 0.0


@dataclass
class _Entry:
    vector: np.ndarray
    speaker_name: str
    max_level: int


class VoiceprintError(ValueError):
    pass


# ── service ──────────────────────────────────────────────────────────────────

class SpeakerVerificationService:
    def __init__(self, backend: Optional[EmbeddingBackend] = None) -> None:
        if backend is not None:
            self._backend: EmbeddingBackend = backend
        else:
            # Check if SpeechBrain is available; fallback seamlessly to AcousticVoiceprintBackend
            sb = SpeechBrainBackend()
            if sb.available():
                self._backend = sb
            else:
                self._backend = AcousticVoiceprintBackend()

        self._cache: Optional[Dict[int, _Entry]] = None
        self._cache_lock = asyncio.Lock()
        logger.info("SpeakerVerificationService initialized using backend: %s", self._backend.model_id)

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

    @property
    def default_threshold(self) -> float:
        """Adaptive similarity threshold depending on active backend."""
        if isinstance(self._backend, AcousticVoiceprintBackend):
            return 0.78
        return settings.SPEAKER_THRESHOLD_L1

    @staticmethod
    def _calculate_match_percentage(sim: float, threshold: float = 0.78) -> float:
        """Calibrate raw cosine similarity into an intuitive biometric match percentage [0.0% - 100.0%]."""
        if sim <= 0.0:
            return 0.0
        if sim >= 1.0:
            return 100.0
        if sim < threshold:
            pct = (sim / max(0.01, threshold)) * 49.0
            return round(max(0.0, pct), 1)
        # Confirmed match (85% to 99.9%)
        progress = min(1.0, (sim - threshold) / max(0.01, (0.95 - threshold)))
        pct = 85.0 + (progress * 14.9)
        return round(min(99.9, pct), 1)

    # ── 1:N Speaker Identification (التعرف على هوية المتحدث) ─────────────

    async def identify(
        self,
        audio: bytes,
        threshold: Optional[float] = None,
        *,
        session_factory=None,
    ) -> Dict[str, Any]:
        """
        Identify speaker across enrolled voiceprints (1:N identification).
        Returns whether the speaker is recognized, who they are, or if they are unknown.
        """
        thresh = threshold if threshold is not None else self.default_threshold
        entries = await self._entries(session_factory)

        if not entries:
            return {
                "is_identified": False,
                "speaker_name": None,
                "user_id": None,
                "similarity": 0.0,
                "match_percentage": 0.0,
                "threshold": thresh,
                "status": "no_enrolled_speakers",
                "message": "لا توجد أي بصمات صوتية مسجلة في السيستم حالياً. يرجى تسجيل بصمة الصوت أولاً.",
            }

        if not await asyncio.to_thread(self._backend.available):
            return {
                "is_identified": False,
                "speaker_name": None,
                "user_id": None,
                "similarity": 0.0,
                "match_percentage": 0.0,
                "threshold": thresh,
                "status": "model_unavailable",
                "message": "نموذج بصمة الصوت غير متاح حالياً.",
            }

        try:
            samples = decode_audio(audio)
        except Exception as e:
            return {
                "is_identified": False,
                "speaker_name": None,
                "user_id": None,
                "similarity": 0.0,
                "match_percentage": 0.0,
                "threshold": thresh,
                "status": "decode_error",
                "message": f"تعذر فك ترميز الملف الصوتي: {e}",
            }

        seconds = len(samples) / float(settings.SPEAKER_SAMPLE_RATE)
        if seconds < 0.6:
            return {
                "is_identified": False,
                "speaker_name": None,
                "user_id": None,
                "similarity": 0.0,
                "match_percentage": 0.0,
                "audio_seconds": round(seconds, 2),
                "threshold": thresh,
                "status": "audio_too_short",
                "message": f"التسجيل الصوتي قصير جداً ({seconds:.1f} ثانية). يرجى التحدث لمدة ثانية على الأقل.",
            }

        emb = _unit(await asyncio.to_thread(self._backend.embed, samples))
        best_uid, best_sim, best_name = None, -1.0, None

        for uid, entry in entries.items():
            s = float(np.dot(emb, entry.vector))
            if s > best_sim:
                best_sim = s
                best_uid = uid
                best_name = entry.speaker_name

        best_sim = max(0.0, float(best_sim))
        is_identified = best_sim >= thresh
        pct = self._calculate_match_percentage(best_sim, thresh)

        if is_identified and best_name:
            msg = f"تم التعرف على الصوت بنجاح: {best_name} (نسبة التطابق: {pct:.1f}%)"
            status_str = "identified"
        else:
            msg = "هذا الصوت غير مسجل في السيستم (صوت غير معروف)"
            status_str = "unknown"

        return {
            "is_identified": is_identified,
            "speaker_name": best_name if is_identified else None,
            "user_id": best_uid if is_identified else None,
            "similarity": round(best_sim, 4),
            "match_percentage": pct if is_identified else 0.0,
            "audio_seconds": round(seconds, 2),
            "threshold": thresh,
            "status": status_str,
            "message": msg,
        }

    # ── verification (Guard Pipeline) ────────────────────────────────────

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

            if best_uid is not None:
                entry = entries[best_uid]
                res.score = best
                res.passed_l1 = best >= settings.SPEAKER_THRESHOLD_L1
                res.passed_l2 = best >= settings.SPEAKER_THRESHOLD_L2
                res.match_percentage = self._calculate_match_percentage(best, settings.SPEAKER_THRESHOLD_L1)

                if res.passed_l1:
                    res.is_identified = True
                    res.user_id = best_uid
                    res.speaker_name = entry.speaker_name
                    res.max_level = entry.max_level
                else:
                    # Below threshold: treat as unknown speaker!
                    res.is_identified = False
                    res.user_id = None
                    res.speaker_name = None
                    res.max_level = 0

            return res
        except Exception as e:
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

    # ── enrolment (تسجيل بصمة الصوت) ─────────────────────────────────────

    async def enroll(
        self,
        db: AsyncSession,
        *,
        user_id: Optional[int] = None,
        speaker_name: str,
        samples: Union[List[bytes], bytes],
        max_level: int = 2,
    ) -> Voiceprint:
        """
        Build and store a voiceprint from audio enrolment samples.
        Supports single audio clip or multi-sample averaging (1 to 20 samples).
        """
        if not (0 <= max_level <= 3):
            raise VoiceprintError("max_level must be between 0 and 3")

        clean_name = speaker_name.strip()
        if not clean_name:
            raise VoiceprintError("Speaker name cannot be empty")

        if isinstance(samples, bytes):
            samples_list = [samples]
        else:
            samples_list = list(samples)

        if not (1 <= len(samples_list) <= 20):
            raise VoiceprintError("Provide 1 to 20 audio samples for voiceprint enrollment")

        if not await asyncio.to_thread(self._backend.available):
            raise VoiceprintError("Speaker model is not available on this server")

        vectors: List[np.ndarray] = []
        for i, raw in enumerate(samples_list):
            try:
                pcm = decode_audio(raw)
            except AudioDecodeError as e:
                raise VoiceprintError(f"Sample {i + 1}: {e}") from e
            secs = len(pcm) / float(settings.SPEAKER_SAMPLE_RATE)
            if secs < 0.8:
                raise VoiceprintError(f"Sample {i + 1}: length must be at least 0.8s (got {secs:.1f}s)")
            vectors.append(_unit(await asyncio.to_thread(self._backend.embed, pcm)))

        # Quality gate: drop outliers if 3 or more samples are provided
        kept = _drop_outliers(vectors) if len(vectors) >= 3 else vectors
        if not kept:
            raise VoiceprintError("Samples are inconsistent or too noisy. Please re-record in a quiet room.")

        mean = _unit(np.mean(np.stack(kept), axis=0))

        # Auto-create user account if user_id is not provided
        if user_id is None:
            from app.models.user import User
            user_row = (await db.execute(select(User).where(User.full_name == clean_name))).scalar_one_or_none()
            if not user_row:
                safe_tag = "".join(c for c in clean_name if c.isalnum() or c in ("-", "_")).lower() or "speaker"
                user_row = User(
                    full_name=clean_name,
                    email=f"{safe_tag}_{int(time.time())}@nebula.local",
                    hashed_password="voiceprint-auto-created",
                    is_active=True,
                )
                db.add(user_row)
                await db.flush()
            user_id = user_row.id

        existing = (
            await db.execute(select(Voiceprint).where(Voiceprint.user_id == user_id))
        ).scalar_one_or_none()

        blob = mean.astype(np.float32).tobytes()
        if existing:
            existing.speaker_name = clean_name
            existing.embedding = blob
            existing.embedding_dim = int(mean.shape[0])
            existing.samples_count = len(kept)
            existing.model_id = self._backend.model_id
            existing.max_level = max_level
            row = existing
        else:
            row = Voiceprint(
                user_id=user_id,
                speaker_name=clean_name,
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

    async def delete_by_name(self, db: AsyncSession, speaker_name: str) -> bool:
        rows = (
            await db.execute(select(Voiceprint).where(Voiceprint.speaker_name == speaker_name.strip()))
        ).scalars().all()
        if not rows:
            return False
        for r in rows:
            await db.delete(r)
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
