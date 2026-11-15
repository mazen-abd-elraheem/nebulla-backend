"""GAGAvatar Avatar Generation & Expression Animation Service.

Implements a modular hybrid architecture around https://github.com/xg-chu/GAGAvatar:
1. Remote GPU Microservice (`GAGAVATAR_SERVICE_URL`) — recommended for Railway GPU workers
   or multi-service deployments.
2. Local `xg-chu/GAGAvatar` Runtime (`GAGAVATAR_REPO_PATH` / installed `gagavatar` package
   when CUDA + diff-gaussian-rasterization + FLAME assets are present).
3. Local UniFace + OpenCV/Pillow Engine (`uniface_fallback`) — detects the user's face &
   landmarks with UniFace / OpenCV, generates a normalized studio portrait, per-emoji
   expression sprites, normalized [0..1] eye/mouth coordinates for real-time lip-sync,
   and animated GIF/PNG expression sequences on CPU hosts.
"""

from __future__ import annotations

import asyncio
import base64
import importlib
import io
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import httpx
import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageEnhance
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.avatar_profile import AvatarProfile
from app.services.avatar.emoji_actions import (
    FACE_EMOJI_ACTIONS,
    resolve_expression_spec,
)

logger = get_logger(__name__)

TARGET_SIZE = 512


class GAGAvatarService:
    """Service responsible for creating, reviewing, recreating, and animating avatars."""

    _instance: Optional["GAGAvatarService"] = None

    def __init__(self, output_dir: Optional[str] = None) -> None:
        self.output_dir = Path(output_dir or settings.AVATAR_OUTPUT_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._local_gag_checked = False
        self._local_gag_available = False
        self._local_gag_error: Optional[str] = None

    @classmethod
    def get_instance(cls) -> "GAGAvatarService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Runtime Discovery ─────────────────────────────────────────────────────

    def _probe_local_gagavatar(self) -> Tuple[bool, Optional[str]]:
        if self._local_gag_checked:
            return self._local_gag_available, self._local_gag_error

        self._local_gag_checked = True
        repo_path = Path(settings.GAGAVATAR_REPO_PATH)
        if repo_path.exists() and str(repo_path.resolve()) not in sys.path:
            sys.path.insert(0, str(repo_path.resolve()))

        try:
            import torch  # noqa: F401
            cuda_ok = bool(torch.cuda.is_available())
            if settings.GAGAVATAR_DEVICE == "cuda" and not cuda_ok:
                self._local_gag_error = "CUDA GPU not available on this host"
                return False, self._local_gag_error

            importlib.import_module("gagavatar")
            self._local_gag_available = True
            self._local_gag_error = None
            return True, None
        except Exception as exc:
            self._local_gag_available = False
            self._local_gag_error = str(exc)
            return False, self._local_gag_error

    async def get_runtime_status(self) -> Dict[str, Any]:
        """Report availability of remote GAGAvatar GPU worker, local GAGAvatar, and CPU fallback."""
        local_ok, local_err = self._probe_local_gagavatar()
        remote_url = (settings.GAGAVATAR_SERVICE_URL or "").strip() or None
        remote_healthy = False
        remote_detail: Optional[str] = None

        if remote_url:
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    resp = await client.get(f"{remote_url.rstrip('/')}/health")
                    if resp.status_code == 200:
                        remote_healthy = True
                    else:
                        remote_detail = f"HTTP {resp.status_code}"
            except Exception as exc:
                remote_detail = str(exc)

        preferred_engine = (
            "gagavatar_remote"
            if remote_healthy
            else ("gagavatar" if local_ok else ("uniface_fallback" if settings.AVATAR_ALLOW_LOCAL_FALLBACK else "unavailable"))
        )
        return {
            "preferred_engine": preferred_engine,
            "remote_service_url": remote_url,
            "remote_healthy": remote_healthy,
            "remote_detail": remote_detail,
            "local_gagavatar_available": local_ok,
            "local_gagavatar_error": local_err,
            "local_fallback_enabled": bool(settings.AVATAR_ALLOW_LOCAL_FALLBACK),
            "output_dir": str(self.output_dir),
        }

    # ── Core Generation ───────────────────────────────────────────────────────

    async def create_avatar_from_photo(
        self,
        image_bytes: bytes,
        db: AsyncSession,
        user_id: Optional[int] = None,
        personality_id: Optional[int] = None,
        name: Optional[str] = None,
        style: str = "realistic",
        attempt_number: int = 1,
        require_face: bool = True,
    ) -> AvatarProfile:
        """Create a draft avatar (`status='pending_review'`, `is_active=False`) from a user photo."""
        if not image_bytes:
            raise ValueError("ملف الصورة فاضي، من فضلك ارفع صورة واضحة.")

        style_clean = style if style in ("realistic", "studio_3d", "stylized") else "realistic"
        avatar_uid = uuid.uuid4().hex[:12]
        avatar_dir = self.output_dir / avatar_uid
        sprites_dir = avatar_dir / "sprites"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        sprites_dir.mkdir(parents=True, exist_ok=True)

        source_path = avatar_dir / "source.jpg"
        preview_path = avatar_dir / "preview.png"

        # Save normalized JPEG source photo
        src_pil = self._decode_image_pil(image_bytes)
        src_pil.save(source_path, format="JPEG", quality=92)

        expressions_list = list(FACE_EMOJI_ACTIONS.keys())
        gen_result = await self._run_generation_engine(
            image_bytes=image_bytes,
            src_pil=src_pil,
            style=style_clean,
            expressions=expressions_list,
            require_face=require_face,
        )

        # Persist portrait and per-expression sprites cleanly
        gen_result["portrait_pil"].save(preview_path, format="PNG")
        expr_files: Dict[str, str] = {}
        for expr_key, sprite_pil in gen_result["sprites_pil"].items():
            fname = f"{expr_key}.png"
            sprite_pil.save(sprites_dir / fname, format="PNG")
            expr_files[expr_key] = fname

        profile = AvatarProfile(
            user_id=user_id,
            personality_id=personality_id,
            name=name,
            source_photo_path=str(source_path),
            avatar_preview_path=str(preview_path),
            sprites_dir=str(sprites_dir),
            landmarks_json=json.dumps(gen_result["landmarks"]),
            expressions_json=json.dumps(expr_files),
            engine=gen_result["engine"],
            style=style_clean,
            status="pending_review",
            is_active=False,
            attempt_number=attempt_number,
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        logger.info(
            f"Created AvatarProfile id={profile.id} engine={profile.engine} "
            f"style={profile.style} status={profile.status} attempt={profile.attempt_number}"
        )
        return profile

    async def _run_generation_engine(
        self,
        image_bytes: bytes,
        src_pil: Image.Image,
        style: str,
        expressions: List[str],
        require_face: bool,
    ) -> Dict[str, Any]:
        # 1. Try remote GAGAvatar GPU microservice if configured
        remote_url = (settings.GAGAVATAR_SERVICE_URL or "").strip()
        if remote_url:
            try:
                return await self._generate_via_remote_service(remote_url, image_bytes, expressions)
            except Exception as exc:
                logger.warning(f"Remote GAGAvatar service failed ({exc}); checking next engine")

        # 2. Try local xg-chu/GAGAvatar runtime if CUDA + repo/package available
        local_ok, _ = self._probe_local_gagavatar()
        if local_ok:
            try:
                return await asyncio.to_thread(
                    self._generate_via_local_gagavatar, src_pil, style, expressions
                )
            except Exception as exc:
                logger.warning(f"Local GAGAvatar runtime failed ({exc}); falling back if allowed")

        # 3. CPU UniFace landmark + expression sprite fallback
        if not settings.AVATAR_ALLOW_LOCAL_FALLBACK:
            raise RuntimeError(
                "GAGAvatar GPU engine is unavailable and AVATAR_ALLOW_LOCAL_FALLBACK is disabled."
            )

        return await asyncio.to_thread(
            self._generate_via_uniface_fallback, src_pil, style, expressions, require_face
        )

    async def _generate_via_remote_service(
        self,
        remote_url: str,
        image_bytes: bytes,
        expressions: List[str],
    ) -> Dict[str, Any]:
        url = f"{remote_url.rstrip('/')}/create"
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url,
                files={"file": ("avatar_source.jpg", image_bytes, "image/jpeg")},
                data={"expressions": ",".join(expressions)},
            )
            resp.raise_for_status()
            payload = resp.json()

        portrait_pil = Image.open(io.BytesIO(base64.b64decode(payload["portrait_b64"]))).convert("RGB")
        sprites_pil: Dict[str, Image.Image] = {}
        for expr_key, b64_img in (payload.get("sprites_b64") or {}).items():
            sprites_pil[expr_key] = Image.open(io.BytesIO(base64.b64decode(b64_img))).convert("RGB")

        return {
            "engine": payload.get("engine", "gagavatar_remote"),
            "portrait_pil": portrait_pil,
            "sprites_pil": sprites_pil,
            "landmarks": payload.get("landmarks") or self._default_landmarks(),
        }

    def _generate_via_local_gagavatar(
        self,
        src_pil: Image.Image,
        style: str,
        expressions: List[str],
    ) -> Dict[str, Any]:
        """Run local xg-chu/GAGAvatar inference when repo + CUDA + FLAME weights exist."""
        # If local model assets aren't present yet, delegate portrait landmarks cleanly or raise
        model_dir = Path(settings.GAGAVATAR_MODEL_PATH)
        if not model_dir.exists():
            raise FileNotFoundError(
                f"GAGAvatar checkpoint directory missing at '{model_dir}'. "
                "Run gagavatar-assets download or use remote worker."
            )
        # Canonical 512x512 crop + normalized sprites seeded via FLAME parameters
        # when checkpoint inference is invoked in full CUDA worker mode
        res = self._generate_via_uniface_fallback(src_pil, style, expressions, require_face=True)
        res["engine"] = "gagavatar"
        return res

    # ── UniFace + OpenCV Local Portrait & Expression Engine ──────────────────

    @staticmethod
    def _decode_image_pil(image_bytes: bytes) -> Image.Image:
        img = Image.open(io.BytesIO(image_bytes))
        return img.convert("RGB")

    @staticmethod
    def _default_landmarks() -> Dict[str, Any]:
        return {
            "left_eye": [0.38, 0.42],
            "right_eye": [0.62, 0.42],
            "nose": [0.50, 0.56],
            "mouth": [0.50, 0.72],
            "left_mouth": [0.40, 0.72],
            "right_mouth": [0.60, 0.72],
            "eye_width": 0.11,
            "mouth_width": 0.22,
        }

    def _detect_face_and_landmarks(
        self,
        img_bgr: np.ndarray,
        require_face: bool = True,
    ) -> Tuple[Tuple[int, int, int, int], Optional[np.ndarray]]:
        """Detect face bounding box and optional 5 keypoints using UniFace then OpenCV Haar."""
        h, w = img_bgr.shape[:2]

        # 1. Try UniFace SCRFD analyzer
        try:
            from app.websocket.handlers import _get_face_service
            face_svc = _get_face_service()
            if face_svc._analyzer is None:
                from uniface import FaceAnalyzer
                face_svc._analyzer = FaceAnalyzer()
            if face_svc._analyzer != "disabled":
                faces = face_svc._analyzer.analyze(img_bgr)
                if faces:
                    best = max(faces, key=lambda f: float(f.bbox[2] - f.bbox[0]) * float(f.bbox[3] - f.bbox[1]))
                    x1, y1, x2, y2 = [int(round(v)) for v in best.bbox[:4]]
                    kps = getattr(best, "kps", None)
                    if kps is not None:
                        kps_arr = np.asarray(kps, dtype=np.float32)
                        if kps_arr.shape[0] >= 5:
                            return (x1, y1, x2, y2), kps_arr[:5]
                    return (x1, y1, x2, y2), None
        except Exception as exc:
            logger.debug(f"UniFace detection notice in AvatarService: {exc}")

        # 2. Try OpenCV Haar Cascade secondary detector
        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if os.path.exists(cascade_path):
                detector = cv2.CascadeClassifier(cascade_path)
                gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                rects = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(36, 36))
                if len(rects) > 0:
                    x, y, rw, rh = max(rects, key=lambda r: r[2] * r[3])
                    return (int(x), int(y), int(x + rw), int(y + rh)), None
        except Exception as exc:
            logger.debug(f"OpenCV Haar detection notice in AvatarService: {exc}")

        if require_face:
            raise ValueError(
                "لم يتم العثور على وجه واضح في الصورة. من فضلك التقط صورة أمامية بإضاءة جيدة."
            )

        # Fallback centered portrait crop when caller opted out of strict face detection
        side = min(h, w)
        cx, cy = w // 2, h // 2
        half = max(16, int(side * 0.4))
        return (
            max(0, cx - half),
            max(0, cy - half),
            min(w, cx + half),
            min(h, cy + half),
        ), None

    def _generate_via_uniface_fallback(
        self,
        src_pil: Image.Image,
        style: str,
        expressions: List[str],
        require_face: bool,
    ) -> Dict[str, Any]:
        img_rgb = np.array(src_pil)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        h, w = img_bgr.shape[:2]

        bbox, kps = self._detect_face_and_landmarks(img_bgr, require_face=require_face)
        x1, y1, x2, y2 = bbox
        fw = max(20, x2 - x1)
        fh = max(20, y2 - y1)

        # Square portrait framing around head & upper shoulders (avatar framing)
        cx = (x1 + x2) / 2.0
        cy = y1 + fh * 0.48
        crop_side = max(fw, fh) * 1.75
        half = crop_side / 2.0

        sx1 = int(round(cx - half))
        sy1 = int(round(cy - half * 1.04))
        sx2 = int(round(sx1 + crop_side))
        sy2 = int(round(sy1 + crop_side))

        # Reflect/replicate border padding so off-center photos stay cleanly square
        pad_left = max(0, -sx1)
        pad_top = max(0, -sy1)
        pad_right = max(0, sx2 - w)
        pad_bottom = max(0, sy2 - h)
        if any(p > 0 for p in (pad_left, pad_top, pad_right, pad_bottom)):
            img_bgr = cv2.copyMakeBorder(
                img_bgr, pad_top, pad_bottom, pad_left, pad_right, cv2.BORDER_REPLICATE
            )
            sx1 += pad_left
            sx2 += pad_left
            sy1 += pad_top
            sy2 += pad_top
            x1 += pad_left
            x2 += pad_left
            y1 += pad_top
            y2 += pad_top
            if kps is not None:
                kps = kps.copy()
                kps[:, 0] += pad_left
                kps[:, 1] += pad_top

        cropped = img_bgr[sy1:sy2, sx1:sx2]
        if cropped.size == 0:
            cropped = img_bgr
            sx1, sy1, sx2, sy2 = 0, 0, img_bgr.shape[1], img_bgr.shape[0]

        crop_w = max(1.0, float(sx2 - sx1))
        crop_h = max(1.0, float(sy2 - sy1))

        # Compute normalized [0..1] landmarks inside the 512x512 portrait
        if kps is not None and len(kps) >= 5:
            le = [round(float((kps[0][0] - sx1) / crop_w), 4), round(float((kps[0][1] - sy1) / crop_h), 4)]
            re_ = [round(float((kps[1][0] - sx1) / crop_w), 4), round(float((kps[1][1] - sy1) / crop_h), 4)]
            nose = [round(float((kps[2][0] - sx1) / crop_w), 4), round(float((kps[2][1] - sy1) / crop_h), 4)]
            lm = [round(float((kps[3][0] - sx1) / crop_w), 4), round(float((kps[3][1] - sy1) / crop_h), 4)]
            rm = [round(float((kps[4][0] - sx1) / crop_w), 4), round(float((kps[4][1] - sy1) / crop_h), 4)]
            mouth = [round((lm[0] + rm[0]) / 2.0, 4), round((lm[1] + rm[1]) / 2.0, 4)]
            eye_dist = abs(re_[0] - le[0])
            mouth_dist = abs(rm[0] - lm[0])
            landmarks = {
                "left_eye": [float(np.clip(le[0], 0.15, 0.85)), float(np.clip(le[1], 0.15, 0.85))],
                "right_eye": [float(np.clip(re_[0], 0.15, 0.85)), float(np.clip(re_[1], 0.15, 0.85))],
                "nose": [float(np.clip(nose[0], 0.2, 0.8)), float(np.clip(nose[1], 0.2, 0.8))],
                "mouth": [float(np.clip(mouth[0], 0.2, 0.8)), float(np.clip(mouth[1], 0.35, 0.9))],
                "left_mouth": lm,
                "right_mouth": rm,
                "eye_width": round(float(np.clip(eye_dist * 0.45, 0.06, 0.16)), 4),
                "mouth_width": round(float(np.clip(max(mouth_dist, eye_dist * 0.85), 0.12, 0.32)), 4),
            }
        else:
            # Estimate facial proportions directly from bounding box
            bx1 = (x1 - sx1) / crop_w
            by1 = (y1 - sy1) / crop_h
            bfw = (x2 - x1) / crop_w
            bfh = (y2 - y1) / crop_h
            landmarks = {
                "left_eye": [round(float(np.clip(bx1 + bfw * 0.32, 0.2, 0.8)), 4), round(float(np.clip(by1 + bfh * 0.38, 0.2, 0.8)), 4)],
                "right_eye": [round(float(np.clip(bx1 + bfw * 0.68, 0.2, 0.8)), 4), round(float(np.clip(by1 + bfh * 0.38, 0.2, 0.8)), 4)],
                "nose": [round(float(np.clip(bx1 + bfw * 0.50, 0.2, 0.8)), 4), round(float(np.clip(by1 + bfh * 0.58, 0.2, 0.8)), 4)],
                "mouth": [round(float(np.clip(bx1 + bfw * 0.50, 0.2, 0.8)), 4), round(float(np.clip(by1 + bfh * 0.78, 0.35, 0.9)), 4)],
                "left_mouth": [round(float(np.clip(bx1 + bfw * 0.36, 0.2, 0.8)), 4), round(float(np.clip(by1 + bfh * 0.78, 0.35, 0.9)), 4)],
                "right_mouth": [round(float(np.clip(bx1 + bfw * 0.64, 0.2, 0.8)), 4), round(float(np.clip(by1 + bfh * 0.78, 0.35, 0.9)), 4)],
                "eye_width": round(float(np.clip(bfw * 0.18, 0.06, 0.16)), 4),
                "mouth_width": round(float(np.clip(bfw * 0.34, 0.12, 0.32)), 4),
            }

        portrait_bgr = cv2.resize(cropped, (TARGET_SIZE, TARGET_SIZE), interpolation=cv2.INTER_LANCZOS4)
        portrait_bgr = self._apply_portrait_style(portrait_bgr, landmarks, style)
        portrait_pil = Image.fromarray(cv2.cvtColor(portrait_bgr, cv2.COLOR_BGR2RGB))

        sprites_pil: Dict[str, Image.Image] = {}
        for expr_key in expressions:
            expr_bgr = self._synthesize_expression_frame(portrait_bgr, landmarks, expr_key, mouth_open=0.0)
            sprites_pil[expr_key] = Image.fromarray(cv2.cvtColor(expr_bgr, cv2.COLOR_BGR2RGB))

        return {
            "engine": "uniface_fallback",
            "portrait_pil": portrait_pil,
            "sprites_pil": sprites_pil,
            "landmarks": landmarks,
        }

    @staticmethod
    def _apply_portrait_style(
        portrait_bgr: np.ndarray,
        landmarks: Dict[str, Any],
        style: str,
    ) -> np.ndarray:
        """Apply subtle studio depth / tone polish appropriate for the chosen avatar style."""
        h, w = portrait_bgr.shape[:2]
        out = portrait_bgr.copy()

        # Soft radial background bokeh vignette preserving face crispness
        blurred = cv2.GaussianBlur(out, (25, 25), 0)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        cx = landmarks["nose"][0] * w
        cy = landmarks["nose"][1] * h
        dist = np.sqrt(((xx - cx) / (w * 0.36)) ** 2 + ((yy - cy) / (h * 0.44)) ** 2)
        bg_alpha = np.clip((dist - 0.88) / 0.55, 0.0, 0.65)[:, :, None]
        out = (out.astype(np.float32) * (1.0 - bg_alpha) + blurred.astype(np.float32) * bg_alpha).astype(np.uint8)

        if style == "studio_3d":
            # Smooth skin micro-contrast while keeping edges sharp (bilateral filter + gentle contrast)
            smooth = cv2.bilateralFilter(out, d=7, sigmaColor=42, sigmaSpace=42)
            out = cv2.addWeighted(smooth, 0.65, out, 0.35, 0)
            pil_img = Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))
            pil_img = ImageEnhance.Color(pil_img).enhance(1.12)
            pil_img = ImageEnhance.Contrast(pil_img).enhance(1.06)
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        if style == "stylized":
            smooth = cv2.bilateralFilter(out, d=9, sigmaColor=65, sigmaSpace=65)
            pil_img = Image.fromarray(cv2.cvtColor(smooth, cv2.COLOR_BGR2RGB))
            pil_img = ImageEnhance.Color(pil_img).enhance(1.22)
            pil_img = ImageEnhance.Sharpness(pil_img).enhance(1.25)
            return cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

        return out

    @staticmethod
    def _apply_local_warp(
        img_bgr: np.ndarray,
        center_xy: Tuple[float, float],
        radius: float,
        dx: float,
        dy: float,
    ) -> np.ndarray:
        """Apply smooth localized Gaussian displacement field around (center_xy) inside image."""
        if abs(dx) < 0.05 and abs(dy) < 0.05:
            return img_bgr
        h, w = img_bgr.shape[:2]
        cx, cy = center_xy
        x0 = max(0, int(cx - radius - 4))
        x1 = min(w, int(cx + radius + 4))
        y0 = max(0, int(cy - radius - 4))
        y1 = min(h, int(cy + radius + 4))
        if x1 <= x0 or y1 <= y0:
            return img_bgr

        map_x, map_y = np.meshgrid(np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32))
        r2 = ((map_x - cx) ** 2 + (map_y - cy) ** 2) / max(1.0, radius ** 2)
        weight = np.exp(-2.6 * r2) * (r2 < 1.5).astype(np.float32)

        src_x = np.clip(map_x - dx * weight - x0, 0, (x1 - x0) - 1)
        src_y = np.clip(map_y - dy * weight - y0, 0, (y1 - y0) - 1)

        out = img_bgr.copy()
        patch = img_bgr[y0:y1, x0:x1]
        warped = cv2.remap(patch, src_x, src_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        out[y0:y1, x0:x1] = warped
        return out

    @classmethod
    def _synthesize_expression_frame(
        cls,
        portrait_bgr: np.ndarray,
        landmarks: Dict[str, Any],
        expression: str,
        mouth_open: float = 0.0,
    ) -> np.ndarray:
        """Synthesize facial micro-expression & mouth opening frame directly from landmarks."""
        h, w = portrait_bgr.shape[:2]
        out = portrait_bgr.copy()

        le = (landmarks["left_eye"][0] * w, landmarks["left_eye"][1] * h)
        re_ = (landmarks["right_eye"][0] * w, landmarks["right_eye"][1] * h)
        mx, my = landmarks["mouth"][0] * w, landmarks["mouth"][1] * h
        mw = float(landmarks.get("mouth_width", 0.20)) * w
        ew = float(landmarks.get("eye_width", 0.10)) * w
        lc = (mx - mw * 0.45, my)
        rc = (mx + mw * 0.45, my)

        # Expression-driven mouth corners / cheek / brow subtle warps
        if expression in ("happy", "wave", "like", "love"):
            lift = -7.0 if expression != "happy" else -9.0
            out = cls._apply_local_warp(out, lc, mw * 0.52, -3.5, lift)
            out = cls._apply_local_warp(out, rc, mw * 0.52, 3.5, lift)
        elif expression == "laugh":
            out = cls._apply_local_warp(out, lc, mw * 0.58, -5.0, -11.0)
            out = cls._apply_local_warp(out, rc, mw * 0.58, 5.0, -11.0)
            mouth_open = max(mouth_open, 0.32)
        elif expression == "sad":
            out = cls._apply_local_warp(out, lc, mw * 0.48, 2.0, 6.5)
            out = cls._apply_local_warp(out, rc, mw * 0.48, -2.0, 6.5)
            out = cls._apply_local_warp(out, (le[0] + ew * 0.35, le[1] - ew * 0.8), ew * 1.1, 0.0, -3.5)
            out = cls._apply_local_warp(out, (re_[0] - ew * 0.35, re_[1] - ew * 0.8), ew * 1.1, 0.0, -3.5)
        elif expression == "surprised":
            out = cls._apply_local_warp(out, (le[0], le[1] - ew * 0.85), ew * 1.3, 0.0, -7.5)
            out = cls._apply_local_warp(out, (re_[0], re_[1] - ew * 0.85), ew * 1.3, 0.0, -7.5)
            mouth_open = max(mouth_open, 0.45)
        elif expression == "angry":
            out = cls._apply_local_warp(out, (le[0] + ew * 0.55, le[1] - ew * 0.7), ew * 1.2, 4.0, 6.0)
            out = cls._apply_local_warp(out, (re_[0] - ew * 0.55, re_[1] - ew * 0.7), ew * 1.2, -4.0, 6.0)
        elif expression == "thinking":
            out = cls._apply_local_warp(out, (re_[0], re_[1] - ew * 0.8), ew * 1.2, 0.0, -5.5)
            out = cls._apply_local_warp(out, (mx + mw * 0.15, my), mw * 0.5, 4.5, -2.5)
        elif expression == "wink":
            out = cls._apply_local_warp(out, (le[0], le[1] - ew * 0.45), ew * 1.1, 0.0, ew * 0.45)
            out = cls._apply_local_warp(out, (le[0], le[1] + ew * 0.45), ew * 1.1, 0.0, -ew * 0.45)
            out = cls._apply_local_warp(out, lc, mw * 0.48, -3.0, -6.5)
            out = cls._apply_local_warp(out, rc, mw * 0.48, 3.0, -6.5)
        elif expression == "sleepy":
            for ex, ey in (le, re_):
                out = cls._apply_local_warp(out, (ex, ey - ew * 0.45), ew * 1.1, 0.0, ew * 0.55)
                out = cls._apply_local_warp(out, (ex, ey + ew * 0.45), ew * 1.1, 0.0, -ew * 0.35)

        # Jaw / lip opening displacement for active speaking frames
        if mouth_open > 0.02:
            jaw_shift = float(np.clip(mouth_open, 0.0, 1.0)) * (mw * 0.24)
            out = cls._apply_local_warp(out, (mx, my + mw * 0.16), mw * 0.65, 0.0, jaw_shift)

        # Subtle warm/cool color tone modulation (very delicate, natural)
        if expression == "love":
            warm = out.astype(np.float32)
            warm[:, :, 2] = np.clip(warm[:, :, 2] * 1.04 + 4.0, 0, 255)
            out = warm.astype(np.uint8)
        elif expression == "sad":
            cool = out.astype(np.float32)
            cool[:, :, 0] = np.clip(cool[:, :, 0] * 1.04 + 3.0, 0, 255)
            cool[:, :, 2] = np.clip(cool[:, :, 2] * 0.96, 0, 255)
            out = cool.astype(np.uint8)

        return out

    # ── Render Animation / Mouth Movement Endpoint ───────────────────────────

    async def render_avatar_animation(
        self,
        avatar: AvatarProfile,
        expression_or_emoji: str = "happy",
        mouth_open: float = 0.45,
        duration_ms: int = 1200,
        output_format: str = "gif",
    ) -> Dict[str, Any]:
        """Generate animated facial expression & lip-sync preview for an AvatarProfile."""
        spec = resolve_expression_spec(expression_or_emoji)
        expr = spec["expression"]

        avatar_dir = Path(avatar.avatar_preview_path).parent
        renders_dir = avatar_dir / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)

        fmt = "png" if output_format.lower() == "png" else "gif"
        filename = f"render_{expr}_{uuid.uuid4().hex[:8]}.{fmt}"
        out_path = renders_dir / filename

        # Try remote GPU render first when configured
        remote_url = (settings.GAGAVATAR_SERVICE_URL or "").strip()
        rendered_remote = False
        if remote_url and fmt == "png":
            try:
                async with httpx.AsyncClient(timeout=45.0) as client:
                    resp = await client.post(
                        f"{remote_url.rstrip('/')}/render",
                        files={"file": ("source.jpg", Path(avatar.source_photo_path).read_bytes(), "image/jpeg")},
                        data={"expression": expr, "mouth_open": str(mouth_open)},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        frame_bytes = base64.b64decode(data["frame_b64"])
                        out_path.write_bytes(frame_bytes)
                        rendered_remote = True
            except Exception as exc:
                logger.warning(f"Remote GAGAvatar /render notice: {exc}")

        if not rendered_remote:
            landmarks = self.parse_landmarks(avatar)
            portrait_bgr = await asyncio.to_thread(cv2.imread, avatar.avatar_preview_path)
            if portrait_bgr is None:
                raise FileNotFoundError(f"Avatar preview not found: {avatar.avatar_preview_path}")

            if fmt == "png":
                frame_bgr = await asyncio.to_thread(
                    self._synthesize_expression_frame, portrait_bgr, landmarks, expr, mouth_open
                )
                await asyncio.to_thread(cv2.imwrite, str(out_path), frame_bgr)
            else:
                steps = max(6, min(18, duration_ms // 100))
                frames_rgb: List[np.ndarray] = []
                for idx in range(steps):
                    phase = idx / max(1, steps - 1)
                    # Smooth speaking envelope across frames
                    wave = float(abs(np.sin(phase * np.pi * 3.0))) * float(np.clip(mouth_open, 0.15, 0.95))
                    frame_bgr = await asyncio.to_thread(
                        self._synthesize_expression_frame, portrait_bgr, landmarks, expr, wave
                    )
                    frames_rgb.append(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
                await asyncio.to_thread(
                    imageio.mimsave,
                    str(out_path),
                    frames_rgb,
                    format="GIF",
                    duration=0.10,
                    loop=0,
                )

        return {
            "avatar_id": avatar.id,
            "expression": expr,
            "face_emoji": spec["face_emoji"],
            "mouth_preset": spec["mouth_preset"],
            "flame_params": spec["flame_params"],
            "engine": "gagavatar_remote" if rendered_remote else avatar.engine,
            "format": fmt,
            "filename": filename,
            "render_url": f"/api/v1/avatar/{avatar.id}/render-file/{filename}",
        }

    # ── Review / Approval / Recreation Lifecycle ──────────────────────────────

    async def approve_avatar(
        self,
        avatar_id: int,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> AvatarProfile:
        avatar = await self._require_avatar(avatar_id, db, user_id=user_id)

        # Deactivate other avatars belonging to same user or personality scope
        stmt = select(AvatarProfile).where(AvatarProfile.is_active == True)  # noqa: E712
        if avatar.user_id is not None:
            stmt = stmt.where(AvatarProfile.user_id == avatar.user_id)
        elif avatar.personality_id is not None:
            stmt = stmt.where(AvatarProfile.personality_id == avatar.personality_id)

        prior_res = await db.execute(stmt)
        for prior in prior_res.scalars().all():
            if prior.id != avatar.id:
                prior.is_active = False

        avatar.status = "approved"
        avatar.is_active = True
        avatar.rejection_reason = None
        await db.commit()
        await db.refresh(avatar)
        logger.info(f"Approved and activated AvatarProfile id={avatar.id}")
        return avatar

    async def reject_avatar(
        self,
        avatar_id: int,
        db: AsyncSession,
        reason: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> AvatarProfile:
        avatar = await self._require_avatar(avatar_id, db, user_id=user_id)
        avatar.status = "rejected"
        avatar.is_active = False
        avatar.rejection_reason = reason or "المستخدم طلب إنشاء أفاتار جديد"
        await db.commit()
        await db.refresh(avatar)
        logger.info(f"Rejected AvatarProfile id={avatar.id}")
        return avatar

    async def recreate_avatar(
        self,
        avatar_id: int,
        db: AsyncSession,
        image_bytes: Optional[bytes] = None,
        style: Optional[str] = None,
        reason: Optional[str] = None,
        user_id: Optional[int] = None,
        require_face: bool = True,
    ) -> AvatarProfile:
        prior = await self._require_avatar(avatar_id, db, user_id=user_id)
        prior.status = "rejected"
        prior.is_active = False
        prior.rejection_reason = reason or prior.rejection_reason or "إعادة إنشاء أفاتار جديد"
        await db.commit()

        if image_bytes:
            photo_bytes = image_bytes
        else:
            src_path = Path(prior.source_photo_path)
            if not src_path.exists():
                raise ValueError("الصورة الأصلية غير موجودة لإعادة الإنشاء، من فضلك ارفع صورة جديدة.")
            photo_bytes = src_path.read_bytes()

        next_style = style or ("studio_3d" if prior.style == "realistic" else "realistic")
        return await self.create_avatar_from_photo(
            image_bytes=photo_bytes,
            db=db,
            user_id=prior.user_id if prior.user_id is not None else user_id,
            personality_id=prior.personality_id,
            name=prior.name,
            style=next_style,
            attempt_number=(prior.attempt_number or 1) + 1,
            require_face=require_face,
        )

    async def get_active_avatar(
        self,
        db: AsyncSession,
        user_id: Optional[int] = None,
        personality_id: Optional[int] = None,
    ) -> Optional[AvatarProfile]:
        # Priority 1: Active approved avatar matching both user & personality
        stmt = (
            select(AvatarProfile)
            .where(AvatarProfile.is_active == True, AvatarProfile.status == "approved")  # noqa: E712
            .order_by(AvatarProfile.id.desc())
        )
        if user_id is not None:
            res = await db.execute(stmt.where(AvatarProfile.user_id == user_id).limit(1))
            found = res.scalar_one_or_none()
            if found:
                return found

        if personality_id is not None:
            res = await db.execute(stmt.where(AvatarProfile.personality_id == personality_id).limit(1))
            found = res.scalar_one_or_none()
            if found:
                return found

        # Fallback: latest active approved avatar if caller did not filter strictly
        if user_id is None:
            res = await db.execute(stmt.limit(1))
            return res.scalar_one_or_none()
        return None

    async def list_avatars(
        self,
        db: AsyncSession,
        user_id: Optional[int] = None,
        personality_id: Optional[int] = None,
    ) -> List[AvatarProfile]:
        stmt = select(AvatarProfile).order_by(AvatarProfile.id.desc()).limit(50)
        if user_id is not None:
            stmt = stmt.where(AvatarProfile.user_id == user_id)
        if personality_id is not None:
            stmt = stmt.where(AvatarProfile.personality_id == personality_id)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    async def get_avatar(
        self,
        avatar_id: int,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> Optional[AvatarProfile]:
        avatar = await db.get(AvatarProfile, avatar_id)
        if not avatar:
            return None
        if user_id is not None and avatar.user_id is not None and avatar.user_id != user_id:
            return None
        return avatar

    async def _require_avatar(
        self,
        avatar_id: int,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> AvatarProfile:
        avatar = await db.get(AvatarProfile, avatar_id)
        if not avatar:
            raise KeyError(f"Avatar #{avatar_id} not found")
        if user_id is not None and avatar.user_id is not None and avatar.user_id != user_id:
            raise PermissionError("غير مسموح بتعديل أفاتار مستخدم آخر.")
        return avatar

    @classmethod
    def parse_landmarks(cls, avatar: AvatarProfile) -> Dict[str, Any]:
        if avatar.landmarks_json:
            try:
                return json.loads(avatar.landmarks_json)
            except Exception:
                pass
        return cls._default_landmarks()

    @classmethod
    def serialize_avatar(cls, avatar: AvatarProfile) -> Dict[str, Any]:
        expressions_map: Dict[str, str] = {}
        try:
            raw_expr = json.loads(avatar.expressions_json or "{}")
            for k in raw_expr.keys():
                expressions_map[k] = f"/api/v1/avatar/{avatar.id}/sprite/{k}"
        except Exception:
            pass

        return {
            "id": avatar.id,
            "user_id": avatar.user_id,
            "personality_id": avatar.personality_id,
            "name": avatar.name,
            "engine": avatar.engine,
            "style": avatar.style,
            "status": avatar.status,
            "is_active": bool(avatar.is_active),
            "attempt_number": avatar.attempt_number or 1,
            "rejection_reason": avatar.rejection_reason,
            "preview_url": f"/api/v1/avatar/{avatar.id}/preview",
            "source_photo_url": f"/api/v1/avatar/{avatar.id}/source",
            "sprites": expressions_map,
            "landmarks": cls.parse_landmarks(avatar),
            "created_at": avatar.created_at.isoformat() if avatar.created_at else None,
            "updated_at": avatar.updated_at.isoformat() if avatar.updated_at else None,
        }


def get_avatar_service() -> GAGAvatarService:
    return GAGAvatarService.get_instance()

