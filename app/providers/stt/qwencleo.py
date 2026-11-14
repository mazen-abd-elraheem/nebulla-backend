"""
QwenCleo ASR Provider — Egyptian Arabic Speech-to-Text
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Fine-tune of Qwen3-ASR-1.7B specialised for Egyptian Arabic.
WER ≈ 19.9 % on a 3,699-sentence Egyptian test set (doc §6.1).
License: Apache-2.0.

Optimised with:
  • Multithreading (ThreadPoolExecutor) for concurrent chunk processing
  • Overlapping chunk-based ASR pipeline for low latency
  • Energy-based silence trimming to eliminate empty recording lag ("الريك الفاضي")
"""

import asyncio
import concurrent.futures
import gc
import io
import json
import os
import struct
import threading
from pathlib import Path
from typing import List, Optional, Tuple

# Ensure Transformers never wastes pagefile/RAM importing TensorFlow
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ.setdefault("USE_TORCH", "1")

import numpy as np

# Resolve Python 3.12 torchvision circular import bug before any transformers sub-imports
try:
    import torchvision  # noqa: F401
except Exception:
    pass

from app.providers.tts.base import BaseSTTProvider
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

# Dedicated multithreading worker pool for ASR chunk processing
_stt_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=min(4, os.cpu_count() or 2),
    thread_name_prefix="qwencleo_stt",
)

# Mutex to ensure PyTorch model generation never collides or exhausts VRAM on concurrent requests
_model_inference_lock = threading.Lock()


def _trim_silence_array(
    audio: np.ndarray,
    sr: int,
    threshold_factor: float = 0.025,
    pad_ms: int = 80,
) -> Tuple[np.ndarray, bool]:
    """
    Trim leading and trailing silence from an audio array.
    Eliminates dead silence lag ("الريك فاضي") while preserving speech onsets.
    Returns (trimmed_audio, is_pure_silence).
    """
    if len(audio) == 0:
        return audio, True

    mono = audio.mean(axis=1) if audio.ndim > 1 else audio
    if len(mono) > 0:
        mono = mono - float(np.mean(mono))

    frame_size = max(1, int(sr * 0.02))  # 20ms frames
    num_frames = len(mono) // frame_size
    if num_frames == 0:
        return audio, False

    frames = mono[: num_frames * frame_size].reshape(num_frames, frame_size)
    rms = np.sqrt(np.mean(frames ** 2, axis=1))
    peak_rms = float(np.max(rms))

    # If peak volume is below audible speech threshold (empty recording)
    if peak_rms < 1e-4:
        return np.array([], dtype=audio.dtype), True

    threshold = max(0.002, peak_rms * threshold_factor)
    active = np.where(rms > threshold)[0]
    if len(active) == 0:
        return np.array([], dtype=audio.dtype), True

    pad_samples = int(sr * (pad_ms / 1000.0))
    start_idx = max(0, active[0] * frame_size - pad_samples)
    end_idx = min(len(audio), (active[-1] + 1) * frame_size + pad_samples)

    return audio[start_idx:end_idx], False


def _split_into_chunks(
    audio: np.ndarray,
    sr: int,
    chunk_s: float = 10.0,
    stride_s: float = 1.0,
) -> List[np.ndarray]:
    """
    Split audio into overlapping chunks for parallel multithreaded processing.
    """
    total_samples = len(audio)
    chunk_samples = int(chunk_s * sr)
    stride_samples = int(stride_s * sr)
    step_samples = chunk_samples - stride_samples

    if total_samples <= chunk_samples:
        return [audio]

    chunks = []
    idx = 0
    while idx < total_samples:
        end = min(total_samples, idx + chunk_samples)
        chunk = audio[idx:end]
        if len(chunk) > int(sr * 0.5):  # keep chunks > 0.5s
            chunks.append(chunk)
        idx += step_samples

    return chunks


def _merge_transcripts(transcripts: List[str]) -> str:
    """Merge transcribed text chunks, deduplicating overlapping boundary tokens."""
    if not transcripts:
        return ""
    clean = [t.strip() for t in transcripts if t and t.strip()]
    if not clean:
        return ""
    if len(clean) == 1:
        return clean[0]

    merged_words = clean[0].split()
    for nxt in clean[1:]:
        nxt_words = nxt.split()
        if not nxt_words:
            continue
        # Check overlap of 1-3 words at boundary
        matched = 0
        for k in range(min(4, len(merged_words), len(nxt_words)), 0, -1):
            if merged_words[-k:] == nxt_words[:k]:
                matched = k
                break
        merged_words.extend(nxt_words[matched:])

    return " ".join(merged_words)


_SAFETENSORS_DTYPE_NAMES = {
    "BF16": "bfloat16",
    "F16": "float16",
    "F32": "float32",
    "I64": "int64",
    "I32": "int32",
    "I16": "int16",
    "I8": "int8",
    "U8": "uint8",
    "BOOL": "bool",
}


def _resolve_param_device(key: str, device_map: dict, default_dev: str = "cpu") -> str:
    """Resolve target PyTorch device for a parameter key from an accelerate device_map."""
    if "" in device_map and len(device_map) == 1:
        val = device_map[""]
        return f"cuda:{val}" if isinstance(val, int) else str(val)
    best_prefix = ""
    best_dev = default_dev
    for prefix, dev in device_map.items():
        if key == prefix or key.startswith(prefix + "."):
            if len(prefix) > len(best_prefix):
                best_prefix = prefix
                best_dev = f"cuda:{dev}" if isinstance(dev, int) else str(dev)
    return best_dev


def _release_torch_memory() -> None:
    """Release partial CUDA/CPU allocations after a failed model load attempt."""
    gc.collect()
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass


def _load_qwencleo_streaming(model_path: str, torch_dtype, device_idx: int, gpu_budget_mib: int):
    """
    Zero-mmap streaming safetensors loader for Qwen3ASRModel.
    Avoids Windows os error 1455 (pagefile commit ceiling from safetensors mmap)
    by reading tensors sequentially via standard file I/O into GPU/CPU devices.
    """
    import torch
    from accelerate import dispatch_model, infer_auto_device_map, init_empty_weights
    from accelerate.utils import set_module_tensor_to_device
    from huggingface_hub import hf_hub_download
    from transformers import AutoProcessor, GenerationConfig
    from qwen_asr import Qwen3ASRModel
    from qwen_asr.core.transformers_backend import (
        Qwen3ASRConfig,
        Qwen3ASRForConditionalGeneration,
    )

    dtype_map = {k: getattr(torch, v) for k, v in _SAFETENSORS_DTYPE_NAMES.items()}

    local_dir = Path(model_path)
    if local_dir.is_dir() and (local_dir / "model.safetensors").exists():
        st_path = str(local_dir / "model.safetensors")
    else:
        try:
            st_path = hf_hub_download(model_path, "model.safetensors", local_files_only=True)
        except Exception:
            st_path = hf_hub_download(model_path, "model.safetensors", local_files_only=False)

    with open(st_path, "rb") as f:
        header_len = struct.unpack("<Q", f.read(8))[0]
        header = json.loads(f.read(header_len).decode("utf-8"))
        data_start = 8 + header_len

    try:
        cfg = Qwen3ASRConfig.from_pretrained(model_path, local_files_only=True)
    except Exception:
        cfg = Qwen3ASRConfig.from_pretrained(model_path)

    with init_empty_weights():
        model = Qwen3ASRForConditionalGeneration(cfg)

    if device_idx >= 0 and gpu_budget_mib >= 4400:
        device_map = {"": device_idx}
    elif device_idx >= 0 and gpu_budget_mib >= 1024:
        device_map = infer_auto_device_map(
            model,
            max_memory={device_idx: f"{gpu_budget_mib}MiB", "cpu": "6GiB"},
            no_split_module_classes=["Qwen3ASRThinkerTextDecoderLayer", "Qwen3ASRAudioEncoderLayer"],
            dtype=torch_dtype,
        )
        # Keep tied embed_tokens and lm_head on the same device
        if "thinker.model.embed_tokens" in device_map and "thinker.lm_head" in device_map:
            embed_dev = device_map["thinker.model.embed_tokens"]
            if device_map["thinker.lm_head"] != embed_dev:
                device_map["thinker.lm_head"] = embed_dev
    else:
        device_map = {"": "cpu"}

    logger.info(
        f"Streaming QwenCleo-ASR weights (zero-mmap, GPU budget={gpu_budget_mib} MiB)…"
    )

    with open(st_path, "rb") as f:
        for key, meta in header.items():
            if key == "__metadata__":
                continue
            src_dtype = dtype_map[meta["dtype"]]
            shape = tuple(meta["shape"])
            start, end = meta["data_offsets"]
            byte_len = end - start
            f.seek(data_start + start)
            raw = bytearray(byte_len)
            view = memoryview(raw)
            offset = 0
            while offset < byte_len:
                n = f.readinto(view[offset:])
                if not n:
                    break
                offset += n
            tensor = torch.frombuffer(raw, dtype=src_dtype).reshape(shape)
            target_dev = _resolve_param_device(key, device_map, "cpu")
            target_dtype = (
                torch_dtype
                if (torch_dtype is not None and tensor.is_floating_point())
                else tensor.dtype
            )
            tensor_dev = (
                tensor.to(device=target_dev, dtype=target_dtype, copy=True)
                if tensor.dtype != target_dtype
                else tensor.to(device=target_dev, copy=True)
            )
            set_module_tensor_to_device(model, key, target_dev, value=tensor_dev)
            del raw, view, tensor, tensor_dev

    for buf_name, buf in list(model.named_buffers()):
        target_dev = _resolve_param_device(buf_name, device_map, "cpu")
        if str(buf.device) != target_dev:
            set_module_tensor_to_device(model, buf_name, target_dev, value=buf.to(target_dev))

    model.tie_weights()
    model.eval()
    try:
        model.generation_config = GenerationConfig.from_pretrained(model_path, local_files_only=True)
    except Exception:
        try:
            model.generation_config = GenerationConfig.from_pretrained(model_path)
        except Exception:
            pass

    if len(device_map) > 1 or "" not in device_map:
        dispatch_model(
            model,
            device_map=device_map,
            skip_keys=getattr(model, "_skip_keys_device_placement", None),
        )
    elif device_map.get("") != "cpu":
        model.to(f"cuda:{device_map['']}" if isinstance(device_map[""], int) else device_map[""])

    gc.collect()
    try:
        processor = AutoProcessor.from_pretrained(model_path, fix_mistral_regex=True, local_files_only=True)
    except Exception:
        processor = AutoProcessor.from_pretrained(model_path, fix_mistral_regex=True)

    return Qwen3ASRModel(
        backend="transformers",
        model=model,
        processor=processor,
        max_new_tokens=256,
    )


class QwenCleoProvider(BaseSTTProvider):
    """
    Egyptian Arabic ASR via QwenCleo-ASR (Qwen3-ASR-1.7B fine-tune).
    Accelerated with chunk processing and early VAD silence gating.
    """

    _shared_pipeline = None
    _shared_lock = asyncio.Lock()
    _shared_error: str | None = None

    @classmethod
    def is_ready(cls) -> bool:
        """Return True if QwenCleo model is warm and loaded in memory."""
        return cls._shared_pipeline is not None

    async def _ensure_loaded(self):
        if QwenCleoProvider._shared_pipeline is not None:
            return
        async with QwenCleoProvider._shared_lock:
            if QwenCleoProvider._shared_pipeline is None:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(_stt_executor, self._load)

    def _load(self):
        try:
            try:
                import torchvision  # noqa: F401  # type: ignore
            except Exception:
                pass

            import torch

            # 1. Ensure Qwen3-ASR architecture is registered with Transformers
            try:
                import qwen_asr  # noqa: F401  # type: ignore
                from qwen_asr.core.transformers_backend import (  # type: ignore
                    Qwen3ASRConfig,
                    Qwen3ASRForConditionalGeneration,
                    Qwen3ASRProcessor,
                )
                from transformers import (
                    AutoConfig,
                    AutoModel,
                    AutoModelForSpeechSeq2Seq,
                    AutoProcessor,
                )

                AutoConfig.register("qwen3_asr", Qwen3ASRConfig)
                AutoModel.register(Qwen3ASRConfig, Qwen3ASRForConditionalGeneration)
                AutoModelForSpeechSeq2Seq.register(Qwen3ASRConfig, Qwen3ASRForConditionalGeneration)
                AutoProcessor.register(Qwen3ASRConfig, Qwen3ASRProcessor)
            except Exception as reg_err:
                logger.debug(f"Qwen3ASR auto-registration note: {reg_err}")

            model_path = settings.QWENCLEO_MODEL_PATH
            # If local relative path doesn't exist, use Hugging Face repo
            if not Path(model_path).exists():
                logger.info(f"Local QwenCleo model not found at '{model_path}'. Using 'mohammedaly22/QwenCleo-ASR'...")
                model_path = "mohammedaly22/QwenCleo-ASR"

            device_idx = -1
            gpu_budget_mib = 0
            if settings.QWENCLEO_DEVICE == "cuda":
                if torch.cuda.is_available():
                    device_idx = 0
                    try:
                        free_bytes, _total_bytes = torch.cuda.mem_get_info(device_idx)
                        free_mib = int(free_bytes // (1024 * 1024))
                        # Reserve 800 MiB for inference activations, KV cache & WDDM overhead
                        gpu_budget_mib = max(0, free_mib - 800)
                        logger.info(
                            f"CUDA GPU0 free VRAM: {free_mib} MiB -> QwenCleo GPU budget: {gpu_budget_mib} MiB"
                        )
                    except Exception:
                        gpu_budget_mib = 2400
                else:
                    logger.warning("CUDA requested for QwenCleo but not available. Using CPU.")

            device_str = f"cuda:{device_idx}" if device_idx >= 0 else "cpu"
            torch_dtype = (
                torch.bfloat16
                if (device_idx >= 0 and torch.cuda.is_bf16_supported())
                else (torch.float16 if device_idx >= 0 else torch.bfloat16)
            )

            logger.info(f"Loading QwenCleo-ASR from {model_path} ({device_str}, {torch_dtype})…")

            # Temporarily bypass aggressive CUDA caching_allocator_warmup on constrained Windows GPUs
            import transformers.modeling_utils as _tf_mod_utils
            _orig_warmup = getattr(_tf_mod_utils, "caching_allocator_warmup", None)
            if _orig_warmup is not None:
                _tf_mod_utils.caching_allocator_warmup = lambda *args, **kwargs: None

            loaded = False
            try:
                from qwen_asr import Qwen3ASRModel  # type: ignore

                load_kwargs = {
                    "dtype": torch_dtype,
                    "low_cpu_mem_usage": True,
                    "max_new_tokens": 256,
                }
                if device_idx >= 0 and gpu_budget_mib >= 4400:
                    load_kwargs["device_map"] = device_str
                elif device_idx >= 0 and gpu_budget_mib >= 1024:
                    offload_dir = Path("models/offload_cache/qwencleo")
                    offload_dir.mkdir(parents=True, exist_ok=True)
                    load_kwargs["device_map"] = "auto"
                    load_kwargs["max_memory"] = {
                        device_idx: f"{gpu_budget_mib}MiB",
                        "cpu": "6GiB",
                    }
                    load_kwargs["offload_folder"] = str(offload_dir)
                else:
                    load_kwargs["device_map"] = "cpu"

                QwenCleoProvider._shared_pipeline = Qwen3ASRModel.from_pretrained(
                    model_path,
                    **load_kwargs,
                )
                loaded = True
                logger.info("QwenCleo loaded successfully via Qwen3ASRModel [OK]")
            except Exception as model_err:
                logger.warning(
                    f"Direct Qwen3ASRModel loading note ({model_err}). "
                    "Cleaning up memory and retrying with zero-mmap streaming loader…"
                )
                _release_torch_memory()
            finally:
                if _orig_warmup is not None:
                    _tf_mod_utils.caching_allocator_warmup = _orig_warmup

            if not loaded:
                QwenCleoProvider._shared_pipeline = _load_qwencleo_streaming(
                    model_path=model_path,
                    torch_dtype=torch_dtype,
                    device_idx=device_idx,
                    gpu_budget_mib=gpu_budget_mib,
                )
                logger.info("QwenCleo loaded successfully via zero-mmap streaming loader [OK]")

            QwenCleoProvider._shared_error = None
            logger.info("QwenCleo-ASR ready (multithreaded chunks enabled) ✓")
        except Exception as e:
            _release_torch_memory()
            err_msg = f"Failed to load QwenCleo-ASR: {e}"
            logger.error(err_msg, exc_info=True)
            QwenCleoProvider._shared_error = err_msg
            raise RuntimeError(err_msg) from e

    async def transcribe(self, audio_bytes: bytes) -> str:
        await self._ensure_loaded()
        if QwenCleoProvider._shared_pipeline is None:
            raise RuntimeError(
                f"QwenCleo-ASR is unavailable. Error: {QwenCleoProvider._shared_error}"
            )

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_stt_executor, self._run, audio_bytes)

    def _run_single_chunk(self, chunk: np.ndarray, sample_rate: int) -> str:
        """Transcribe an individual audio chunk through the model under inference lock."""
        pipeline = QwenCleoProvider._shared_pipeline
        if pipeline is None:
            return ""

        try:
            with _model_inference_lock:
                if hasattr(pipeline, "transcribe"):
                    res = pipeline.transcribe(
                        audio=(chunk, sample_rate),
                        language="Arabic",
                    )
                    return res[0].text.strip() if res else ""
            return ""
        except Exception as exc:
            logger.warning(f"Error transcribing chunk: {exc}", exc_info=True)
            return ""

    def _run(self, audio_bytes: bytes) -> str:
        import io
        import soundfile as sf  # type: ignore[import]

        try:
            audio_array, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32")
            if audio_array.ndim > 1:
                audio_array = audio_array.mean(axis=1)  # stereo → mono
            audio_array = np.clip(np.asarray(audio_array, dtype=np.float32), -1.0, 1.0)

            # 1. Early silence trimming: remove long empty pauses at start/end
            trimmed_audio, is_silent = _trim_silence_array(audio_array, sample_rate)
            if is_silent or len(trimmed_audio) < int(sample_rate * 0.5):
                logger.debug("Audio recording is silent or empty. Returning empty transcript.")
                return ""

            dur_s = len(trimmed_audio) / sample_rate

            # 2. Standard audio utterances (<= 30s): transcribe in one pass for full context
            if dur_s <= 30.0:
                return self._run_single_chunk(trimmed_audio, sample_rate)

            # 3. Longer audio (> 30s): chunk sequentially without pool recursion/deadlock
            chunks = _split_into_chunks(trimmed_audio, sample_rate, chunk_s=15.0, stride_s=1.5)
            if len(chunks) == 1:
                return self._run_single_chunk(chunks[0], sample_rate)

            transcripts = []
            for chunk in chunks:
                chunk_text = self._run_single_chunk(chunk, sample_rate)
                if chunk_text:
                    transcripts.append(chunk_text)
            return _merge_transcripts(transcripts)

        except Exception as e:
            logger.error(f"QwenCleo transcription execution error: {e}", exc_info=True)
            raise RuntimeError(f"QwenCleo transcription error: {e}") from e
