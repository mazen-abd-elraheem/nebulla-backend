"""
UniFace Vision Service — face detection, gaze estimation, and (optionally) recognition.

Workflow (doc §6.2):
  1. Phone sends small JPEG (320×240) at 5-10 fps
  2. UniFace detects face using SCRFD (fast & lightweight)
  3. Backend computes gaze direction relative to image centre
  4. Smoothed gaze sent to phone (eye tracking)
  5. If neck is attached, servo command sent to ESP32

Performance note (doc §6.2):
  If GPU is busy with STT/TTS, run UniFace on CPU.
"""

import asyncio
import io
import time
from dataclasses import dataclass
from typing import Optional, Tuple

from app.core.config import settings
from app.core.logger import get_logger
from app.websocket.manager import manager

logger = get_logger(__name__)


@dataclass
class FaceResult:
    detected: bool
    x: float = 0.0    # -1.0 (left) to +1.0 (right)
    y: float = 0.0    # -1.0 (bottom) to +1.0 (top)
    confidence: float = 0.0
    face_id: Optional[str] = None   # if recognition is enabled


class FaceService:
    """
    Wraps UniFace for face detection and gaze estimation.
    Lazy-loads the ONNX model to avoid startup delay.
    """

    def __init__(self):
        self._model = None
        self._load_lock = asyncio.Lock()

        # Smoothing filter state (EMA — exponential moving average)
        self._ema_x: float = 0.0
        self._ema_y: float = 0.0
        self._ema_alpha: float = 0.3   # smaller = smoother, more lag

    async def _ensure_model(self):
        if self._model is not None:
            return
        async with self._load_lock:
            if self._model is None:
                await asyncio.get_event_loop().run_in_executor(
                    None, self._load_model
                )

    def _load_model(self):
        """Load UniFace model (ONNX Runtime). Runs in thread pool."""
        try:
            import uniface  # type: ignore[import]
            self._model = uniface.FaceDetector(
                model=settings.UNIFACE_MODEL,
                device=settings.UNIFACE_DEVICE,
            )
            logger.info(f"UniFace loaded: {settings.UNIFACE_MODEL} on {settings.UNIFACE_DEVICE}")
        except ImportError:
            logger.warning("UniFace not installed — vision disabled. Install with: pip install uniface")
            self._model = "disabled"

    async def process_frame(self, jpeg_bytes: bytes) -> Optional[FaceResult]:
        """
        Detect face in JPEG frame, compute gaze, send to phone and ESP32.
        Returns the FaceResult or None if no face detected.
        """
        await self._ensure_model()

        if self._model == "disabled":
            return None

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, self._detect, jpeg_bytes)

        if result.detected:
            # Smooth the gaze signal (doc §6.2 smoothing to prevent eye tremor)
            self._ema_x = self._ema_alpha * result.x + (1 - self._ema_alpha) * self._ema_x
            self._ema_y = self._ema_alpha * result.y + (1 - self._ema_alpha) * self._ema_y

            gaze_msg = {
                "t": "gaze",
                "x": round(self._ema_x, 3),
                "y": round(self._ema_y, 3),
            }
            await manager.send_to_phone(gaze_msg)

            # Wake-up signal when face appears
            await manager.send_to_phone({"t": "eyes", "mood": "attentive"})

        return result if result.detected else None

    def _detect(self, jpeg_bytes: bytes) -> FaceResult:
        """Synchronous detection — runs in thread pool."""
        try:
            import numpy as np
            from PIL import Image  # type: ignore[import]

            img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
            img_array = np.array(img)

            faces = self._model.detect(img_array)
            if not faces:
                return FaceResult(detected=False)

            # Take the largest face
            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))

            # Normalise face centre to [-1, 1] relative to image centre
            h, w = img_array.shape[:2]
            cx = (face.bbox[0] + face.bbox[2]) / 2
            cy = (face.bbox[1] + face.bbox[3]) / 2

            norm_x = (cx / w - 0.5) * 2   # -1 left, +1 right
            norm_y = -((cy / h - 0.5) * 2)  # -1 bottom, +1 top

            return FaceResult(
                detected=True,
                x=float(norm_x),
                y=float(norm_y),
                confidence=float(face.score),
            )
        except Exception as e:
            logger.error(f"Face detection error: {e}")
            return FaceResult(detected=False)
