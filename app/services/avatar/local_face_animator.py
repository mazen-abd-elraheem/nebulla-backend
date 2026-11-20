"""UniFace + OpenCV Landmark-Driven Facial Expression & Lip-Sync Avatar Engine.

Runs natively on CPU (using the project's existing UniFace RetinaFace ONNX
5-point landmark detector + OpenCV localized Gaussian displacement-field
warping) and emits the exact same artifact contract as `GAGAvatarEngine`:
  - 512x512 face-framed studio portrait (`portrait_pil`)
  - 12 canonical facial expression sprites + natural `blink` sprite (`sprites_pil`)
  - 3 jaw/lip-sync mouth opening levels per expression (`mouth_pil`)
  - Real detected facial landmarks (`landmarks`)
  - On-demand animated GIF/PNG rendering (`render_expression_frame`, `render_animation_frames`)
"""

from __future__ import annotations

import math
import threading
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageOps

from app.core.logger import get_logger
from app.services.avatar.emoji_actions import FACE_EMOJI_ACTIONS

logger = get_logger(__name__)

TARGET_SIZE = 512

# Expression deformation recipes driven by detected 5-point landmarks (subtle, human, photorealistic)
_LOCAL_EXPRESSION_RECIPES: Dict[str, Dict[str, Any]] = {
    "neutral": {},
    "blink": {"blink_l": 0.85, "blink_r": 0.85},
    "happy": {"smile": 0.65, "cheek_lift": 0.30, "mouth_open": 0.08, "warmth": 1.04},
    "laugh": {
        "smile": 0.85,
        "cheek_lift": 0.45,
        "squint": 0.20,
        "mouth_open": 0.28,
        "tilt_deg": 1.2,
        "warmth": 1.05,
    },
    "love": {
        "smile": 0.60,
        "cheek_lift": 0.28,
        "blush": 0.22,
        "tilt_deg": 1.4,
        "warmth": 1.06,
    },
    "sad": {
        "smile": -0.50,
        "brow_inner_lift": 0.40,
        "blink_l": 0.15,
        "blink_r": 0.15,
        "tilt_deg": -1.2,
        "warmth": 0.94,
    },
    "surprised": {
        "brow_raise": 0.60,
        "eye_widen": 0.35,
        "mouth_o": 0.35,
        "mouth_open": 0.28,
        "warmth": 1.03,
    },
    "angry": {
        "brow_furrow": 0.60,
        "squint": 0.20,
        "smile": -0.38,
        "mouth_tense": 0.35,
        "warmth": 1.02,
    },
    "thinking": {
        "brow_asym": 0.50,
        "mouth_shift_x": 0.25,
        "smile": -0.08,
        "tilt_deg": 1.8,
    },
    "wink": {
        "blink_r": 0.85,
        "smile": 0.55,
        "cheek_lift": 0.25,
        "tilt_deg": 1.4,
        "warmth": 1.04,
    },
    "sleepy": {
        "blink_l": 0.55,
        "blink_r": 0.55,
        "mouth_open": 0.06,
        "tilt_deg": -1.4,
        "warmth": 0.96,
    },
    "wave": {"smile": 0.68, "cheek_lift": 0.30, "mouth_open": 0.10, "tilt_deg": 1.2, "warmth": 1.04},
    "like": {"smile": 0.65, "cheek_lift": 0.28, "mouth_open": 0.06, "tilt_deg": -1.2, "warmth": 1.04},
}

_MOUTH_LEVEL_AMOUNTS: Dict[int, float] = {
    1: 0.15,
    2: 0.32,
    3: 0.50,
}


class LocalFaceAnimator:
    """CPU-native landmark-driven facial avatar animator using UniFace + OpenCV."""

    _instance: Optional["LocalFaceAnimator"] = None
    _init_lock = threading.Lock()

    def __init__(self) -> None:
        self._detector = None
        self._det_lock = threading.Lock()
        self._grid_x, self._grid_y = np.meshgrid(
            np.arange(TARGET_SIZE, dtype=np.float32),
            np.arange(TARGET_SIZE, dtype=np.float32),
        )

    @classmethod
    def get_instance(cls) -> "LocalFaceAnimator":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _get_detector(self):
        if self._detector is not None:
            return None if self._detector == "disabled" else self._detector
        with self._det_lock:
            if self._detector is None:
                try:
                    import uniface

                    det = uniface.RetinaFace()
                    if hasattr(det, "confidence_threshold"):
                        det.confidence_threshold = 0.35
                    self._detector = det
                    logger.info("LocalFaceAnimator initialized UniFace RetinaFace landmark detector.")
                except Exception as exc:
                    logger.warning(f"UniFace RetinaFace unavailable in LocalFaceAnimator: {exc}")
                    self._detector = "disabled"
        return None if self._detector == "disabled" else self._detector

    # ── Face Detection, Framing & Style Grading ──────────────────────────────

    def detect_and_frame(
        self,
        src_pil: Image.Image,
        style: str = "realistic",
    ) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Detect face & 5 landmarks, frame a 512x512 studio portrait, and map landmarks."""
        rgb = np.asarray(src_pil.convert("RGB"), dtype=np.uint8)
        h, w = rgb.shape[:2]

        det = self._get_detector()
        face = None
        if det is not None:
            try:
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                faces = det.detect(bgr)
                if faces:
                    # Pick largest prominent face
                    face = max(
                        faces,
                        key=lambda f: float((f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1])),
                    )
            except Exception as exc:
                logger.warning(f"RetinaFace detect error: {exc}")

        if face is not None and face.landmarks is not None and len(face.landmarks) >= 5:
            x1, y1, x2, y2 = [float(v) for v in face.bbox[:4]]
            fw = max(1.0, x2 - x1)
            fh = max(1.0, y2 - y1)
            fcx = (x1 + x2) * 0.5
            fcy = (y1 + y2) * 0.5

            # Natural portrait framing: upper-body / head-and-shoulders, strictly clamped within photo bounds
            max_crop = float(min(w, h))
            crop_size = max(fw * 2.30, fh * 2.10)
            crop_size = min(crop_size, max_crop)
            crop_size = max(crop_size, 128.0)

            # Place face centered horizontally and slightly above center vertically (golden portrait ratio)
            cx0 = float(np.clip(fcx - crop_size * 0.5, 0.0, max(0.0, float(w) - crop_size)))
            cy0 = float(np.clip(fcy - crop_size * 0.42, 0.0, max(0.0, float(h) - crop_size)))

            crop_rgb, actual_x0, actual_y0, actual_size = self._safe_square_crop(
                rgb, cx0, cy0, crop_size
            )
            portrait_rgb = cv2.resize(
                crop_rgb,
                (TARGET_SIZE, TARGET_SIZE),
                interpolation=cv2.INTER_LANCZOS4,
            )

            scale = TARGET_SIZE / actual_size
            pts = np.asarray(face.landmarks, dtype=np.float32)

            def _norm_pt(pt: np.ndarray) -> List[float]:
                nx = float(np.clip(((pt[0] - actual_x0) * scale) / TARGET_SIZE, 0.08, 0.92))
                ny = float(np.clip(((pt[1] - actual_y0) * scale) / TARGET_SIZE, 0.08, 0.92))
                return [round(nx, 4), round(ny, 4)]

            l_eye = _norm_pt(pts[0])
            r_eye = _norm_pt(pts[1])
            # Ensure left_eye has smaller x than right_eye
            if l_eye[0] > r_eye[0]:
                l_eye, r_eye = r_eye, l_eye
            nose = _norm_pt(pts[2])
            l_mouth = _norm_pt(pts[3])
            r_mouth = _norm_pt(pts[4])
            if l_mouth[0] > r_mouth[0]:
                l_mouth, r_mouth = r_mouth, l_mouth

            mouth = [
                round((l_mouth[0] + r_mouth[0]) * 0.5, 4),
                round((l_mouth[1] + r_mouth[1]) * 0.5, 4),
            ]
            inter_eye = max(0.08, abs(r_eye[0] - l_eye[0]))
            eye_w = round(float(np.clip(inter_eye * 0.46, 0.06, 0.16)), 4)
            mouth_w = round(
                float(np.clip(abs(r_mouth[0] - l_mouth[0]) * 1.15, inter_eye * 0.65, 0.34)),
                4,
            )

            landmarks: Dict[str, Any] = {
                "left_eye": l_eye,
                "right_eye": r_eye,
                "nose": nose,
                "mouth": mouth,
                "left_mouth": l_mouth,
                "right_mouth": r_mouth,
                "eye_width": eye_w,
                "mouth_width": mouth_w,
                "face_detected": True,
            }
        else:
            fitted = ImageOps.fit(
                src_pil.convert("RGB"),
                (TARGET_SIZE, TARGET_SIZE),
                method=Image.Resampling.LANCZOS,
                centering=(0.5, 0.28),
            )
            portrait_rgb = np.asarray(fitted, dtype=np.uint8)
            landmarks = {
                "left_eye": [0.38, 0.42],
                "right_eye": [0.62, 0.42],
                "nose": [0.50, 0.55],
                "mouth": [0.50, 0.70],
                "left_mouth": [0.41, 0.70],
                "right_mouth": [0.59, 0.70],
                "eye_width": 0.10,
                "mouth_width": 0.20,
                "face_detected": False,
            }

        portrait_rgb = self._apply_studio_style(portrait_rgb, style)
        return portrait_rgb, landmarks

    @staticmethod
    def _safe_square_crop(
        rgb: np.ndarray,
        x0: float,
        y0: float,
        size: float,
    ) -> Tuple[np.ndarray, float, float, float]:
        h, w = rgb.shape[:2]
        # Guarantee crop fits strictly within image boundaries with zero padding or mirroring
        isize = max(64, min(int(round(size)), min(w, h)))
        ix0 = max(0, min(int(round(x0)), max(0, w - isize)))
        iy0 = max(0, min(int(round(y0)), max(0, h - isize)))
        crop = rgb[iy0 : iy0 + isize, ix0 : ix0 + isize]
        return crop, float(ix0), float(iy0), float(isize)

    @staticmethod
    def _apply_studio_style(rgb: np.ndarray, style: str) -> np.ndarray:
        """Apply crisp portrait finishing matching realistic / studio_3d / stylized presets."""
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        if style == "studio_3d":
            # Edge-preserving bilateral smooth for clean 3D avatar look while keeping sharp eyes/hair
            smooth = cv2.bilateralFilter(bgr, d=9, sigmaColor=42, sigmaSpace=42)
            bgr = cv2.addWeighted(bgr, 0.45, smooth, 0.55, 0)
            out_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(out_rgb)
            pil = ImageEnhance.Contrast(pil).enhance(1.06)
            pil = ImageEnhance.Color(pil).enhance(1.08)
            pil = ImageEnhance.Sharpness(pil).enhance(1.12)
            return np.asarray(pil, dtype=np.uint8)
        if style == "stylized":
            smooth = cv2.bilateralFilter(bgr, d=11, sigmaColor=65, sigmaSpace=65)
            bgr = cv2.addWeighted(bgr, 0.30, smooth, 0.70, 0)
            out_rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            pil = Image.fromarray(out_rgb)
            pil = ImageEnhance.Contrast(pil).enhance(1.10)
            pil = ImageEnhance.Color(pil).enhance(1.18)
            pil = ImageEnhance.Sharpness(pil).enhance(1.15)
            return np.asarray(pil, dtype=np.uint8)
        # realistic
        pil = Image.fromarray(rgb)
        pil = ImageEnhance.Contrast(pil).enhance(1.04)
        pil = ImageEnhance.Sharpness(pil).enhance(1.08)
        return np.asarray(pil, dtype=np.uint8)

    # ── Displacement Field Primitives ────────────────────────────────────────

    def _gauss(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
    ) -> np.ndarray:
        dx = (self._grid_x - cx) / max(2.0, rx)
        dy = (self._grid_y - cy) / max(2.0, ry)
        return np.exp(-0.5 * (dx * dx + dy * dy)).astype(np.float32)

    def render_frame(
        self,
        base_rgb: np.ndarray,
        landmarks: Dict[str, Any],
        expression: str = "neutral",
        mouth_open: float = 0.0,
    ) -> Image.Image:
        """Synthesize a single realistic facial expression + jaw/eyelid frame from landmarks."""
        recipe = dict(_LOCAL_EXPRESSION_RECIPES.get(expression, {}))
        eff_mouth = float(np.clip(max(float(recipe.get("mouth_open", 0.0)), mouth_open), 0.0, 1.0))

        lx, ly = landmarks["left_eye"][0] * TARGET_SIZE, landmarks["left_eye"][1] * TARGET_SIZE
        rx, ry = landmarks["right_eye"][0] * TARGET_SIZE, landmarks["right_eye"][1] * TARGET_SIZE
        mx, my = landmarks["mouth"][0] * TARGET_SIZE, landmarks["mouth"][1] * TARGET_SIZE
        lmx, lmy = landmarks["left_mouth"][0] * TARGET_SIZE, landmarks["left_mouth"][1] * TARGET_SIZE
        rmx, rmy = landmarks["right_mouth"][0] * TARGET_SIZE, landmarks["right_mouth"][1] * TARGET_SIZE

        inter_eye = max(36.0, math.hypot(rx - lx, ry - ly))
        eye_r = max(12.0, float(landmarks.get("eye_width", 0.10)) * TARGET_SIZE * 0.58)
        mouth_half_w = max(18.0, abs(rmx - lmx) * 0.55)

        disp_x = np.zeros((TARGET_SIZE, TARGET_SIZE), dtype=np.float32)
        disp_y = np.zeros((TARGET_SIZE, TARGET_SIZE), dtype=np.float32)

        # 1. Smile / Frown (pull mouth corners up/down + slight cheek lift)
        smile = float(recipe.get("smile", 0.0))
        if abs(smile) > 1e-3:
            corner_r = mouth_half_w * 0.72
            up_shift = smile * inter_eye * 0.095
            out_shift = smile * inter_eye * 0.048
            g_lm = self._gauss(lmx, lmy, corner_r, corner_r * 0.85)
            g_rm = self._gauss(rmx, rmy, corner_r, corner_r * 0.85)
            # In cv2.remap: map_y = y + disp_y. Positive disp_y pulls pixels UP (samples from below).
            disp_y += (g_lm + g_rm) * up_shift
            disp_x += g_lm * out_shift - g_rm * out_shift

        cheek_lift = float(recipe.get("cheek_lift", 0.0))
        if cheek_lift > 1e-3:
            ck_r = inter_eye * 0.36
            g_lc = self._gauss(lx - inter_eye * 0.12, (ly + lmy) * 0.52, ck_r, ck_r * 0.85)
            g_rc = self._gauss(rx + inter_eye * 0.12, (ry + rmy) * 0.52, ck_r, ck_r * 0.85)
            disp_y += (g_lc + g_rc) * (cheek_lift * inter_eye * 0.065)

        # 2. Eyebrows (raise, furrow, inner lift, asymmetric thinking)
        brow_offset_y = inter_eye * 0.30
        brow_rx = eye_r * 1.45
        brow_ry = eye_r * 0.75

        brow_raise = float(recipe.get("brow_raise", 0.0))
        if brow_raise > 1e-3:
            g_lb = self._gauss(lx, ly - brow_offset_y, brow_rx, brow_ry)
            g_rb = self._gauss(rx, ry - brow_offset_y, brow_rx, brow_ry)
            disp_y += (g_lb + g_rb) * (brow_raise * inter_eye * 0.11)

        brow_furrow = float(recipe.get("brow_furrow", 0.0))
        if brow_furrow > 1e-3:
            g_li = self._gauss(lx + eye_r * 0.55, ly - brow_offset_y * 0.88, eye_r * 1.05, brow_ry)
            g_ri = self._gauss(rx - eye_r * 0.55, ry - brow_offset_y * 0.88, eye_r * 1.05, brow_ry)
            # Negative disp_y pulls upper brow pixels DOWN
            disp_y -= (g_li + g_ri) * (brow_furrow * inter_eye * 0.11)
            disp_x += g_li * (-brow_furrow * inter_eye * 0.05) + g_ri * (brow_furrow * inter_eye * 0.05)

        brow_inner_lift = float(recipe.get("brow_inner_lift", 0.0))
        if brow_inner_lift > 1e-3:
            g_li = self._gauss(lx + eye_r * 0.45, ly - brow_offset_y * 0.92, eye_r * 0.95, brow_ry)
            g_ri = self._gauss(rx - eye_r * 0.45, ry - brow_offset_y * 0.92, eye_r * 0.95, brow_ry)
            disp_y += (g_li + g_ri) * (brow_inner_lift * inter_eye * 0.085)

        brow_asym = float(recipe.get("brow_asym", 0.0))
        if brow_asym > 1e-3:
            g_lb = self._gauss(lx, ly - brow_offset_y, brow_rx, brow_ry)
            g_rb = self._gauss(rx, ry - brow_offset_y, brow_rx, brow_ry)
            disp_y += g_lb * (brow_asym * inter_eye * 0.09) - g_rb * (brow_asym * inter_eye * 0.06)

        # 3. Eye Widen / Squint / Blink / Wink
        eye_widen = float(recipe.get("eye_widen", 0.0))
        if eye_widen > 1e-3:
            for ex, ey in ((lx, ly), (rx, ry)):
                g_top = self._gauss(ex, ey - eye_r * 0.45, eye_r * 1.05, eye_r * 0.48)
                g_bot = self._gauss(ex, ey + eye_r * 0.45, eye_r * 1.05, eye_r * 0.48)
                disp_y += g_top * (eye_widen * eye_r * 0.34) - g_bot * (eye_widen * eye_r * 0.24)

        squint = float(recipe.get("squint", 0.0))
        if squint > 1e-3:
            for ex, ey in ((lx, ly), (rx, ry)):
                g_bot = self._gauss(ex, ey + eye_r * 0.42, eye_r * 1.15, eye_r * 0.50)
                disp_y += g_bot * (squint * eye_r * 0.48)

        blink_l = float(recipe.get("blink_l", 0.0))
        blink_r = float(recipe.get("blink_r", 0.0))
        for ex, ey, b_amt in ((lx, ly, blink_l), (rx, ry, blink_r)):
            if b_amt > 1e-3:
                # Natural eyelid closure: smooth lid motion preserving natural skin texture & eyelashes
                g_top = self._gauss(ex, ey - eye_r * 0.25, eye_r * 1.10, eye_r * 0.45)
                g_bot = self._gauss(ex, ey + eye_r * 0.35, eye_r * 1.10, eye_r * 0.45)
                disp_y -= g_top * (b_amt * eye_r * 0.22)
                disp_y += g_bot * (b_amt * eye_r * 0.26)

        # 4. Mouth Shift / Tense / 'O' Shape / Real Jaw Opening
        mouth_shift_x = float(recipe.get("mouth_shift_x", 0.0))
        if abs(mouth_shift_x) > 1e-3:
            g_m = self._gauss(mx, my, mouth_half_w * 1.25, mouth_half_w * 0.72)
            disp_x -= g_m * (mouth_shift_x * inter_eye * 0.085)

        mouth_tense = float(recipe.get("mouth_tense", 0.0))
        if mouth_tense > 1e-3:
            g_ul = self._gauss(mx, my - mouth_half_w * 0.20, mouth_half_w * 1.0, mouth_half_w * 0.35)
            g_ll = self._gauss(mx, my + mouth_half_w * 0.20, mouth_half_w * 1.0, mouth_half_w * 0.35)
            disp_y -= g_ul * (mouth_tense * inter_eye * 0.035)
            disp_y += g_ll * (mouth_tense * inter_eye * 0.035)

        mouth_o = float(recipe.get("mouth_o", 0.0))
        if mouth_o > 1e-3:
            g_lm = self._gauss(lmx, lmy, mouth_half_w * 0.68, mouth_half_w * 0.62)
            g_rm = self._gauss(rmx, rmy, mouth_half_w * 0.68, mouth_half_w * 0.62)
            # Pull corners slightly inward for surprised 'O' shape
            disp_x += g_lm * (-mouth_o * inter_eye * 0.085) + g_rm * (mouth_o * inter_eye * 0.085)

        if eff_mouth > 0.04:
            # Lower lip + chin drop downward naturally; upper lip rises slightly
            jaw_drop = eff_mouth * inter_eye * 0.18
            g_jaw = self._gauss(
                mx,
                my + mouth_half_w * 0.48,
                mouth_half_w * 1.35,
                mouth_half_w * 0.90,
            )
            g_upper_lip = self._gauss(
                mx,
                my - mouth_half_w * 0.22,
                mouth_half_w * 0.90,
                mouth_half_w * 0.35,
            )
            disp_y -= g_jaw * jaw_drop
            disp_y += g_upper_lip * (jaw_drop * 0.14)

        # Apply smooth sub-pixel remap with replicate border mode (no mirroring)
        map_x = np.clip(self._grid_x + disp_x, 0, TARGET_SIZE - 1).astype(np.float32)
        map_y = np.clip(self._grid_y + disp_y, 0, TARGET_SIZE - 1).astype(np.float32)
        warped = cv2.remap(
            base_rgb,
            map_x,
            map_y,
            interpolation=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

        # 5. Subtle Rosy Blush for 'love' expression
        blush = float(recipe.get("blush", 0.0))
        if blush > 1e-3:
            warped = self._blend_rosy_blush(warped, lx, ly, rx, ry, my, inter_eye, blush)

        # 6. Gentle Natural Head Tilt for Expressive Pose
        tilt_deg = float(recipe.get("tilt_deg", 0.0))
        if abs(tilt_deg) > 0.1:
            pivot = (TARGET_SIZE * 0.5, TARGET_SIZE * 0.58)
            rot_m = cv2.getRotationMatrix2D(pivot, tilt_deg, 1.015)
            warped = cv2.warpAffine(
                warped,
                rot_m,
                (TARGET_SIZE, TARGET_SIZE),
                flags=cv2.INTER_CUBIC,
                borderMode=cv2.BORDER_REPLICATE,
            )

        # 7. Subtle Mood Warmth / Brightness Grading
        pil = Image.fromarray(warped)
        warmth = float(recipe.get("warmth", 1.0))
        if abs(warmth - 1.0) > 0.01:
            pil = ImageEnhance.Color(pil).enhance(warmth)
            pil = ImageEnhance.Brightness(pil).enhance(0.98 + (warmth - 0.98) * 0.45)

        return pil

    @staticmethod
    def _blend_mouth_interior(
        rgb: np.ndarray,
        mx: float,
        my: float,
        mouth_half_w: float,
        open_amt: float,
        inter_eye: float,
        smiling: bool = False,
    ) -> np.ndarray:
        """Blend a realistic soft-feathered oral cavity between the parted lips."""
        out = rgb.astype(np.float32)
        h, w = out.shape[:2]

        cavity_rx = max(6.0, mouth_half_w * (0.72 + 0.14 * open_amt))
        cavity_ry = max(2.5, open_amt * inter_eye * 0.115)
        cy = my + cavity_ry * 0.42

        # Compute bounding box for fast local blending
        x0 = max(0, int(mx - cavity_rx * 1.8))
        x1 = min(w, int(mx + cavity_rx * 1.8) + 1)
        y0 = max(0, int(cy - cavity_ry * 2.2))
        y1 = min(h, int(cy + cavity_ry * 2.2) + 1)
        if x1 <= x0 or y1 <= y0:
            return rgb

        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        nx = (xx - mx) / cavity_rx
        ny = (yy - cy) / cavity_ry

        # Slight upward curve at corners when smiling
        if smiling:
            ny = ny + 0.22 * (nx * nx)

        dist = np.sqrt(nx * nx + ny * ny)
        # Smooth feathered mask inside ellipse (dist < 1)
        alpha = np.clip((1.02 - dist) / 0.32, 0.0, 1.0)
        alpha = (alpha * alpha * (3.0 - 2.0 * alpha)) * float(np.clip(0.55 + open_amt * 0.40, 0.0, 0.92))

        # Deep warm dark-crimson interior color (realistic mouth shadow, not flat black)
        interior = np.zeros((y1 - y0, x1 - x0, 3), dtype=np.float32)
        interior[:, :, 0] = 52.0  # R
        interior[:, :, 1] = 24.0  # G
        interior[:, :, 2] = 28.0  # B

        # Subtle upper teeth gleam near top of open mouth when laughing/speaking wide
        if open_amt >= 0.45:
            teeth_mask = np.clip((1.0 - np.abs(nx) / 0.78), 0.0, 1.0) * np.clip(
                (1.0 - np.abs(ny + 0.52) / 0.36), 0.0, 1.0
            )
            teeth_alpha = teeth_mask * (0.48 if smiling else 0.28) * open_amt
            interior[:, :, 0] = interior[:, :, 0] * (1.0 - teeth_alpha) + 228.0 * teeth_alpha
            interior[:, :, 1] = interior[:, :, 1] * (1.0 - teeth_alpha) + 218.0 * teeth_alpha
            interior[:, :, 2] = interior[:, :, 2] * (1.0 - teeth_alpha) + 210.0 * teeth_alpha

        a3 = alpha[:, :, None]
        out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1.0 - a3) + interior * a3
        return np.clip(out, 0, 255).astype(np.uint8)

    @staticmethod
    def _blend_closed_eyelid_crease(
        rgb: np.ndarray,
        ex: float,
        ey: float,
        eye_r: float,
        blink_amt: float,
    ) -> np.ndarray:
        """Add a soft, natural upper-eyelid skin patch & gentle curved lash line."""
        out = rgb.copy()
        h, w = out.shape[:2]

        # Sample average skin tone just above the eye (upper lid skin)
        sx0 = max(0, int(ex - eye_r * 0.7))
        sx1 = min(w, int(ex + eye_r * 0.7))
        sy0 = max(0, int(ey - eye_r * 1.05))
        sy1 = min(h, int(ey - eye_r * 0.45))
        if sx1 <= sx0 or sy1 <= sy0:
            return rgb
        lid_color = np.median(out[sy0:sy1, sx0:sx1].reshape(-1, 3), axis=0).astype(np.float32)

        # Feather-blend lid skin smoothly over the eye aperture
        x0 = max(0, int(ex - eye_r * 1.35))
        x1 = min(w, int(ex + eye_r * 1.35) + 1)
        y0 = max(0, int(ey - eye_r * 0.85))
        y1 = min(h, int(ey + eye_r * 0.85) + 1)
        if x1 <= x0 or y1 <= y0:
            return rgb

        yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
        nx = (xx - ex) / max(4.0, eye_r * 1.02)
        ny = (yy - (ey + eye_r * 0.04)) / max(3.0, eye_r * 0.46)
        dist = np.sqrt(nx * nx + ny * ny)

        lid_alpha = np.clip((1.05 - dist) / 0.42, 0.0, 1.0)
        lid_alpha = (lid_alpha * lid_alpha * (3.0 - 2.0 * lid_alpha)) * float(
            np.clip((blink_amt - 0.55) / 0.45, 0.0, 1.0) * 0.82
        )

        # Subtle natural downward-curved lash line along the bottom of the closed lid
        lash_y = ey + eye_r * (0.16 + 0.14 * (1.0 - nx * nx))
        lash_dist = np.abs(yy - lash_y) / max(1.4, eye_r * 0.095)
        lash_mask = (
            np.exp(-0.5 * lash_dist * lash_dist)
            * np.clip(1.0 - np.abs(nx) * 1.02, 0.0, 1.0)
            * (0.58 * blink_amt)
        )

        patch = out[y0:y1, x0:x1].astype(np.float32)
        patch = patch * (1.0 - lid_alpha[:, :, None]) + lid_color[None, None, :] * lid_alpha[:, :, None]
        lash_color = np.clip(lid_color * 0.28, 18, 65)
        patch = patch * (1.0 - lash_mask[:, :, None]) + lash_color[None, None, :] * lash_mask[:, :, None]

        out[y0:y1, x0:x1] = np.clip(patch, 0, 255).astype(np.uint8)
        return out

    @staticmethod
    def _blend_rosy_blush(
        rgb: np.ndarray,
        lx: float,
        ly: float,
        rx: float,
        ry: float,
        my: float,
        inter_eye: float,
        amount: float,
    ) -> np.ndarray:
        out = rgb.astype(np.float32)
        h, w = out.shape[:2]
        rad = inter_eye * 0.34
        blush_color = np.array([235.0, 115.0, 130.0], dtype=np.float32)

        for cx, cy in (
            (lx - inter_eye * 0.10, (ly + my) * 0.54),
            (rx + inter_eye * 0.10, (ry + my) * 0.54),
        ):
            x0 = max(0, int(cx - rad * 1.6))
            x1 = min(w, int(cx + rad * 1.6) + 1)
            y0 = max(0, int(cy - rad * 1.6))
            y1 = min(h, int(cy + rad * 1.6) + 1)
            if x1 <= x0 or y1 <= y0:
                continue
            yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
            g = np.exp(-0.5 * (((xx - cx) / rad) ** 2 + ((yy - cy) / (rad * 0.8)) ** 2))
            a = (g * amount * 0.35)[:, :, None]
            out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1.0 - a) + blush_color[None, None, :] * a

        return np.clip(out, 0, 255).astype(np.uint8)

    # ── Full Avatar Pack Generation (Same Contract as GAGAvatarEngine) ───────

    def track_and_generate_avatar(
        self,
        src_pil: Image.Image,
        style: str = "realistic",
        expressions: Optional[List[str]] = None,
        avatar_key: str = "avatar",
    ) -> Dict[str, Any]:
        """Generate full portrait, 12 expression sprites + blink, and 3-level mouth frames."""
        expr_list = list(expressions or FACE_EMOJI_ACTIONS.keys())
        base_rgb, landmarks = self.detect_and_frame(src_pil, style=style)
        portrait_pil = Image.fromarray(base_rgb)

        sprites_pil: Dict[str, Image.Image] = {}
        mouth_pil: Dict[str, List[Image.Image]] = {}

        # Generate natural blink frame first
        sprites_pil["blink"] = self.render_frame(
            base_rgb, landmarks, expression="blink", mouth_open=0.0
        )

        # Generate all canonical expression sprites + 3 lip-sync mouth opening levels
        for expr_key in expr_list:
            sprites_pil[expr_key] = self.render_frame(
                base_rgb, landmarks, expression=expr_key, mouth_open=0.0
            )
            mouth_pil[expr_key] = [
                self.render_frame(
                    base_rgb,
                    landmarks,
                    expression=expr_key,
                    mouth_open=_MOUTH_LEVEL_AMOUNTS[lvl],
                )
                for lvl in (1, 2, 3)
            ]

        logger.info(
            f"LocalFaceAnimator generated avatar '{avatar_key}' "
            f"(face_detected={landmarks.get('face_detected')}, "
            f"sprites={len(sprites_pil)}, mouth_sets={len(mouth_pil)})"
        )
        return {
            "engine": "local_face_3d",
            "portrait_pil": portrait_pil,
            "sprites_pil": sprites_pil,
            "mouth_pil": mouth_pil,
            "landmarks": landmarks,
            "tracked_feature": None,
        }

    def render_animation_frames(
        self,
        src_pil: Image.Image,
        landmarks: Optional[Dict[str, Any]] = None,
        expression: str = "happy",
        mouth_open: float = 0.5,
        duration_ms: int = 1200,
        style: str = "realistic",
    ) -> List[Image.Image]:
        """Render multi-frame speaking/expression animation frames for GIF export."""
        base_rgb, detected = self.detect_and_frame(src_pil, style=style)
        lm = landmarks if (landmarks and "left_eye" in landmarks and "mouth" in landmarks) else detected
        steps = max(6, min(14, duration_ms // 120))
        frames: List[Image.Image] = []
        for idx in range(steps):
            phase = idx / max(1, steps - 1)
            wave = abs(math.sin(phase * math.pi * 2.5)) * float(np.clip(mouth_open, 0.2, 0.95))
            if idx == steps // 2:
                frames.append(self.render_frame(base_rgb, lm, expression="blink", mouth_open=wave * 0.5))
            else:
                frames.append(self.render_frame(base_rgb, lm, expression=expression, mouth_open=wave))
        return frames


def get_local_face_animator() -> LocalFaceAnimator:
    return LocalFaceAnimator.get_instance()
