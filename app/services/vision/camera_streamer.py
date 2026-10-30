"""
CameraStreamer — Real-Time Laptop Webcam Streaming and MJPEG Server.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Manages OpenCV VideoCapture for the laptop camera with:
  - Exclusive access and safe thread management
  - Real-time UniFace face detection & HUD annotation overlay
  - Fast MJPEG streaming for HTML5 <img> tags
  - Auto-release timeout when all clients disconnect (turns off camera LED)
  - Snapshot capture for instant face registration and verification
"""

import asyncio
import sys
import threading
import time
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

import cv2
import numpy as np

from app.core.logger import get_logger

logger = get_logger(__name__)


class CameraStreamer:
    """Singleton manager for real-time laptop webcam streaming."""

    _instance: Optional["CameraStreamer"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, camera_index: int = 0):
        if getattr(self, "_initialized", False):
            return
        self.camera_index = camera_index
        self._cap: Optional[cv2.VideoCapture] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._active_clients = 0
        self._clients_lock = threading.Lock()

        # Shared frame state
        self._latest_jpeg: Optional[bytes] = None
        self._latest_raw_bgr: Optional[np.ndarray] = None
        self._frame_lock = threading.Lock()
        self._new_frame_event = threading.Event()

        # Performance metrics
        self.fps: float = 0.0
        self.total_frames: int = 0
        self.last_face_count: int = 0
        self._is_running: bool = False
        self._idle_timer: Optional[threading.Timer] = None

        self._initialized = True
        logger.info(f"CameraStreamer initialized for camera index {camera_index}.")

    @property
    def is_running(self) -> bool:
        return self._is_running

    @staticmethod
    def get_available_cameras(max_probe: int = 3) -> list:
        """Scan and return list of actually available camera devices on the system."""
        cams = []
        for idx in range(max_probe):
            cap = None
            try:
                if sys.platform == "win32":
                    cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                else:
                    cap = cv2.VideoCapture(idx)
                if cap is not None and cap.isOpened():
                    cams.append({
                        "index": idx,
                        "label": f"الكاميرا المدمجة ({idx} - Laptop Webcam)" if idx == 0 else f"كاميرا خارجية ({idx} - External)",
                    })
                    cap.release()
            except Exception:
                pass
        if not cams:
            cams.append({"index": 0, "label": "الكاميرا الافتراضية (0 - Default Webcam)"})
        return cams

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        """Open OpenCV video capture with optimal backend for host OS."""
        cap = None
        target_idx = self.camera_index

        if sys.platform == "win32":
            try:
                cap = cv2.VideoCapture(target_idx, cv2.CAP_DSHOW)
            except Exception:
                cap = None

        if cap is None or not cap.isOpened():
            cap = cv2.VideoCapture(target_idx)

        # Fallback to camera 0 if requested index is unavailable
        if (cap is None or not cap.isOpened()) and target_idx != 0:
            logger.warning(f"Camera index {target_idx} not accessible. Falling back to default camera 0...")
            target_idx = 0
            self.camera_index = 0
            if sys.platform == "win32":
                try:
                    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
                except Exception:
                    cap = None
            if cap is None or not cap.isOpened():
                cap = cv2.VideoCapture(0)

        if cap is None or not cap.isOpened():
            logger.error(f"Failed to open camera device at index {self.camera_index}.")
            return None

        # Set 720p HD resolution for high clarity at distance
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)

        actual_w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        logger.info(f"Opened laptop webcam (index {self.camera_index}): {int(actual_w)}x{int(actual_h)}.")
        return cap

    def start(self, camera_index: Optional[int] = None) -> bool:
        """Start the camera capture thread."""
        with self._lock:
            # If camera index changed, restart capture on new index
            if camera_index is not None and camera_index != self.camera_index:
                if self._is_running:
                    self._stop_event.set()
                    self._is_running = False
                    if self._cap:
                        try:
                            self._cap.release()
                        except Exception:
                            pass
                        self._cap = None
                    if self._thread and self._thread.is_alive():
                        self._thread.join(timeout=1.0)
                self.camera_index = camera_index

            # Cancel any pending auto-shutdown idle timer
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None

            if self._is_running and self._thread and self._thread.is_alive():
                return True

            self._stop_event.clear()
            self._cap = self._open_capture()
            if self._cap is None:
                return False

            self._is_running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True, name="WebcamCaptureThread")
            self._thread.start()
            logger.info("Webcam capture thread started.")
            return True

    def stop(self) -> None:
        """Stop capture and release camera device immediately."""
        with self._lock:
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None

            self._stop_event.set()
            self._is_running = False

            if self._cap:
                try:
                    self._cap.release()
                except Exception as e:
                    logger.debug(f"Error releasing camera: {e}")
                self._cap = None

            with self._frame_lock:
                self._latest_jpeg = None
                self._latest_raw_bgr = None

            logger.info("Webcam stopped and camera device released.")

    def _schedule_auto_shutdown(self, delay_sec: float = 6.0) -> None:
        """Schedule camera release if no clients reconnect within timeout."""
        with self._lock:
            if self._idle_timer:
                self._idle_timer.cancel()

            def _timed_stop():
                with self._clients_lock:
                    if self._active_clients <= 0:
                        logger.info(f"No active clients for {delay_sec}s. Auto-releasing camera.")
                        self.stop()

            self._idle_timer = threading.Timer(delay_sec, _timed_stop)
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _capture_loop(self) -> None:
        """Background thread continuously grabbing and annotating frames."""
        from app.websocket.handlers import _get_face_service

        face_service = _get_face_service()
        if face_service._analyzer is None:
            face_service._load_model()

        frame_count = 0
        fps_start = time.time()
        current_fps = 0.0

        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]

        while not self._stop_event.is_set():
            if not self._cap or not self._cap.isOpened():
                break

            ret, frame = self._cap.read()
            if not ret or frame is None:
                time.sleep(0.01)
                continue

            frame_count += 1
            now = time.time()
            elapsed = now - fps_start
            if elapsed >= 1.0:
                current_fps = frame_count / elapsed
                self.fps = round(current_fps, 1)
                frame_count = 0
                fps_start = now

            # Annotate frame with high-tech HUD (threshold 0.35 supports natural angles and movement)
            annotated_frame, detections = face_service.annotate_frame(
                frame_bgr=frame,
                threshold=0.35,
                fps=self.fps,
                draw_landmarks=True,
            )
            self.last_face_count = len(detections)

            # Compress to JPEG
            ok, jpeg = cv2.imencode(".jpg", annotated_frame, encode_param)
            if ok:
                jpeg_bytes = jpeg.tobytes()
                with self._frame_lock:
                    self._latest_jpeg = jpeg_bytes
                    self._latest_raw_bgr = frame
                self._new_frame_event.set()

            # Throttle slightly to conserve CPU
            time.sleep(0.015)

        logger.info("Webcam capture loop terminated.")

    async def get_stream(self) -> AsyncGenerator[bytes, None]:
        """Yield multipart MJPEG frames for HTTP StreamingResponse."""
        if not self.start():
            raise RuntimeError(f"Could not access camera device {self.camera_index}.")

        with self._clients_lock:
            self._active_clients += 1
            if self._idle_timer:
                self._idle_timer.cancel()
                self._idle_timer = None

        logger.info(f"Client connected to webcam stream (active clients: {self._active_clients}).")

        try:
            while self._is_running:
                # Wait for next frame event
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, self._new_frame_event.wait, 0.2)
                self._new_frame_event.clear()

                with self._frame_lock:
                    jpeg = self._latest_jpeg

                if jpeg:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n"
                        b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                        + jpeg + b"\r\n"
                    )
                else:
                    await asyncio.sleep(0.02)

        finally:
            with self._clients_lock:
                self._active_clients = max(0, self._active_clients - 1)
                logger.info(f"Client disconnected from webcam stream (remaining: {self._active_clients}).")
                if self._active_clients == 0:
                    self._schedule_auto_shutdown(delay_sec=5.0)

    def get_snapshot(self) -> Optional[bytes]:
        """Capture or return the latest annotated JPEG frame."""
        if not self._is_running:
            # Quick one-shot grab if camera is off
            cap = self._open_capture()
            if not cap:
                return None
            try:
                for _ in range(5):  # warm up auto-exposure
                    cap.read()
                ret, frame = cap.read()
                if not ret or frame is None:
                    return None

                from app.websocket.handlers import _get_face_service
                face_service = _get_face_service()
                annotated, _ = face_service.annotate_frame(frame, threshold=0.40, fps=None)
                _, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
                return jpeg.tobytes() if _ else None
            finally:
                cap.release()

        with self._frame_lock:
            return self._latest_jpeg

    def get_status(self) -> Dict[str, Any]:
        """Get live telemetry and status of the webcam service."""
        return {
            "is_running": self._is_running,
            "active_clients": self._active_clients,
            "fps": self.fps,
            "camera_index": self.camera_index,
            "faces_detected": self.last_face_count,
        }


_streamer: Optional[CameraStreamer] = None


def get_camera_streamer() -> CameraStreamer:
    """Return the global CameraStreamer singleton."""
    global _streamer
    if _streamer is None:
        _streamer = CameraStreamer()
    return _streamer
