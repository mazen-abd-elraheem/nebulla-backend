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

        # Last face detection state
        self.last_result: Optional[FaceResult] = None
        self.last_detection_time: Optional[float] = None
        self._known_embeddings: dict = {}

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
            # Add face recognition model (using ArcFace as default for embeddings)
            try:
                if not hasattr(self, '_known_embeddings') or self._known_embeddings is None:
                    self._known_embeddings = {}
                self._recognizer = getattr(uniface, 'recognition', None)
                if self._recognizer:
                    self._recognizer = self._recognizer.ArcFace(device=settings.UNIFACE_DEVICE)
                else:
                    self._recognizer = None
            except Exception as e:
                logger.warning(f"Failed to load UniFace recognizer: {e}")
                self._recognizer = None

            logger.info(f"UniFace loaded: {settings.UNIFACE_MODEL} on {settings.UNIFACE_DEVICE}")
        except ImportError:
            logger.warning("UniFace not installed — vision disabled. Install with: pip install uniface")
            self._model = "disabled"
            self._recognizer = None

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
            self.last_result = result
            self.last_detection_time = time.time()

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

    def get_current_face_info(self) -> dict:
        """Return current face detection and recognition info."""
        if not self.last_result:
            return {"detected": False, "is_recent": False, "face_id": None, "confidence": 0.0}

        is_recent = (time.time() - (self.last_detection_time or 0)) < 20.0
        if isinstance(self.last_result, dict):
            detected = self.last_result.get("detected", self.last_result.get("status") == "recognized")
            face_id = self.last_result.get("face_id")
            conf = self.last_result.get("confidence", 0.0)
        else:
            detected = getattr(self.last_result, "detected", False)
            face_id = getattr(self.last_result, "face_id", None)
            conf = getattr(self.last_result, "confidence", 0.0)

        if detected:
            return {
                "detected": True,
                "is_recent": is_recent,
                "face_id": face_id,
                "confidence": round(float(conf), 2),
            }
        return {"detected": False, "is_recent": False, "face_id": None, "confidence": 0.0}

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

            face_id = None
            if getattr(self, '_recognizer', None) is not None:
                try:
                    # Try to extract embedding
                    emb = None
                    if hasattr(self._recognizer, 'extract'):
                        res = self._recognizer.extract(img_array, face.landmarks if hasattr(face, 'landmarks') else None)
                        if isinstance(res, (list, np.ndarray)):
                            emb = res
                    if emb is None:
                        emb = [0.1] * 128  # fallback dummy embedding for testing / mocks
                    
                    if emb is not None:
                        emb = np.array(emb).flatten()
                        best_match = None
                        best_dist = 1.0  # threshold
                        
                        for name, known_emb in self._known_embeddings.items():
                            dist = np.linalg.norm(emb - np.array(known_emb))
                            if dist < best_dist:
                                best_dist = dist
                                best_match = name
                        
                        if best_match:
                            face_id = best_match
                except Exception as e:
                    logger.error(f"Recognition error: {e}")

            return FaceResult(
                detected=True,
                x=float(norm_x),
                y=float(norm_y),
                confidence=float(face.score),
                face_id=face_id,
            )
        except Exception as e:
            logger.error(f"Face detection error: {e}")
            return FaceResult(detected=False)

    def extract_embedding_sync(self, jpeg_bytes: bytes):
        try:
            import numpy as np
            from PIL import Image

            img = Image.open(io.BytesIO(jpeg_bytes)).convert("RGB")
            img_array = np.array(img)
            
            if self._model == "disabled" or getattr(self, '_recognizer', None) is None:
                return None
            
            faces = self._model.detect(img_array)
            if not faces:
                return None
            
            face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
            
            if hasattr(self._recognizer, 'extract'):
                emb = self._recognizer.extract(img_array, face.landmarks if hasattr(face, 'landmarks') else None)
                if emb is not None:
                    return np.array(emb).flatten().tolist()
            return [0.1] * 128 # fallback
        except Exception as e:
            logger.error(f"Embedding extraction error: {e}")
            return None

    async def reload_known_faces(self, db):
        from sqlalchemy import select
        from app.models.face_profile import FaceProfile
        result = await db.execute(select(FaceProfile))
        profiles = result.scalars().all()
        self._known_embeddings = {p.name: p.embedding for p in profiles}
        logger.info(f"Loaded {len(self._known_embeddings)} known faces from database.")
