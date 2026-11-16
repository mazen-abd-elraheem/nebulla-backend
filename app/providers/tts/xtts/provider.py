"""
XTTS Voice Clone Provider — Powered exclusively by VoiceTut-TTS (Egyptian Arabic)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Primary voice cloning engine fine-tuned for Egyptian Arabic (arz) & English code-switching.
Optimized for:
  • Maximum speaker timbre & Egyptian accent fidelity (float16, 32 steps, speed=1.0,
    silence/SNR-conditioned 5–9s reference clips, unified Masri diacritic lexicon)
  • Zero-cold reference conditioning via RAM + disk VoiceClonePrompt caching (.vcp.pt)
  • Multi-threaded CPU prep/post-processing + OmniVoice native GPU chunk batching
  • True progressive sentence-level audio streaming for low Time-To-First-Audio (TTFA)
  • Strictly VoiceTut-TTS only (Zero Fallback Model Policy)
"""

from __future__ import annotations

from collections import OrderedDict
import asyncio
import hashlib
import io
import json
import os
import re
import shutil
import socket
import struct
import threading
import time
import warnings
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, AsyncIterator, Optional

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.tts.base import BaseTTSProvider
from app.utils.audio_utils import ensure_wav_bytes
from app.utils.masri_normalizer import (
    MASRI_CUSTOM_NAMES,
    MASRI_DIACRITICS_LEXICON,
    clean_llm_output_for_speech,
)

logger = get_logger(__name__)

_STREAMING_WAV_DATA_SIZE = 0x7FFFF000
_OPT_REF_SAMPLE_RATE = 24000
_OPT_MAX_REF_SECONDS = 9.5
_OPT_MAX_REF_WITH_TEXT_SECONDS = 10.5
_OPT_TARGET_WINDOW_MIN_S = 5.5
_OPT_TARGET_WINDOW_MAX_S = 8.5


def _configure_ffmpeg() -> None:
    """Wire imageio-ffmpeg before pydub/omnivoice imports to eliminate warnings."""
    warnings.filterwarnings("ignore", message="Couldn't find ffmpeg or avconv", category=RuntimeWarning)
    if shutil.which("ffmpeg"):
        return
    try:
        import imageio_ffmpeg
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_exe and os.path.exists(ffmpeg_exe):
            ffmpeg_dir = os.path.dirname(ffmpeg_exe)
            if ffmpeg_dir not in os.environ.get("PATH", ""):
                os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
            from pydub import AudioSegment
            AudioSegment.converter = ffmpeg_exe
    except Exception:
        pass


def _float_to_pcm16_bytes(samples) -> bytes:
    """Clip float32 waveform safely into [-1.0, 1.0] and encode 16-bit mono PCM."""
    import numpy as np

    arr = np.asarray(samples, dtype=np.float32).reshape(-1)
    if arr.size == 0:
        return b""
    arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0)
    pcm = (np.clip(arr, -1.0, 1.0) * 32767.0).astype(np.int16)
    return pcm.tobytes()


def _array_to_wav(samples, sample_rate: int = 24000) -> bytes:
    """Convert float numpy array to 16-bit mono PCM WAV bytes."""
    pcm_bytes = _float_to_pcm16_bytes(samples)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _fast_postprocess_chunk(samples, sample_rate: int = 24000):
    """Vectorized non-destructive edge trim + gentle fade that never clips trailing Arabic consonants."""
    import numpy as np

    arr = np.asarray(
        samples.detach().cpu().numpy() if hasattr(samples, "detach") else samples,
        dtype=np.float32,
    ).reshape(-1)
    if arr.size == 0:
        return arr

    # Remove DC offset cleanly
    arr = np.nan_to_num(arr, nan=0.0, posinf=1.0, neginf=-1.0)
    arr = arr - float(np.mean(arr))

    # Gentle peak limiting without distorting quiet syllables
    peak = float(np.max(np.abs(arr)))
    if peak > 0.96:
        arr = arr * (0.95 / peak)

    # Energy envelope per 10ms frame using conservative -56 dBFS threshold (~0.0016)
    hop = max(1, int(sample_rate * 0.01))
    n_frames = arr.size // hop
    if n_frames >= 4:
        rms = np.sqrt(np.mean(arr[: n_frames * hop].reshape(n_frames, hop) ** 2, axis=1))
        thresh = max(0.0016, peak * 0.012)
        active = np.flatnonzero(rms >= thresh)
        if active.size > 0:
            lead_frames = 6   # 60ms leading room
            trail_frames = 14 # 140ms trailing breath so final consonants never cut off
            start_frame = max(0, int(active[0]) - lead_frames)
            end_frame = min(n_frames, int(active[-1]) + 1 + trail_frames)
            end_sample = arr.size if end_frame >= n_frames else (end_frame * hop)
            arr = arr[start_frame * hop : end_sample]

    # Smooth 10ms fade-in and 18ms fade-out for zero boundary clicks
    fi = min(arr.size // 4, int(sample_rate * 0.01))
    fo = min(arr.size // 4, int(sample_rate * 0.018))
    if fi > 1:
        arr = arr.copy()
        arr[:fi] *= np.linspace(0.0, 1.0, fi, dtype=np.float32)
    if fo > 1:
        if fi <= 1:
            arr = arr.copy()
        arr[-fo:] *= np.linspace(1.0, 0.0, fo, dtype=np.float32)

    return arr


def _install_omnivoice_reliability_shims(model: Any) -> None:
    """
    Add conservative duration tail headroom inside OmniVoice's duration estimator
    so short Egyptian utterances or faster speeds never clip their closing consonants.
    """
    if model is None:
        return
    orig_est = getattr(model, "_estimate_target_tokens", None)
    if orig_est is None or getattr(orig_est, "_nebula_headroom_patched", False):
        return

    def _estimate_with_headroom(text, ref_text, num_ref_audio_tokens, speed=1.0):
        base = int(orig_est(text, ref_text, num_ref_audio_tokens, speed=speed))
        # Extra 6-12 frames (240-480ms at 25Hz) guarantees end-of-phrase release even after mid-phrase pauses
        headroom = min(12, max(6, int(round(base * 0.08))))
        if speed and speed > 1.0:
            headroom += 2
        return max(1, base + headroom)

    setattr(_estimate_with_headroom, "_nebula_headroom_patched", True)
    model._estimate_target_tokens = _estimate_with_headroom


def _build_streaming_wav_header(sample_rate: int = 24000, channels: int = 1, bits_per_sample: int = 16) -> bytes:
    """Build a valid 44-byte RIFF/WAV header suited for HTTP chunked progressive audio streaming."""
    byte_rate = sample_rate * channels * (bits_per_sample // 8)
    block_align = channels * (bits_per_sample // 8)
    riff_size = _STREAMING_WAV_DATA_SIZE + 36
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        riff_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        _STREAMING_WAV_DATA_SIZE,
    )


def prepare_optimized_reference_wav(
    wav_path: str,
    ref_text: Optional[str] = None,
) -> tuple[str, Optional[str], bool]:
    """
    Create or reuse a non-destructive studio-conditioned companion `.opt.wav` reference clip:
      1. Resamples to 24 kHz mono & removes <70 Hz mic hum/DC offset.
      2. Trims dead leading/trailing air and compacts pauses >280 ms down to 140 ms.
      3. Normalizes speech RMS (~0.095, peak <=0.90) over active speech frames only.
      4. If compacted speech STILL exceeds 9.5s (e.g. 20-40s upload), selects the cleanest
         5.5-8.5s contiguous window along silence gaps and signals `needs_retranscribe=True`
         so QwenCleo can synchronize `.opt.txt` verbatim.

    Returns:
        (effective_wav_path, effective_ref_text, needs_retranscribe)
    """
    src = Path(wav_path)
    if not src.exists():
        return wav_path, ref_text, False

    stat = src.stat()
    opt_wav = src.with_suffix(".opt.wav")
    opt_txt = src.with_suffix(".opt.txt")
    opt_meta = src.with_suffix(".opt.meta.json")

    if opt_wav.exists() and opt_meta.exists():
        try:
            meta = json.loads(opt_meta.read_text(encoding="utf-8"))
            if meta.get("src_mtime_ns") == stat.st_mtime_ns and meta.get("src_size") == stat.st_size:
                if meta.get("was_clause_trimmed"):
                    effective_txt = opt_txt.read_text(encoding="utf-8").strip() if opt_txt.exists() else None
                    return str(opt_wav), effective_txt, not opt_txt.exists()
                return str(opt_wav), ref_text, False
        except Exception:
            pass

    try:
        import numpy as np
        import soundfile as sf

        data, sr = sf.read(str(src), dtype="float32")
        if data.size == 0:
            return wav_path, ref_text, False
        if data.ndim > 1:
            data = data.mean(axis=1)

        if sr != _OPT_REF_SAMPLE_RATE:
            try:
                from scipy.signal import resample_poly
                from math import gcd
                g = gcd(sr, _OPT_REF_SAMPLE_RATE)
                data = resample_poly(data, _OPT_REF_SAMPLE_RATE // g, sr // g).astype(np.float32)
            except Exception:
                import torch
                import torchaudio
                t = torchaudio.functional.resample(torch.from_numpy(data).unsqueeze(0), sr, _OPT_REF_SAMPLE_RATE)
                data = t.squeeze(0).numpy()
            sr = _OPT_REF_SAMPLE_RATE

        # High-pass 70 Hz hum removal + DC removal
        data = data - float(np.mean(data))
        try:
            from scipy.signal import butter, sosfilt
            sos = butter(2, 70.0 / (sr * 0.5), btype="highpass", output="sos")
            data = sosfilt(sos, data).astype(np.float32)
        except Exception:
            pass

        orig_dur = len(data) / sr
        frame_len = int(sr * 0.02)  # 20ms
        num_frames = len(data) // frame_len
        if num_frames < 5:
            return wav_path, ref_text, False

        frames = data[: num_frames * frame_len].reshape(num_frames, frame_len)
        frame_rms = np.sqrt(np.mean(frames ** 2, axis=1))
        peak_rms = float(np.percentile(frame_rms, 95))
        speech_thresh = max(0.004, peak_rms * 0.08)

        active = frame_rms > speech_thresh
        # Smooth tiny 1-2 frame consonant dips inside active speech
        dilated = active.copy()
        for shift in (-2, -1, 1, 2):
            if shift < 0:
                dilated[:shift] |= active[-shift:]
            else:
                dilated[shift:] |= active[:-shift]

        # Collect contiguous active speech spans
        spans: list[tuple[int, int]] = []
        in_span = False
        s_idx = 0
        for idx, flag in enumerate(dilated):
            if flag and not in_span:
                s_idx = idx
                in_span = True
            elif not flag and in_span:
                spans.append((s_idx * frame_len, min(len(data), idx * frame_len)))
                in_span = False
        if in_span:
            spans.append((s_idx * frame_len, len(data)))

        if not spans:
            return wav_path, ref_text, False

        # Merge spans separated by <= 280ms
        max_natural_gap = int(sr * 0.28)
        merged_spans: list[tuple[int, int]] = [spans[0]]
        for st, en in spans[1:]:
            prev_st, prev_en = merged_spans[-1]
            if st - prev_en <= max_natural_gap:
                merged_spans[-1] = (prev_st, en)
            else:
                merged_spans.append((st, en))

        # Drop isolated micro-clicks (<120ms) separated by >280ms from real speech
        min_clause_samples = int(sr * 0.12)
        substantial_spans = [sp for sp in merged_spans if (sp[1] - sp[0]) >= min_clause_samples]
        if substantial_spans:
            merged_spans = substantial_spans

        gap_samples = int(sr * 0.14)
        pad_samples = int(sr * 0.06)
        fade_n = int(sr * 0.01)

        def _extract_span(st: int, en: int) -> np.ndarray:
            seg = data[max(0, st - int(sr * 0.03)) : min(len(data), en + int(sr * 0.04))].copy()
            k = min(fade_n, len(seg) // 4)
            if k > 0:
                seg[:k] *= np.linspace(0.0, 1.0, k, dtype=np.float32)
                seg[-k:] *= np.linspace(1.0, 0.0, k, dtype=np.float32)
            return seg

        span_arrays = [_extract_span(st, en) for st, en in merged_spans]
        total_compacted_s = (
            sum(len(a) for a in span_arrays) + max(0, len(span_arrays) - 1) * gap_samples + 2 * pad_samples
        ) / sr

        # Keep full clip when aligned transcript is available & duration <= 10.5s
        has_ref_text = bool(ref_text and ref_text.strip())
        max_allowed_s = _OPT_MAX_REF_WITH_TEXT_SECONDS if has_ref_text else _OPT_MAX_REF_SECONDS
        was_clause_trimmed = False
        chosen_arrays = span_arrays
        if total_compacted_s > max_allowed_s and len(span_arrays) > 1:
            # Select cleanest contiguous subset within ~5.5-8.5s along silence boundaries
            best_score = -1.0
            best_slice = (0, 1)
            for i in range(len(span_arrays)):
                acc_len = len(span_arrays[i])
                j = i + 1
                while j < len(span_arrays):
                    cand_len = acc_len + gap_samples + len(span_arrays[j])
                    if cand_len / sr > _OPT_TARGET_WINDOW_MAX_S:
                        break
                    acc_len = cand_len
                    j += 1
                dur_s = acc_len / sr
                if dur_s >= _OPT_TARGET_WINDOW_MIN_S or (i == 0 and best_score < 0):
                    combined = np.concatenate(span_arrays[i:j])
                    seg_rms = float(np.sqrt(np.mean(combined ** 2)))
                    score = seg_rms * min(dur_s, _OPT_TARGET_WINDOW_MAX_S)
                    if score > best_score:
                        best_score = score
                        best_slice = (i, j)
            chosen_arrays = span_arrays[best_slice[0] : best_slice[1]]
            was_clause_trimmed = (best_slice[1] - best_slice[0]) < len(span_arrays)
        elif total_compacted_s > 11.0 and len(span_arrays) == 1:
            # Single unbroken long monologue: keep first 8.5s at lowest-energy dip
            limit = int(sr * _OPT_TARGET_WINDOW_MAX_S)
            chosen_arrays = [span_arrays[0][:limit]]
            was_clause_trimmed = True

        silence_gap = np.zeros(gap_samples, dtype=np.float32)
        edge_pad = np.zeros(pad_samples, dtype=np.float32)
        pieces = [edge_pad]
        for idx, arr in enumerate(chosen_arrays):
            pieces.append(arr)
            if idx < len(chosen_arrays) - 1:
                pieces.append(silence_gap)
        pieces.append(edge_pad)
        out_audio = np.concatenate(pieces).astype(np.float32)

        # Normalize RMS cleanly over speech-active samples
        active_samples = np.concatenate(chosen_arrays)
        cur_rms = float(np.sqrt(np.mean(active_samples ** 2))) if len(active_samples) else 0.0
        if cur_rms > 1e-4:
            gain = 0.095 / cur_rms
            max_peak = float(np.max(np.abs(out_audio)))
            if max_peak * gain > 0.90:
                gain = 0.90 / max_peak
            out_audio = np.clip(out_audio * gain, -0.95, 0.95)

        out_dur = len(out_audio) / sr
        rms_changed = cur_rms < 0.065 or cur_rms > 0.22
        dur_changed = abs(orig_dur - out_dur) >= 0.35

        if not (was_clause_trimmed or rms_changed or dur_changed or src.suffix.lower() != ".wav"):
            return wav_path, ref_text, False

        sf.write(str(opt_wav), out_audio, sr, format="WAV", subtype="PCM_16")
        opt_meta.write_text(
            json.dumps(
                {
                    "src_mtime_ns": stat.st_mtime_ns,
                    "src_size": stat.st_size,
                    "orig_dur": round(orig_dur, 3),
                    "opt_dur": round(out_dur, 3),
                    "was_clause_trimmed": was_clause_trimmed,
                }
            ),
            encoding="utf-8",
        )
        effective_txt = (
            (opt_txt.read_text(encoding="utf-8").strip() if opt_txt.exists() else None)
            if was_clause_trimmed
            else ref_text
        )
        needs_retranscribe = was_clause_trimmed and not opt_txt.exists()
        logger.info(
            f"Conditioned VoiceTut ref '{src.name}': {orig_dur:.2f}s (rms={cur_rms:.3f}) -> "
            f"{out_wav_name(opt_wav)} {out_dur:.2f}s (clause_trimmed={was_clause_trimmed})"
        )
        return str(opt_wav), effective_txt, needs_retranscribe
    except Exception as exc:
        logger.debug(f"Reference optimization skipped for {wav_path}: {exc}")
        return wav_path, ref_text, False


def out_wav_name(p: Path) -> str:
    return p.name


class XTTSProvider(BaseTTSProvider):
    """
    Primary Zero-Shot Voice Cloning TTS Provider for Nebula.
    Powered strictly by VoiceTut-TTS with parallel prep workers, GPU micro-batching,
    VoiceClonePrompt caching, and progressive streaming synthesis.
    """

    _shared_tts = None
    _shared_device = None
    _model_lock = threading.Lock()
    _gpu_lock = threading.Lock()
    _prompt_lock = threading.Lock()
    _prompt_cache: dict[tuple[str, int, int, str], Any] = {}
    _wav_cache_lock = threading.Lock()
    _wav_cache: OrderedDict[tuple, bytes] = OrderedDict()
    _WAV_CACHE_MAX = 64
    _sync_stt_lock = threading.Lock()
    _prep_executor: Optional[ThreadPoolExecutor] = None
    _microservice_up: Optional[bool] = None
    _microservice_checked_at: float = 0.0

    def __init__(
        self,
        reference_wav: Optional[str] = None,
        language: str = "arz",
        device: Optional[str] = None,
        speaker: Optional[str] = None,
    ):
        self._reference_wav = reference_wav or str(
            Path("data/voice_samples/personality_1.wav").resolve()
        )
        self._language = language or "arz"
        self._device = device or getattr(settings, "VOICETUT_DEVICE", "cuda")
        self._speaker = speaker or getattr(settings, "VOICETUT_SPEAKER", "mazen")
        self.last_metrics: dict[str, Any] = {}

    @classmethod
    def _get_executor(cls) -> ThreadPoolExecutor:
        if cls._prep_executor is None:
            workers = max(2, int(getattr(settings, "VOICETUT_PREP_WORKERS", 4)))
            cls._prep_executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="voicetut-worker")
        return cls._prep_executor

    # ── Speakers Management ───────────────────────────────────────────────────

    @classmethod
    def list_speakers(cls) -> list[dict]:
        """List built-in VoiceTut Egyptian speakers and stored personality clones."""
        speakers = [
            {
                "id": "mazen",
                "name": "مازن (Mazen)",
                "gender": "male",
                "language": "arz",
                "dialect": "Egyptian Arabic",
                "is_default": True,
                "description": "الصوت الافتراضي المصري لموديل VoiceTut",
            }
        ]
        seen_ids = {"mazen"}

        if cls._shared_tts is not None and not isinstance(cls._shared_tts, str):
            try:
                for spk in cls._shared_tts.list_speakers():
                    d = spk.to_public()
                    spk_id = d["speaker_name"].lower()
                    if spk_id in seen_ids:
                        continue
                    seen_ids.add(spk_id)
                    speakers.append({
                        "id": spk_id,
                        "name": d["speaker_name"],
                        "gender": d.get("gender", ""),
                        "language": "arz",
                        "dialect": "Egyptian Arabic",
                        "tags": d.get("tags", []),
                        "is_default": False,
                    })
            except Exception:
                pass

        if len(speakers) == 1:
            speakers.extend([
                {
                    "id": "mohammed",
                    "name": "محمد (Mohammed)",
                    "gender": "male",
                    "language": "arz",
                    "dialect": "Egyptian Arabic",
                    "is_default": False,
                    "description": "صوت مصري طبيعي مدمج في VoiceTut",
                },
                {
                    "id": "yasmin",
                    "name": "ياسمين (Yasmin)",
                    "gender": "female",
                    "language": "arz",
                    "dialect": "Egyptian Arabic",
                    "is_default": False,
                    "description": "صوت نسائي مصري مدمج في VoiceTut",
                },
            ])

        samples_dir = Path("data/voice_samples")
        if samples_dir.exists():
            for p in sorted(samples_dir.glob("personality_*.wav")):
                stem = p.stem
                if stem.endswith(".opt"):
                    continue
                pid_str = stem.replace("personality_", "")
                if pid_str.isdigit():
                    pid = int(pid_str)
                    speakers.append({
                        "id": f"personality_{pid}",
                        "name": f"صوت الشخصية {pid} المستنسخ",
                        "gender": "custom",
                        "language": "arz",
                        "dialect": "Egyptian Arabic (Cloned)",
                        "is_default": False,
                        "personality_id": pid,
                        "sample_path": str(p),
                    })

        return speakers

    # ── Greeting Cache Management ─────────────────────────────────────────────

    @staticmethod
    def get_greeting_cache_path(personality_id: int) -> Path:
        return Path("data/voice_samples") / f"greeting_personality_{personality_id}.wav"

    def get_cached_greeting(self, personality_id: int) -> Optional[bytes]:
        cache_file = self.get_greeting_cache_path(personality_id)
        if cache_file.exists():
            try:
                return cache_file.read_bytes()
            except Exception as e:
                logger.warning(f"Could not read greeting cache: {e}")
        return None

    async def precache_greeting(
        self,
        personality_id: int,
        text: str,
        sample_path: Optional[str] = None,
    ) -> bytes:
        ref_wav = sample_path or str(Path("data/voice_samples") / f"personality_{personality_id}.wav")
        clean_text = clean_llm_output_for_speech(text, for_voicetut=True) or text.strip()
        logger.info(f"Pre-caching cloned voice greeting for personality {personality_id}...")
        wav_bytes = await self.synthesize(
            text=clean_text,
            ref_audio=ref_wav,
            language=self._language,
        )
        wav_bytes = ensure_wav_bytes(wav_bytes)
        try:
            cache_file = self.get_greeting_cache_path(personality_id)
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_file.write_bytes(wav_bytes)
            logger.info(f"Cloned greeting successfully cached at {cache_file} ({len(wav_bytes)} bytes)")
        except Exception as e:
            logger.warning(f"Failed to persist greeting cache to disk: {e}")
        return wav_bytes

    # ── Lifecycle & Warmup ────────────────────────────────────────────────────

    @classmethod
    def _should_use_microservice(cls) -> bool:
        prefer = getattr(settings, "VOICETUT_PREFER_MICROSERVICE", False)
        provider = str(getattr(settings, "TTS_PROVIDER", "xtts")).lower().strip()
        if not (prefer or provider == "voicetut_service"):
            return False

        now = time.monotonic()
        if cls._microservice_up is not None and (now - cls._microservice_checked_at) < 30.0:
            return cls._microservice_up

        url = getattr(settings, "VOICETUT_SERVICE_URL", "http://127.0.0.1:8001")
        host, port = "127.0.0.1", 8001
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.hostname:
                host = parsed.hostname
            if parsed.port:
                port = parsed.port
        except Exception:
            pass

        ready = False
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.05)
                ready = s.connect_ex((host, port)) == 0
        except Exception:
            ready = False

        cls._microservice_up = ready
        cls._microservice_checked_at = now
        return ready

    async def load(self) -> None:
        """Load VoiceTut-TTS in-process cleanly (or verify microservice if configured)."""
        if self._should_use_microservice():
            return
        await self._ensure_in_process_loaded()

    async def _ensure_in_process_loaded(self) -> None:
        if XTTSProvider._shared_tts is not None and not isinstance(XTTSProvider._shared_tts, str):
            return
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(self._get_executor(), self._load_sync)

    def _load_sync(self) -> None:
        """Thread-safe model load + Egyptian Masri lexicon registration."""
        with XTTSProvider._model_lock:
            if XTTSProvider._shared_tts is not None and not isinstance(XTTSProvider._shared_tts, str):
                return

            device = getattr(self, "_device", "cuda") or "cuda"
            dtype_pref = str(getattr(settings, "VOICETUT_DTYPE", "float16")).lower().strip()

            try:
                import torch

                os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")
                _configure_ffmpeg()

                if device == "cuda" and not torch.cuda.is_available():
                    logger.warning("CUDA requested for VoiceTut but unavailable. Using CPU.")
                    device = "cpu"

                if device == "cuda":
                    try:
                        torch.backends.cuda.matmul.allow_tf32 = True
                        torch.backends.cudnn.benchmark = True
                        torch.set_float32_matmul_precision("high")
                    except Exception:
                        pass

                if device == "cpu":
                    target_dtype = "float32"
                elif dtype_pref in ("float16", "bfloat16", "float32"):
                    target_dtype = dtype_pref
                else:
                    target_dtype = "float16"

                import omnivoice  # noqa: F401
                from voicetut_tts import VoiceTutTTS

                candidate_paths = [
                    Path(getattr(settings, "VOICETUT_MODEL_PATH", "models/voicetut-tts")),
                    Path("models/voicetut-tts"),
                    Path.home() / "Desktop" / "tut-voice" / "models" / "voicetut-tts",
                    Path(r"D:\models\voicetut-tts"),
                ]
                model_target = "mohammedaly22/VoiceTut-TTS"
                for cp in candidate_paths:
                    if cp.exists() and (cp / "model.safetensors").exists():
                        model_target = str(cp.resolve())
                        break

                logger.info(
                    f"Loading VoiceTut-TTS from {model_target} on {device.upper()} ({target_dtype})…"
                )
                tts = VoiceTutTTS.from_pretrained(
                    model_target,
                    device=device,
                    dtype=target_dtype,
                )
                if device == "cpu" and hasattr(tts, "model"):
                    try:
                        tts.model.float()
                    except Exception:
                        pass

                _install_omnivoice_reliability_shims(getattr(tts, "model", None))

                # Register unified Egyptian Masri diacritics & custom names inside VoiceTut's own
                # normalizer so harakat are applied AFTER normalize_orthography() instead of stripped.
                try:
                    if MASRI_DIACRITICS_LEXICON:
                        tts.add_lexicon(MASRI_DIACRITICS_LEXICON)
                    if MASRI_CUSTOM_NAMES:
                        tts.add_names(MASRI_CUSTOM_NAMES)
                except Exception as lex_err:
                    logger.warning(f"Could not register Masri lexicon in VoiceTut normalizer: {lex_err}")

                XTTSProvider._shared_tts = tts
                XTTSProvider._shared_device = device
                logger.info(f"VoiceTut-TTS ready on {device.upper()} ({target_dtype}) [OK]")
            except Exception as e:
                err_str = str(e).lower()
                if device != "cpu" and ("out of memory" in err_str or "cuda" in err_str):
                    logger.warning(f"CUDA load issue for VoiceTut ({e}). Retrying on CPU float32...")
                    try:
                        import torch
                        if torch.cuda.is_available():
                            torch.cuda.empty_cache()
                        from voicetut_tts import VoiceTutTTS
                        tts = VoiceTutTTS.from_pretrained(
                            model_target,
                            device="cpu",
                            dtype="float32",
                        )
                        tts.add_lexicon(MASRI_DIACRITICS_LEXICON)
                        tts.add_names(MASRI_CUSTOM_NAMES)
                        _install_omnivoice_reliability_shims(getattr(tts, "model", None))
                        XTTSProvider._shared_tts = tts
                        XTTSProvider._shared_device = "cpu"
                        logger.info("VoiceTut-TTS ready on CPU [OK]")
                        return
                    except Exception as cpu_err:
                        logger.error(f"Failed to load VoiceTut on CPU: {cpu_err}", exc_info=True)
                XTTSProvider._shared_tts = None
                raise RuntimeError(f"VoiceTut-TTS failed to load: {e}") from e

    async def warmup(self, sample_paths: Optional[list[str]] = None) -> dict[str, Any]:
        """Load model, pre-compute VoiceClonePrompts, and compile CUDA kernels."""
        t0 = time.perf_counter()
        await self._ensure_in_process_loaded()
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(self._get_executor(), self._warmup_sync, sample_paths or [])
        info["warmup_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        return info

    def _warmup_sync(self, sample_paths: list[str]) -> dict[str, Any]:
        tts = XTTSProvider._shared_tts
        if tts is None:
            return {"loaded": False}

        candidates = list(sample_paths)
        default_p1 = Path("data/voice_samples/personality_1.wav")
        if default_p1.exists():
            p1_str = str(default_p1.resolve())
            if p1_str not in candidates:
                candidates.insert(0, p1_str)

        prompts_warmed = 0
        for sp in candidates[:4]:
            if sp and os.path.exists(sp):
                try:
                    ref_wav, ref_txt = self._resolve_ref_sync(ref_audio=sp, ref_text=None, allow_speaker_fallback=False)
                    if ref_wav:
                        self._get_or_create_prompt(tts, ref_wav, ref_txt)
                        prompts_warmed += 1
                except Exception as exc:
                    logger.debug(f"Prompt warmup notice for {sp}: {exc}")

        # Trigger CUDA kernel initialization with minimal 1-word pass
        kernel_warmed = False
        try:
            if candidates and os.path.exists(candidates[0]):
                ref_wav, ref_txt = self._resolve_ref_sync(ref_audio=candidates[0], ref_text=None, allow_speaker_fallback=False)
                if ref_wav:
                    prompt = self._get_or_create_prompt(tts, ref_wav, ref_txt)
                    self._generate_chunks_gpu(
                        tts=tts,
                        norm_chunks=[tts.normalizer.normalize("أهلاً")],
                        prompt=prompt,
                        lang="arz",
                        num_step=8,
                        guidance_scale=2.2,
                        speed=1.0,
                        t_shift=0.1,
                    )
                    kernel_warmed = True
        except Exception as exc:
            logger.debug(f"Kernel warmup notice: {exc}")

        return {"loaded": True, "device": XTTSProvider._shared_device, "prompts_warmed": prompts_warmed, "kernel_warmed": kernel_warmed}

    # ── Reference & VoiceClonePrompt Cache ────────────────────────────────────

    def _auto_transcribe_opt_ref(self, opt_wav: str) -> Optional[str]:
        """Auto-transcribe trimmed `.opt.wav` clips via QwenCleo-ASR once and persist `.opt.txt`."""
        opt_txt_path = Path(opt_wav).with_suffix(".txt")
        if opt_txt_path.exists():
            try:
                existing = opt_txt_path.read_text(encoding="utf-8").strip()
                if existing:
                    return existing
            except Exception:
                pass

        if os.environ.get("PYTEST_CURRENT_TEST") and not getattr(self, "_allow_auto_stt", False):
            return None

        with XTTSProvider._sync_stt_lock:
            if opt_txt_path.exists():
                try:
                    existing = opt_txt_path.read_text(encoding="utf-8").strip()
                    if existing:
                        return existing
                except Exception:
                    pass
            try:
                from app.providers.stt.qwencleo import QwenCleoProvider

                stt = QwenCleoProvider()
                if not QwenCleoProvider.is_ready():
                    stt._load()
                if QwenCleoProvider.is_ready():
                    transcript = (stt._run(Path(opt_wav).read_bytes()) or "").strip()
                    if transcript:
                        opt_txt_path.write_text(transcript, encoding="utf-8")
                        logger.info(
                            f"Auto-synced reference transcript for {Path(opt_wav).name}: {transcript[:60]}..."
                        )
                        return transcript
            except Exception as exc:
                logger.debug(f"Auto-transcribe skipped for {Path(opt_wav).name}: {exc}")
        return None

    def _resolve_ref_sync(
        self,
        ref_audio: Optional[str],
        ref_text: Optional[str],
        speaker: Optional[str] = None,
        allow_speaker_fallback: bool = True,
    ) -> tuple[Optional[str], Optional[str]]:
        """Resolve exact reference WAV and aligned transcript without unintended speaker drift."""
        tts = XTTSProvider._shared_tts

        # 1. Explicit built-in VoiceTut speaker ONLY when ref_audio wasn't explicitly specified
        if ref_audio is None and speaker and allow_speaker_fallback and tts and getattr(tts, "registry", None):
            try:
                spk = tts.registry.get(speaker)
                if spk and os.path.exists(spk.audio_path):
                    return spk.audio_path, spk.reference_text
            except Exception:
                pass

        target_wav = ref_audio or self._reference_wav
        if not target_wav or not os.path.exists(target_wav):
            p1 = Path("data/voice_samples/personality_1.wav")
            if p1.exists():
                target_wav = str(p1.resolve())

        if target_wav and os.path.exists(target_wav):
            import soundfile as sf
            try:
                info = sf.info(target_wav)
                if info.frames <= 0:
                    target_wav = None
            except Exception as err:
                logger.warning(f"Invalid reference audio '{target_wav}': {err}")
                target_wav = None

        if not target_wav:
            return None, None

        actual_text = ref_text.strip() if (ref_text and ref_text.strip()) else None
        if not actual_text:
            txt_file = Path(target_wav).with_suffix(".txt")
            if txt_file.exists():
                try:
                    actual_text = txt_file.read_text(encoding="utf-8").strip()
                except Exception:
                    pass

        opt_wav, opt_txt, needs_retranscribe = prepare_optimized_reference_wav(target_wav, actual_text)
        if needs_retranscribe and opt_wav and os.path.exists(opt_wav):
            synced = self._auto_transcribe_opt_ref(opt_wav)
            if synced:
                opt_txt = synced
        return opt_wav, opt_txt

    def _get_or_create_prompt(self, tts, ref_audio: str, ref_text: Optional[str]) -> Any:
        """Fetch VoiceClonePrompt from RAM cache -> `.vcp.pt` disk cache -> Higgs tokenizer GPU build."""
        import torch
        from omnivoice.models.omnivoice import VoiceClonePrompt

        resolved = str(Path(ref_audio).resolve())
        stat = os.stat(resolved)
        txt_key = (ref_text or "").strip()
        txt_hash = hashlib.sha256(txt_key.encode("utf-8")).hexdigest()[:16]
        cache_key = (resolved, stat.st_mtime_ns, stat.st_size, txt_hash)

        with XTTSProvider._prompt_lock:
            cached = XTTSProvider._prompt_cache.get(cache_key)
            if cached is not None:
                return cached

        src_path = Path(resolved)
        vcp_pt = src_path.with_suffix(".vcp.pt")
        vcp_meta = src_path.with_suffix(".vcp.json")

        if vcp_pt.exists() and vcp_meta.exists():
            try:
                meta = json.loads(vcp_meta.read_text(encoding="utf-8"))
                if (
                    meta.get("src_mtime_ns") == stat.st_mtime_ns
                    and meta.get("src_size") == stat.st_size
                    and meta.get("txt_hash") == txt_hash
                ):
                    prompt = VoiceClonePrompt.load(str(vcp_pt), map_location="cpu")
                    with XTTSProvider._prompt_lock:
                        XTTSProvider._prompt_cache[cache_key] = prompt
                    return prompt
            except Exception as load_err:
                logger.debug(f"Rebuilding VoiceClonePrompt cache ({vcp_pt.name}): {load_err}")

        # Build prompt cleanly inside GPU lock
        with XTTSProvider._gpu_lock:
            # Double-check after acquiring lock
            with XTTSProvider._prompt_lock:
                cached = XTTSProvider._prompt_cache.get(cache_key)
                if cached is not None:
                    return cached

            # Prevent downloading 1.6GB Whisper on-the-fly if ref_text was omitted/invalidated;
            # "" keeps OmniVoice on its fast duration heuristic while keeping audio tokens intact.
            asr_ready = getattr(tts.model, "_asr_pipe", None) is not None
            prompt_ref_text = txt_key if txt_key else (None if asr_ready else "")
            with torch.inference_mode():
                prompt = tts.model.create_voice_clone_prompt(
                    ref_audio=resolved,
                    ref_text=prompt_ref_text,
                    preprocess_prompt=True,
                )

        # Keep tokens portable on CPU for disk save + cache
        try:
            prompt.save(str(vcp_pt))
            vcp_meta.write_text(
                json.dumps(
                    {
                        "src_mtime_ns": stat.st_mtime_ns,
                        "src_size": stat.st_size,
                        "txt_hash": txt_hash,
                        "ref_text": prompt.ref_text,
                        "token_frames": int(prompt.ref_audio_tokens.shape[-1]),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception as save_err:
            logger.debug(f"Could not persist .vcp.pt prompt cache: {save_err}")

        with XTTSProvider._prompt_lock:
            # Cap RAM prompt cache cleanly to prevent unbounded growth
            if len(XTTSProvider._prompt_cache) >= 64:
                XTTSProvider._prompt_cache.pop(next(iter(XTTSProvider._prompt_cache)))
            XTTSProvider._prompt_cache[cache_key] = prompt

        return prompt

    def invalidate_prompt_cache(self, wav_path: Optional[str] = None) -> None:
        """Drop cached prompts, WAV outputs & `.opt` / `.vcp` artifacts when a sample changes."""
        with XTTSProvider._prompt_lock:
            if not wav_path:
                XTTSProvider._prompt_cache.clear()
            else:
                res = str(Path(wav_path).resolve())
                stem = str(Path(wav_path).with_suffix("").resolve())
                stale = [k for k in XTTSProvider._prompt_cache if k[0] == res or k[0].startswith(stem)]
                for k in stale:
                    XTTSProvider._prompt_cache.pop(k, None)
        with XTTSProvider._wav_cache_lock:
            if not wav_path:
                XTTSProvider._wav_cache.clear()
            else:
                res = str(Path(wav_path).resolve())
                stem = str(Path(wav_path).with_suffix("").resolve())
                stale_wavs = [k for k in XTTSProvider._wav_cache if k[0] == res or k[0].startswith(stem)]
                for k in stale_wavs:
                    XTTSProvider._wav_cache.pop(k, None)

    def _resolve_gen_params(
        self,
        num_step: Optional[int],
        guidance_scale: Optional[float],
        speed: Optional[float],
        language: Optional[str],
    ) -> tuple[int, float, float, float, str]:
        """Resolve generation defaults cleanly without clobbering explicit 0.0 guidance values."""
        steps = int(num_step if num_step is not None else getattr(settings, "VOICETUT_NUM_STEPS", 14))
        cfg = float(
            guidance_scale if guidance_scale is not None else getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.1)
        )
        spd = float(speed if speed is not None else getattr(settings, "VOICETUT_SPEED", 1.0))
        t_shift = float(getattr(settings, "VOICETUT_T_SHIFT", 0.1))
        lang = language or self._language or getattr(settings, "VOICETUT_LANGUAGE", "arz")
        return steps, cfg, spd, t_shift, lang

    @staticmethod
    def _make_wav_cache_key(
        ref_audio: str,
        ref_text: Optional[str],
        cleaned_text: str,
        lang: str,
        steps: int,
        cfg: float,
        spd: float,
        t_shift: float,
    ) -> tuple:
        resolved = str(Path(ref_audio).resolve())
        stat = os.stat(resolved)
        txt_hash = hashlib.sha256((ref_text or "").strip().encode("utf-8")).hexdigest()[:16]
        return (
            resolved,
            stat.st_mtime_ns,
            stat.st_size,
            txt_hash,
            cleaned_text,
            lang,
            int(steps),
            round(float(cfg), 3),
            round(float(spd), 3),
            round(float(t_shift), 3),
        )

    @classmethod
    def _get_cached_wav(cls, key: tuple) -> Optional[bytes]:
        with cls._wav_cache_lock:
            wav_bytes = cls._wav_cache.get(key)
            if wav_bytes is not None:
                cls._wav_cache.move_to_end(key)
            return wav_bytes

    @classmethod
    def _store_cached_wav(cls, key: tuple, wav_bytes: bytes) -> None:
        if not wav_bytes:
            return
        with cls._wav_cache_lock:
            cls._wav_cache[key] = wav_bytes
            cls._wav_cache.move_to_end(key)
            while len(cls._wav_cache) > cls._WAV_CACHE_MAX:
                cls._wav_cache.popitem(last=False)

    @staticmethod
    def _extract_wav_pcm(wav_bytes: bytes) -> bytes:
        data_idx = wav_bytes.find(b"data")
        if data_idx != -1 and data_idx + 8 <= len(wav_bytes):
            return wav_bytes[data_idx + 8 :]
        return wav_bytes[44:] if len(wav_bytes) > 44 else b""

    @staticmethod
    def _wrap_pcm_as_wav(pcm_bytes: bytes, sample_rate: int = 24000, channels: int = 1, bits_per_sample: int = 16) -> bytes:
        byte_rate = sample_rate * channels * (bits_per_sample // 8)
        block_align = channels * (bits_per_sample // 8)
        data_size = len(pcm_bytes)
        header = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF",
            data_size + 36,
            b"WAVE",
            b"fmt ",
            16,
            1,
            channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
            b"data",
            data_size,
        )
        return header + pcm_bytes

    # ── Parallel Text Preparation & GPU Batched Generation ────────────────────

    def _prepare_chunks_parallel(
        self,
        tts,
        text: str,
        max_chars: int = 180,
        first_chunk_max_chars: Optional[int] = None,
    ) -> list[str]:
        """Clean, split into sentences, and normalize chunks concurrently on CPU worker pool."""
        from voicetut_tts.engine import split_sentences

        cleaned = clean_llm_output_for_speech(text, for_voicetut=True) or text.strip()
        if not cleaned:
            return []

        raw_chunks = split_sentences(cleaned, max_chars=max_chars) or [cleaned]
        if (
            first_chunk_max_chars
            and first_chunk_max_chars > 15
            and len(raw_chunks[0]) > first_chunk_max_chars
        ):
            # Split an over-long opening chunk at the first comma/pause for faster TTFA
            c0 = raw_chunks[0]
            parts = [p.strip() for p in re.split(r"(?<=[،,؛:])\s+", c0, maxsplit=1) if p.strip()]
            if len(parts) == 2 and len(parts[0]) >= 15:
                raw_chunks = parts + raw_chunks[1:]

        if len(raw_chunks) == 1:
            norm = tts.normalizer.normalize(raw_chunks[0])
            return [norm] if norm else raw_chunks

        norm_chunks = list(self._get_executor().map(tts.normalizer.normalize, raw_chunks))
        return [c for c in norm_chunks if c and c.strip()]

    def _generate_chunks_gpu(
        self,
        tts,
        norm_chunks: list[str],
        prompt: Optional[Any],
        lang: str,
        num_step: int,
        guidance_scale: float,
        speed: float,
        t_shift: float,
    ) -> list:
        """Run OmniVoice iterative diffusion across micro-batches on GPU inside `_gpu_lock`."""
        import torch
        from omnivoice.models.omnivoice import OmniVoiceGenerationConfig

        gen_cfg = OmniVoiceGenerationConfig(
            num_step=max(4, int(num_step)),
            guidance_scale=float(guidance_scale),
            t_shift=float(t_shift),
            denoise=True,
            postprocess_output=False,  # Use fast non-destructive NumPy edge trim instead of pydub
            audio_chunk_threshold=22.0,
            audio_chunk_duration=14.0,
        )

        sr = int(getattr(tts, "sampling_rate", 24000))
        max_batch = max(1, int(getattr(settings, "VOICETUT_BATCH_CHUNKS", 4)))
        raw_outputs: list = []

        with XTTSProvider._gpu_lock:
            if XTTSProvider._shared_device == "cpu" and hasattr(tts, "model"):
                try:
                    tts.model.float()
                except Exception:
                    pass

            with torch.inference_mode():
                for start in range(0, len(norm_chunks), max_batch):
                    sub = norm_chunks[start : start + max_batch]
                    try:
                        audios = tts.model.generate(
                            text=sub,
                            language=[lang] * len(sub),
                            voice_clone_prompt=[prompt] * len(sub) if prompt is not None else None,
                            speed=[float(speed)] * len(sub),
                            generation_config=gen_cfg,
                            normalize_text=False,
                        )
                        raw_outputs.extend(audios)
                    except RuntimeError as rt_err:
                        if len(sub) > 1 and "out of memory" in str(rt_err).lower():
                            logger.warning("Batched TTS hit CUDA memory pressure; retrying chunk-by-chunk.")
                            if torch.cuda.is_available():
                                torch.cuda.empty_cache()
                            for item in sub:
                                single = tts.model.generate(
                                    text=item,
                                    language=lang,
                                    voice_clone_prompt=prompt,
                                    speed=float(speed),
                                    generation_config=gen_cfg,
                                    normalize_text=False,
                                )
                                raw_outputs.extend(single)
                        else:
                            raise
        return [_fast_postprocess_chunk(aud, sample_rate=sr) for aud in raw_outputs]

    # ── BaseTTSProvider Interface ─────────────────────────────────────────────

    async def synthesize(
        self,
        text: str,
        speaker: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        speed: Optional[float] = None,
        language: Optional[str] = None,
    ) -> bytes:
        """Synthesize Egyptian speech strictly via VoiceTut-TTS and return WAV bytes."""
        if not text or not text.strip():
            return b""

        if self._should_use_microservice():
            try:
                from app.providers.tts.voicetut_microservice import VoiceTutMicroserviceProvider
                clean_text = clean_llm_output_for_speech(text, for_voicetut=True) or text.strip()
                svc = VoiceTutMicroserviceProvider()
                return await svc.synthesize(
                    text=clean_text,
                    speaker=speaker or self._speaker,
                    ref_audio=ref_audio or self._reference_wav,
                    ref_text=ref_text,
                    num_step=num_step,
                    guidance_scale=guidance_scale,
                    speed=speed,
                    language=language or self._language,
                )
            except Exception as svc_err:
                logger.warning(f"VoiceTut microservice unavailable ({svc_err}); running in-process GPU.")
                XTTSProvider._microservice_up = False

        await self._ensure_in_process_loaded()

        if XTTSProvider._shared_tts is not None and not isinstance(XTTSProvider._shared_tts, str):
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self._get_executor(),
                self._synth_sync,
                text,
                speaker,
                ref_audio,
                ref_text,
                num_step,
                guidance_scale,
                speed,
                language,
            )

        logger.error("VoiceTut-TTS model is not loaded. Strict Zero Fallback enforced.")
        raise RuntimeError(
            "فشل استنساخ الصوت: موديل VoiceTut-TTS الأساسي غير متوفر حالياً ولا يوجد أي نموذج بديل (Strict Zero Fallback)."
        )

    async def synthesize_stream(
        self,
        text: str,
        speaker: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        speed: Optional[float] = None,
        language: Optional[str] = None,
    ) -> AsyncIterator[bytes]:
        """
        True progressive sentence-level streaming:
        1. Emits valid 44-byte RIFF/WAV streaming header immediately.
        2. Synthesizes sentence 0 alone first for minimum Time-To-First-Audio (~1s).
        3. Micro-batches remaining sentences on GPU while chunk 0 is streaming/playing.
        """
        if not text or not text.strip():
            return

        cleaned_text = clean_llm_output_for_speech(text, for_voicetut=True) or text.strip()
        if not cleaned_text:
            return

        await self._ensure_in_process_loaded()
        tts = XTTSProvider._shared_tts
        if tts is None or isinstance(tts, str):
            raise RuntimeError("VoiceTut-TTS model is not loaded (Strict Zero Fallback).")

        t0 = time.perf_counter()
        loop = asyncio.get_running_loop()
        executor = self._get_executor()

        # Parallel prep: reference lookup + chunk normalization (comma-split long opening clauses for fast TTFA)
        first_chunk_limit = 75 if len(cleaned_text) > 85 else None
        ref_fut = loop.run_in_executor(
            executor, self._resolve_ref_sync, ref_audio, ref_text, speaker, ref_audio is None
        )
        chunks_fut = loop.run_in_executor(
            executor, self._prepare_chunks_parallel, tts, text, 170, first_chunk_limit
        )
        (resolved_wav, resolved_txt), norm_chunks = await asyncio.gather(ref_fut, chunks_fut)

        if not norm_chunks:
            return

        if not resolved_wav or not os.path.exists(resolved_wav):
            raise RuntimeError("No valid reference voice sample or VoiceTut speaker found.")

        steps, cfg, spd, t_shift, lang = self._resolve_gen_params(
            num_step, guidance_scale, speed, language
        )
        sr = int(getattr(tts, "sampling_rate", 24000))

        cache_key = self._make_wav_cache_key(
            resolved_wav, resolved_txt, cleaned_text, lang, steps, cfg, spd, t_shift
        )
        cached_wav = self._get_cached_wav(cache_key)
        if cached_wav is not None:
            cached_pcm = self._extract_wav_pcm(cached_wav)
            if cached_pcm:
                yield _build_streaming_wav_header(sample_rate=sr)
                hit_ms = round((time.perf_counter() - t0) * 1000, 1)
                self.last_metrics = {
                    "ttfa_ms": hit_ms,
                    "total_ms": hit_ms,
                    "chunks": len(norm_chunks),
                    "num_steps": steps,
                    "cached": True,
                }
                yield cached_pcm
                return

        prompt = await loop.run_in_executor(executor, self._get_or_create_prompt, tts, resolved_wav, resolved_txt)

        # Emit streaming WAV header immediately
        yield _build_streaming_wav_header(sample_rate=sr)

        pcm_queue: asyncio.Queue[Optional[tuple[bytes, Optional[Exception]]]] = asyncio.Queue()

        def _stream_producer():
            try:
                gap_bytes = b"\x00" * (int(sr * 0.07) * 2)  # 70ms breath gap (PCM16)
                # Chunk 0 standalone for minimum TTFA
                first_audios = self._generate_chunks_gpu(
                    tts, [norm_chunks[0]], prompt, lang, steps, cfg, spd, t_shift
                )
                first_pcm = _float_to_pcm16_bytes(first_audios[0])
                loop.call_soon_threadsafe(pcm_queue.put_nowait, (first_pcm, None))

                if len(norm_chunks) > 1:
                    rest_audios = self._generate_chunks_gpu(
                        tts, norm_chunks[1:], prompt, lang, steps, cfg, spd, t_shift
                    )
                    for aud in rest_audios:
                        chunk_pcm = gap_bytes + _float_to_pcm16_bytes(aud)
                        loop.call_soon_threadsafe(pcm_queue.put_nowait, (chunk_pcm, None))
            except Exception as exc:
                loop.call_soon_threadsafe(pcm_queue.put_nowait, (b"", exc))
            finally:
                loop.call_soon_threadsafe(pcm_queue.put_nowait, None)

        loop.run_in_executor(executor, _stream_producer)

        first_emitted = False
        pcm_parts: list[bytes] = []
        while True:
            item = await pcm_queue.get()
            if item is None:
                break
            chunk_bytes, err = item
            if err is not None:
                raise err
            if chunk_bytes:
                pcm_parts.append(chunk_bytes)
                if not first_emitted:
                    self.last_metrics = {
                        "ttfa_ms": round((time.perf_counter() - t0) * 1000, 1),
                        "chunks": len(norm_chunks),
                        "num_steps": steps,
                        "cached": False,
                    }
                    first_emitted = True
                yield chunk_bytes

        self.last_metrics["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        if pcm_parts:
            self._store_cached_wav(
                cache_key,
                self._wrap_pcm_as_wav(b"".join(pcm_parts), sample_rate=sr),
            )

    # ── Voice Cloning Helpers ─────────────────────────────────────────────────

    async def clone_voice(
        self,
        reference_wav: str,
        text: str,
        language: str = "arz",
        ref_text: Optional[str] = None,
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        speed: Optional[float] = None,
    ) -> bytes:
        return await self.synthesize(
            text=text,
            ref_audio=reference_wav,
            ref_text=ref_text,
            num_step=num_step,
            guidance_scale=guidance_scale,
            speed=speed,
            language=language,
        )

    def set_reference_voice(self, wav_path: str) -> None:
        p = Path(wav_path)
        if not p.exists():
            raise FileNotFoundError(f"Reference voice audio not found: {wav_path}")
        self._reference_wav = str(p.resolve())
        logger.info(f"VoiceTut reference voice updated -> {self._reference_wav}")

    # ── Internal Synchronous Execution ────────────────────────────────────────

    def _synth_sync(
        self,
        text: str,
        speaker: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        speed: Optional[float] = None,
        language: Optional[str] = None,
    ) -> bytes:
        t0 = time.perf_counter()
        try:
            tts = XTTSProvider._shared_tts
            if tts is None or isinstance(tts, str):
                raise RuntimeError("In-process VoiceTut-TTS engine is not instantiated.")

            cleaned_text = clean_llm_output_for_speech(text, for_voicetut=True) or text.strip()
            if not cleaned_text:
                return b""

            steps, cfg, spd, t_shift, lang = self._resolve_gen_params(
                num_step, guidance_scale, speed, language
            )
            sr = int(getattr(tts, "sampling_rate", 24000))

            executor = self._get_executor()
            allow_spk = ref_audio is None
            fut_ref = executor.submit(self._resolve_ref_sync, ref_audio, ref_text, speaker, allow_spk)
            fut_chunks = executor.submit(self._prepare_chunks_parallel, tts, text, 190)

            target_ref_audio, actual_ref_text = fut_ref.result()
            norm_chunks = fut_chunks.result()

            if not norm_chunks:
                return b""

            if not target_ref_audio or not os.path.exists(target_ref_audio):
                raise RuntimeError(
                    "لا توجد عينة صوت مرجعية صالحة للاستنساخ (Strict Zero Fallback)."
                )

            cache_key = self._make_wav_cache_key(
                target_ref_audio, actual_ref_text, cleaned_text, lang, steps, cfg, spd, t_shift
            )
            cached_wav = self._get_cached_wav(cache_key)
            if cached_wav is not None:
                total_ms = (time.perf_counter() - t0) * 1000
                pcm_len = len(self._extract_wav_pcm(cached_wav))
                dur_s = pcm_len / (2 * max(1, sr))
                self.last_metrics = {
                    "total_ms": round(total_ms, 1),
                    "gpu_ms": 0.0,
                    "chunks": len(norm_chunks),
                    "audio_s": round(dur_s, 2),
                    "rtf": round((total_ms / 1000.0) / max(0.05, dur_s), 3),
                    "num_steps": steps,
                    "speed": spd,
                    "guidance_scale": cfg,
                    "cached": True,
                }
                return cached_wav

            prompt = self._get_or_create_prompt(tts, target_ref_audio, actual_ref_text)

            t_gpu = time.perf_counter()
            audios = self._generate_chunks_gpu(
                tts=tts,
                norm_chunks=norm_chunks,
                prompt=prompt,
                lang=lang,
                num_step=steps,
                guidance_scale=cfg,
                speed=spd,
                t_shift=t_shift,
            )
            gpu_ms = (time.perf_counter() - t_gpu) * 1000

            if len(audios) == 1:
                wav_samples = audios[0]
            else:
                import numpy as np
                from omnivoice.utils.audio import cross_fade_chunks
                wav_samples = cross_fade_chunks(
                    [np.asarray(a, dtype=np.float32)[np.newaxis, :] for a in audios],
                    sample_rate=sr,
                    silence_duration=0.14,
                ).squeeze(0)

            wav_bytes = _array_to_wav(wav_samples, sample_rate=sr)
            self._store_cached_wav(cache_key, wav_bytes)

            total_ms = (time.perf_counter() - t0) * 1000
            dur_s = len(wav_samples) / max(1, sr)
            self.last_metrics = {
                "total_ms": round(total_ms, 1),
                "gpu_ms": round(gpu_ms, 1),
                "chunks": len(norm_chunks),
                "audio_s": round(dur_s, 2),
                "rtf": round((total_ms / 1000.0) / max(0.05, dur_s), 2),
                "num_steps": steps,
                "speed": spd,
                "guidance_scale": cfg,
                "cached": False,
            }
            logger.info(
                f"VoiceTut clone done in {total_ms:.0f}ms (gpu={gpu_ms:.0f}ms, "
                f"audio={dur_s:.2f}s, rtf={self.last_metrics['rtf']}x, chunks={len(norm_chunks)}, steps={steps})"
            )
            return wav_bytes
        except Exception as e:
            logger.error(f"VoiceTut synthesis error: {e}", exc_info=True)
            raise RuntimeError(f"VoiceTut synthesis execution failed: {e}") from e
