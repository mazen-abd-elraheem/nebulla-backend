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

# Expression deformation recipes driven by detected 5-point landmarks (vivid, distinct, human & photorealistic)
_LOCAL_EXPRESSION_RECIPES: Dict[str, Dict[str, Any]] = {
    "neutral": {},
    "blink": {"blink_l": 0.95, "blink_r": 0.95},
    "happy": {
        "smile": 1.0,
        "cheek_lift": 0.60,
        "squint": 0.40,
    },
    "laugh": {
        "smile": 1.30,
        "cheek_lift": 0.80,
        "squint": 0.60,
        "mouth_open": 0.38,
    },
    "love": {
        "smile": 0.95,
        "cheek_lift": 0.50,
        "squint": 0.35,
        "blush": 0.45,
    },
    "sad": {
        "frown": 1.0,
        "brow_inner_lift": 0.85,
    },
    "surprised": {
        "brow_raise": 1.05,
        "mouth_o": 0.60,
        "mouth_open": 0.40,
    },
    "angry": {
        "brow_furrow": 1.0,
        "squint": 0.50,
        "frown": 0.50,
    },
    "thinking": {
        "brow_asym": 1.05,
        "mouth_shift_x": 0.80,
    },
    "wink": {
        "smile": 0.95,
        "blink_r": 0.95,
        "squint": 0.30,
        "cheek_lift": 0.50,
    },
    "sleepy": {
        "blink_l": 0.65,
        "blink_r": 0.65,
    },
    "wave": {
        "smile": 1.05,
        "cheek_lift": 0.55,
    },
    "like": {
        "smile": 0.95,
        "brow_asym": 0.45,
    },
}

_MOUTH_LEVEL_AMOUNTS: Dict[int, float] = {
    1: 0.28,
    2: 0.58,
    3: 0.88,
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

        # 1. Smile (Corners UP and OUT with asymmetric vertical falloff: chin is never pulled)
        smile = float(recipe.get("smile", 0.0))
        if smile > 1e-3:
            up_px = smile * 11.5
            out_px = smile * 7.0
            for cx, cy, sign in ((lmx, lmy, 1.0), (rmx, rmy, -1.0)):
                dx = (self._grid_x - cx) / max(2.0, mouth_half_w * 0.70)
                ry_c = np.where(self._grid_y < cy, mouth_half_w * 0.70, mouth_half_w * 0.35)
                dy = (self._grid_y - cy) / ry_c
                g = np.exp(-0.5 * (dx * dx + dy * dy)).astype(np.float32)
                disp_y += g * up_px
                disp_x += g * (out_px * sign)

        # 2. Frown (Corners DOWN with smooth gentle falloff)
        frown = float(recipe.get("frown", 0.0))
        if frown < 1e-3 and smile < -1e-3:
            frown = abs(smile)
        if frown > 1e-3:
            down_px = frown * 10.0
            for cx, cy, sign in ((lmx, lmy, -1.0), (rmx, rmy, 1.0)):
                dx = (self._grid_x - cx) / max(2.0, mouth_half_w * 0.70)
                ry_c = np.where(self._grid_y > cy, mouth_half_w * 0.70, mouth_half_w * 0.35)
                dy = (self._grid_y - cy) / ry_c
                g = np.exp(-0.5 * (dx * dx + dy * dy)).astype(np.float32)
                disp_y -= g * down_px
                disp_x += g * (frown * 3.0 * sign)

        # 3. Cheek lift (apples of cheeks lift)
        cheek_lift = float(recipe.get("cheek_lift", 0.0))
        if cheek_lift > 1e-3:
            ck_r = inter_eye * 0.36
            g_lc = np.exp(-0.5 * (((self._grid_x - (lx - inter_eye * 0.08)) / ck_r) ** 2 + ((self._grid_y - (ly + lmy) * 0.50) / (ck_r * 0.75)) ** 2))
            g_rc = np.exp(-0.5 * (((self._grid_x - (rx + inter_eye * 0.08)) / ck_r) ** 2 + ((self._grid_y - (ry + rmy) * 0.50) / (ck_r * 0.75)) ** 2))
            disp_y += (g_lc + g_rc).astype(np.float32) * (cheek_lift * 8.0)

        # 4. Eyebrows (smooth Gaussian on brow bone, zero sharp cutoffs)
        brow_center_y = ly - inter_eye * 0.35
        brow_rx = eye_r * 1.55
        brow_ry = eye_r * 0.50

        brow_raise = float(recipe.get("brow_raise", 0.0))
        if brow_raise > 1e-3:
            g_lb = np.exp(-0.5 * (((self._grid_x - lx) / brow_rx) ** 2 + ((self._grid_y - brow_center_y) / brow_ry) ** 2))
            g_rb = np.exp(-0.5 * (((self._grid_x - rx) / brow_rx) ** 2 + ((self._grid_y - brow_center_y) / brow_ry) ** 2))
            disp_y += (g_lb + g_rb).astype(np.float32) * (brow_raise * 9.5)

        brow_furrow = float(recipe.get("brow_furrow", 0.0))
        if brow_furrow > 1e-3:
            g_li = np.exp(-0.5 * (((self._grid_x - (lx + eye_r * 0.45)) / (eye_r * 1.25)) ** 2 + ((self._grid_y - (brow_center_y + 4)) / brow_ry) ** 2))
            g_ri = np.exp(-0.5 * (((self._grid_x - (rx - eye_r * 0.45)) / (eye_r * 1.25)) ** 2 + ((self._grid_y - (brow_center_y + 4)) / brow_ry) ** 2))
            disp_y -= (g_li + g_ri).astype(np.float32) * (brow_furrow * 8.5)
            disp_x += (g_li * (-brow_furrow * 4.5) + g_ri * (brow_furrow * 4.5)).astype(np.float32)

        brow_inner_lift = float(recipe.get("brow_inner_lift", 0.0))
        if brow_inner_lift > 1e-3:
            g_li = np.exp(-0.5 * (((self._grid_x - (lx + eye_r * 0.40)) / (eye_r * 1.15)) ** 2 + ((self._grid_y - brow_center_y) / brow_ry) ** 2))
            g_ri = np.exp(-0.5 * (((self._grid_x - (rx - eye_r * 0.40)) / (eye_r * 1.15)) ** 2 + ((self._grid_y - brow_center_y) / brow_ry) ** 2))
            disp_y += (g_li + g_ri).astype(np.float32) * (brow_inner_lift * 7.5)

        brow_asym = float(recipe.get("brow_asym", 0.0))
        if abs(brow_asym) > 1e-3:
            g_lb = np.exp(-0.5 * (((self._grid_x - lx) / brow_rx) ** 2 + ((self._grid_y - brow_center_y) / brow_ry) ** 2))
            g_rb = np.exp(-0.5 * (((self._grid_x - rx) / brow_rx) ** 2 + ((self._grid_y - brow_center_y) / brow_ry) ** 2))
            disp_y += (g_lb * (brow_asym * 10.0) - g_rb * (brow_asym * 4.5)).astype(np.float32)

        # 5. Eyes: Lower lid squint (natural Duchenne smile eye)
        squint = float(recipe.get("squint", 0.0))
        if squint > 1e-3:
            for ex, ey in ((lx, ly), (rx, ry)):
                g_bot = np.exp(-0.5 * (((self._grid_x - ex) / (eye_r * 1.10)) ** 2 + ((self._grid_y - (ey + eye_r * 0.32)) / (eye_r * 0.42)) ** 2))
                disp_y += g_bot.astype(np.float32) * (squint * 6.5)

        # 6. Eye widen (surprised)
        eye_widen = float(recipe.get("eye_widen", 0.0))
        if eye_widen > 1e-3:
            for ex, ey in ((lx, ly), (rx, ry)):
                g_top = np.exp(-0.5 * (((self._grid_x - ex) / (eye_r * 1.15)) ** 2 + ((self._grid_y - (ey - eye_r * 0.35)) / (eye_r * 0.45)) ** 2))
                disp_y += g_top.astype(np.float32) * (eye_widen * 5.5)

        # 7. Blink / Wink
        blink_l = float(recipe.get("blink_l", 0.0))
        blink_r = float(recipe.get("blink_r", 0.0))
        for ex, ey, b_amt in ((lx, ly, blink_l), (rx, ry, blink_r)):
            if b_amt > 1e-3:
                g_top = np.exp(-0.5 * (((self._grid_x - ex) / (eye_r * 1.15)) ** 2 + ((self._grid_y - (ey - 2.0)) / (eye_r * 0.48)) ** 2))
                g_bot = np.exp(-0.5 * (((self._grid_x - ex) / (eye_r * 1.10)) ** 2 + ((self._grid_y - (ey + eye_r * 0.35)) / (eye_r * 0.38)) ** 2))
                disp_y -= (g_top * b_amt * 12.0).astype(np.float32)
                disp_y += (g_bot * b_amt * 7.0).astype(np.float32)

        # 8. Mouth 'O' shape & shift (thinking)
        mouth_o = float(recipe.get("mouth_o", 0.0))
        if mouth_o > 1e-3:
            for cx, cy, sign in ((lmx, lmy, -1.0), (rmx, rmy, 1.0)):
                dx = (self._grid_x - cx) / max(2.0, mouth_half_w * 0.70)
                dy = (self._grid_y - cy) / max(2.0, mouth_half_w * 0.55)
                g = np.exp(-0.5 * (dx * dx + dy * dy)).astype(np.float32)
                disp_x += g * (mouth_o * 8.0 * sign)

        mouth_shift_x = float(recipe.get("mouth_shift_x", 0.0))
        if abs(mouth_shift_x) > 1e-3:
            g_m = np.exp(-0.5 * (((self._grid_x - mx) / (mouth_half_w * 1.25)) ** 2 + ((self._grid_y - my) / (mouth_half_w * 0.65)) ** 2))
            disp_x -= g_m.astype(np.float32) * (mouth_shift_x * 8.5)

        # Apply smooth sub-pixel remap with replicate border mode (zero distortion, fixed background)
        map_x = np.clip(self._grid_x + disp_x, 0, TARGET_SIZE - 1).astype(np.float32)
        map_y = np.clip(self._grid_y + disp_y, 0, TARGET_SIZE - 1).astype(np.float32)
        warped = cv2.remap(
            base_rgb,
            map_x,
            map_y,
            interpolation=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

        # 9. Seamless Natural Mouth Opening & Lip Parting (Reveals Real Teeth on Speech / Laugh)
        if eff_mouth > 0.04:
            warped = self._render_seamless_mouth_opening(
                warped,
                mx=mx,
                my=my,
                lmx=lmx,
                rmx=rmx,
                mouth_half_w=mouth_half_w,
                open_amt=eff_mouth,
                smile_amt=smile,
            )

        # 10. Subtle Rosy Blush for 'love' expression
        blush = float(recipe.get("blush", 0.0))
        if blush > 1e-3:
            warped = self._blend_rosy_blush(warped, lx, ly, rx, ry, my, inter_eye, blush)

        return Image.fromarray(warped)

    def _render_seamless_mouth_opening(
        self,
        base_rgb: np.ndarray,
        mx: float,
        my: float,
        lmx: float,
        rmx: float,
        mouth_half_w: float,
        open_amt: float,
        smile_amt: float = 0.0,
    ) -> np.ndarray:
        """Naturally parts upper and lower lips to reveal teeth and oral cavity for speech."""
        max_gap = open_amt * 12.0
        x_dist = np.abs(self._grid_x - mx) / (mouth_half_w * 0.88)
        h_weight = np.clip(1.0 - x_dist * x_dist, 0.0, 1.0) ** 1.3
        gap = max_gap * h_weight

        smile_arch = smile_amt * 3.5 * (np.clip((self._grid_x - mx) / mouth_half_w, -1.0, 1.0) ** 2)
        seam = my - (open_amt * 2.0) - smile_arch

        chin_falloff = np.clip(1.0 - (self._grid_y - (seam + gap)) / 45.0, 0.0, 1.0)
        chin_falloff = chin_falloff * chin_falloff

        lower_map_y = np.clip(self._grid_y - gap * chin_falloff, 0, TARGET_SIZE - 1).astype(np.float32)
        lower_warped = cv2.remap(
            base_rgb,
            self._grid_x,
            lower_map_y,
            interpolation=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )

        res = base_rgb.copy().astype(np.float32)

        gap_safe = np.maximum(1e-4, gap)
        t_gap = np.clip((self._grid_y - seam) / gap_safe, 0.0, 1.0)

        cavity_rgb = np.zeros((TARGET_SIZE, TARGET_SIZE, 3), dtype=np.float32)
        cavity_rgb[:, :, 0] = 45.0 + t_gap * 28.0
        cavity_rgb[:, :, 1] = 16.0 + t_gap * 18.0
        cavity_rgb[:, :, 2] = 20.0 + t_gap * 18.0

        rel_x = (self._grid_x - mx)
        groove_dist = np.min(np.abs([rel_x, rel_x - 10.5, rel_x + 10.5, rel_x - 20.5, rel_x + 20.5]), axis=0)
        grooves = np.clip((groove_dist / 1.5), 0.76, 1.0)

        teeth_h = np.clip((0.60 - t_gap) / 0.18, 0.0, 1.0)
        teeth_w = np.clip(1.0 - (x_dist / 0.85) ** 2, 0.0, 1.0)
        teeth_mask = (teeth_h * teeth_w)[:, :, None]

        teeth_color = np.zeros_like(cavity_rgb)
        teeth_color[:, :, 0] = 238.0 * grooves
        teeth_color[:, :, 1] = 232.0 * grooves
        teeth_color[:, :, 2] = 224.0 * grooves

        lip_shadow = np.clip(t_gap / 0.25, 0.40, 1.0)[:, :, None]
        teeth_color = teeth_color * lip_shadow

        gap_content = cavity_rgb * (1.0 - teeth_mask) + teeth_color * teeth_mask

        blend_y_top = np.clip((self._grid_y - (seam - 0.5)), 0.0, 1.0)
        blend_y_bot = np.clip((self._grid_y - (seam + gap - 0.5)), 0.0, 1.0)

        in_gap = (blend_y_top * (1.0 - blend_y_bot) * h_weight)[:, :, None]
        in_lower = (blend_y_bot * h_weight)[:, :, None]

        res = res * (1.0 - in_gap - in_lower) + gap_content * in_gap + lower_warped * in_lower
        return np.clip(res, 0, 255).astype(np.uint8)

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
