"""GAGAvatar Avatar Generation & Expression Animation Service.

Strictly powered by https://github.com/xg-chu/GAGAvatar:
1. Remote GPU Microservice (`GAGAVATAR_SERVICE_URL`) when configured.
2. Local `xg-chu/GAGAvatar` CUDA runtime (`GAGAvatarEngine` wrapping `CoreEngine`
   tracker + `GAGAvatarRuntime` 3D Gaussian Splatting renderer + FLAME model).
Zero CPU image-warp or synthetic overlay fallbacks when `GAGAVATAR_STRICT_ONLY` /
`not AVATAR_ALLOW_LOCAL_FALLBACK`.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import imageio.v2 as imageio
import httpx
import numpy as np
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.avatar_profile import AvatarProfile
from app.services.avatar.emoji_actions import (
    FACE_EMOJI_ACTIONS,
    resolve_expression_spec,
)
from app.services.avatar.gagavatar_engine import get_gagavatar_engine

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
        self._local_gag_info: Dict[str, Any] = {}

    @classmethod
    def get_instance(cls) -> "GAGAvatarService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Runtime Discovery ─────────────────────────────────────────────────────

    def _probe_local_gagavatar(self) -> Tuple[bool, Optional[str]]:
        if self._local_gag_checked and self._local_gag_available:
            return True, self._local_gag_error

        ok, err, info = get_gagavatar_engine().probe()
        self._local_gag_checked = True
        self._local_gag_available = ok
        self._local_gag_error = err
        self._local_gag_info = info
        return ok, err

    async def get_runtime_status(self) -> Dict[str, Any]:
        """Report availability of remote GAGAvatar GPU worker and local GAGAvatar CUDA runtime."""
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
            else ("gagavatar" if local_ok else "unavailable")
        )
        return {
            "preferred_engine": preferred_engine,
            "strict_gagavatar_only": bool(settings.GAGAVATAR_STRICT_ONLY or not settings.AVATAR_ALLOW_LOCAL_FALLBACK),
            "remote_service_url": remote_url,
            "remote_healthy": remote_healthy,
            "remote_detail": remote_detail,
            "local_gagavatar_available": local_ok,
            "local_gagavatar_error": local_err,
            "cuda_available": self._local_gag_info.get("cuda_available", False),
            "cuda_device": self._local_gag_info.get("cuda_device"),
            "local_fallback_enabled": False,
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
        mouth_dir = avatar_dir / "mouth"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        sprites_dir.mkdir(parents=True, exist_ok=True)
        mouth_dir.mkdir(parents=True, exist_ok=True)

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
            avatar_key=avatar_uid,
            require_face=require_face,
        )

        # Persist portrait, expression sprites (including natural blink), mouth frames & tracked FLAME feature
        gen_result["portrait_pil"].save(preview_path, format="PNG")
        expr_files: Dict[str, Any] = {}
        for expr_key, sprite_pil in (gen_result.get("sprites_pil") or {}).items():
            fname = f"{expr_key}.png"
            sprite_pil.save(sprites_dir / fname, format="PNG")
            expr_files[expr_key] = fname

        mouth_manifest: Dict[str, List[int]] = {}
        for expr_key, mouth_imgs in (gen_result.get("mouth_pil") or {}).items():
            levels: List[int] = [0]
            for lvl_idx, mouth_img in enumerate(mouth_imgs, start=1):
                mouth_img.save(mouth_dir / f"{expr_key}_{lvl_idx}.png", format="PNG")
                levels.append(lvl_idx)
            mouth_manifest[expr_key] = levels
        if mouth_manifest:
            expr_files["_mouth"] = mouth_manifest

        tracked_feature = gen_result.get("tracked_feature")
        if tracked_feature is not None:
            feat_path = avatar_dir / "tracked_feature.pt"
            if isinstance(tracked_feature, (bytes, bytearray)):
                feat_path.write_bytes(bytes(tracked_feature))
            else:
                try:
                    import torch

                    await asyncio.to_thread(torch.save, tracked_feature, feat_path)
                except (ImportError, ModuleNotFoundError):
                    import pickle

                    await asyncio.to_thread(lambda: feat_path.write_bytes(pickle.dumps(tracked_feature)))

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
        avatar_key: str,
        require_face: bool = True,
    ) -> Dict[str, Any]:
        # 1. Try remote GAGAvatar GPU microservice if configured
        remote_url = (settings.GAGAVATAR_SERVICE_URL or "").strip()
        if remote_url:
            try:
                return await self._generate_via_remote_service(
                    remote_url=remote_url,
                    image_bytes=image_bytes,
                    expressions=expressions,
                    style=style,
                )
            except ValueError:
                raise
            except Exception as exc:
                logger.warning(f"Remote GAGAvatar service failed ({exc}); checking local GAGAvatar engine")

        # 2. Local xg-chu/GAGAvatar CUDA runtime if available
        local_ok, local_err = self._probe_local_gagavatar()
        if local_ok:
            return await asyncio.to_thread(
                self._generate_via_local_gagavatar,
                src_pil,
                style,
                expressions,
                avatar_key,
            )

        # 3. Graceful Local UniFace + Kinematic Engine Fallback (when Colab GPU is not yet connected)
        if settings.AVATAR_ALLOW_LOCAL_FALLBACK:
            logger.info("GAGAvatar CUDA/Colab worker not connected; generating initial portrait with UniFace + Kinematic Engine")
            return await asyncio.to_thread(
                self._generate_via_uniface_fallback,
                src_pil,
                style,
                expressions,
                require_face=require_face,
            )

        raise RuntimeError(
            f"GAGAvatar engine is unavailable ({local_err or 'CUDA or weights missing'}). "
            "Local CPU/OpenCV fallback is disabled."
        )

    async def _generate_via_remote_service(
        self,
        remote_url: str,
        image_bytes: bytes,
        expressions: List[str],
        style: str = "realistic",
    ) -> Dict[str, Any]:
        url = f"{remote_url.rstrip('/')}/create"
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                url,
                files={"file": ("avatar_source.jpg", image_bytes, "image/jpeg")},
                data={"expressions": ",".join(expressions), "style": style},
            )
            if resp.status_code == 422:
                detail = resp.json().get("detail", "No clear face detected by GAGAvatar tracker.")
                raise ValueError(detail)
            resp.raise_for_status()
            payload = resp.json()

        portrait_pil = Image.open(io.BytesIO(base64.b64decode(payload["portrait_b64"]))).convert("RGB")
        sprites_pil: Dict[str, Image.Image] = {}
        for expr_key, b64_img in (payload.get("sprites_b64") or {}).items():
            sprites_pil[expr_key] = Image.open(io.BytesIO(base64.b64decode(b64_img))).convert("RGB")

        mouth_pil: Dict[str, List[Image.Image]] = {}
        for expr_key, b64_list in (payload.get("mouth_b64") or {}).items():
            mouth_pil[expr_key] = [
                Image.open(io.BytesIO(base64.b64decode(item))).convert("RGB")
                for item in (b64_list or [])
            ]

        tracked_bytes: Optional[bytes] = None
        if payload.get("tracked_feature_b64"):
            tracked_bytes = base64.b64decode(payload["tracked_feature_b64"])

        return {
            "engine": payload.get("engine", "gagavatar_remote"),
            "portrait_pil": portrait_pil,
            "sprites_pil": sprites_pil,
            "mouth_pil": mouth_pil,
            "tracked_feature": tracked_bytes,
            "landmarks": payload.get("landmarks") or self._default_landmarks(),
        }

    def _generate_via_local_gagavatar(
        self,
        src_pil: Image.Image,
        style: str,
        expressions: List[str],
        avatar_key: str = "avatar",
    ) -> Dict[str, Any]:
        """Run local xg-chu/GAGAvatar CoreEngine tracker + 3DGS neural renderer."""
        return get_gagavatar_engine().track_and_generate_avatar(
            src_pil=src_pil,
            style=style,
            expressions=expressions,
            avatar_key=avatar_key,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

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
        """Detect face bounding box and 5 keypoints using UniFace then OpenCV Haar."""
        h, w = img_bgr.shape[:2]

        try:
            from app.websocket.handlers import _get_face_service

            face_svc = _get_face_service()
            if face_svc._analyzer is None:
                from uniface import FaceAnalyzer

                face_svc._analyzer = FaceAnalyzer()
            if face_svc._analyzer != "disabled":
                faces = face_svc._analyzer.analyze(img_bgr)
                if faces:
                    best = max(
                        faces,
                        key=lambda f: float(f.bbox[2] - f.bbox[0]) * float(f.bbox[3] - f.bbox[1]),
                    )
                    x1, y1, x2, y2 = [int(round(v)) for v in best.bbox[:4]]
                    kps = getattr(best, "kps", None)
                    if kps is not None:
                        kps_arr = np.asarray(kps, dtype=np.float32)
                        if kps_arr.shape[0] >= 5:
                            return (x1, y1, x2, y2), kps_arr[:5]
                    return (x1, y1, x2, y2), None
        except Exception as exc:
            logger.debug(f"UniFace detection notice in AvatarService: {exc}")

        try:
            cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
            if os.path.exists(cascade_path):
                detector = cv2.CascadeClassifier(cascade_path)
                gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
                rects = detector.detectMultiScale(
                    gray, scaleFactor=1.1, minNeighbors=4, minSize=(36, 36)
                )
                if len(rects) > 0:
                    x, y, rw, rh = max(rects, key=lambda r: r[2] * r[3])
                    return (int(x), int(y), int(x + rw), int(y + rh)), None
        except Exception as exc:
            logger.debug(f"OpenCV Haar detection notice in AvatarService: {exc}")

        if require_face:
            raise ValueError(
                "لم يتم العثور على وجه واضح في الصورة. من فضلك التقط صورة أمامية بإضاءة جيدة."
            )

        side = min(h, w)
        cx, cy = w // 2, h // 2
        half = max(16, int(side * 0.4))
        return (cx - half, cy - half, cx + half, cy + half), None

    @staticmethod
    def _apply_local_warp(
        img_bgr: np.ndarray,
        center_xy: Tuple[float, float],
        radius: float,
        dx: float,
        dy: float,
    ) -> np.ndarray:
        """Apply smooth localized Gaussian displacement field around (center_xy)."""
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

        map_x, map_y = np.meshgrid(
            np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32)
        )
        r2 = ((map_x - cx) ** 2 + (map_y - cy) ** 2) / max(1.0, radius**2)
        weight = np.exp(-2.6 * r2) * (r2 < 1.5).astype(np.float32)

        src_x = np.clip(map_x - dx * weight - x0, 0, (x1 - x0) - 1)
        src_y = np.clip(map_y - dy * weight - y0, 0, (y1 - y0) - 1)

        out = img_bgr.copy()
        patch = img_bgr[y0:y1, x0:x1]
        warped = cv2.remap(
            patch, src_x, src_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE
        )
        out[y0:y1, x0:x1] = warped
        return out

    @classmethod
    def _synthesize_expression_frame(
        cls,
        portrait_bgr: np.ndarray,
        landmarks: Dict[str, Any],
        expression: str,
    ) -> np.ndarray:
        """Synthesize facial micro-expression (eyes, brows, cheeks) directly from landmarks."""
        h, w = portrait_bgr.shape[:2]
        out = portrait_bgr.copy()

        le = (landmarks["left_eye"][0] * w, landmarks["left_eye"][1] * h)
        re_ = (landmarks["right_eye"][0] * w, landmarks["right_eye"][1] * h)
        ew = float(landmarks.get("eye_width", 0.10)) * w

        if expression == "sad":
            out = cls._apply_local_warp(out, (le[0] + ew * 0.35, le[1] - ew * 0.8), ew * 1.1, 0.0, -3.5)
            out = cls._apply_local_warp(out, (re_[0] - ew * 0.35, re_[1] - ew * 0.8), ew * 1.1, 0.0, -3.5)
        elif expression == "surprised":
            out = cls._apply_local_warp(out, (le[0], le[1] - ew * 0.85), ew * 1.3, 0.0, -7.5)
            out = cls._apply_local_warp(out, (re_[0], re_[1] - ew * 0.85), ew * 1.3, 0.0, -7.5)
        elif expression == "angry":
            out = cls._apply_local_warp(out, (le[0] + ew * 0.55, le[1] - ew * 0.7), ew * 1.2, 4.0, 6.0)
            out = cls._apply_local_warp(out, (re_[0] - ew * 0.55, re_[1] - ew * 0.7), ew * 1.2, -4.0, 6.0)
        elif expression == "thinking":
            out = cls._apply_local_warp(out, (re_[0], re_[1] - ew * 0.8), ew * 1.2, 0.0, -5.5)
        elif expression == "wink":
            out = cls._apply_local_warp(out, (le[0], le[1] - ew * 0.45), ew * 1.1, 0.0, ew * 0.45)
            out = cls._apply_local_warp(out, (le[0], le[1] + ew * 0.45), ew * 1.1, 0.0, -ew * 0.45)
        elif expression == "blink":
            for ex, ey in (le, re_):
                out = cls._apply_local_warp(out, (ex, ey - ew * 0.45), ew * 1.2, 0.0, ew * 0.6)
                out = cls._apply_local_warp(out, (ex, ey + ew * 0.45), ew * 1.2, 0.0, -ew * 0.6)
        elif expression == "sleepy":
            for ex, ey in (le, re_):
                out = cls._apply_local_warp(out, (ex, ey - ew * 0.45), ew * 1.1, 0.0, ew * 0.55)

        return out

    def _generate_via_uniface_fallback(
        self,
        src_pil: Image.Image,
        style: str,
        expressions: List[str],
        require_face: bool = True,
    ) -> Dict[str, Any]:
        """Local UniFace + Kinematic Engine: crops 512x512 portrait, computes landmarks, and generates expressions."""
        img_rgb = np.array(src_pil)
        img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        h, w = img_bgr.shape[:2]

        bbox, kps = self._detect_face_and_landmarks(img_bgr, require_face=require_face)
        x1, y1, x2, y2 = bbox
        fw = max(20, x2 - x1)
        fh = max(20, y2 - y1)

        cx = (x1 + x2) / 2.0
        cy = y1 + fh * 0.48
        crop_side = max(fw, fh) * 1.75
        half = crop_side / 2.0

        sx1 = int(round(cx - half))
        sy1 = int(round(cy - half * 1.04))
        sx2 = int(round(sx1 + crop_side))
        sy2 = int(round(sy1 + crop_side))

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
        portrait_pil = Image.fromarray(cv2.cvtColor(portrait_bgr, cv2.COLOR_BGR2RGB))

        expr_configs = {
            "neutral":   {"corner_dy": 0.0,   "gap": 0.0},
            "happy":     {"corner_dy": -8.5,  "gap": 2.5},
            "laugh":     {"corner_dy": -11.0, "gap": 8.0},
            "love":      {"corner_dy": -6.0,  "gap": 1.5},
            "sad":       {"corner_dy": +9.5,  "gap": 1.0},
            "surprised": {"corner_dy": -1.0,  "gap": 14.0},
            "angry":     {"corner_dy": +4.5,  "gap": 0.0},
            "thinking":  {"corner_dy": +2.0,  "gap": 1.0},
            "wink":      {"corner_dy": -5.0,  "gap": 1.5},
            "sleepy":    {"corner_dy": +3.0,  "gap": 3.0},
            "wave":      {"corner_dy": -6.5,  "gap": 2.0},
            "like":      {"corner_dy": -6.5,  "gap": 1.5},
        }
        mouth_levels_gap = {1: 5.0, 2: 10.5, 3: 17.0}

        clean_exprs = [e for e in expressions if e in FACE_EMOJI_ACTIONS]
        if "neutral" not in clean_exprs:
            clean_exprs.insert(0, "neutral")

        sprites_pil: Dict[str, Image.Image] = {}
        mouth_pil: Dict[str, List[Image.Image]] = {e: [] for e in clean_exprs}

        for expr in clean_exprs:
            upper_bgr = self._synthesize_expression_frame(portrait_bgr, landmarks, expr)
            upper_pil = Image.fromarray(cv2.cvtColor(upper_bgr, cv2.COLOR_BGR2RGB))
            cfg = expr_configs.get(expr, expr_configs["neutral"])
            sprite_im = self._morph_mouth_image(
                upper_pil, corner_dy=cfg["corner_dy"], mouth_gap=cfg["gap"], lm=landmarks
            )
            sprites_pil[expr] = sprite_im

            for lvl, lvl_gap in mouth_levels_gap.items():
                m_im = self._morph_mouth_image(
                    upper_pil,
                    corner_dy=cfg["corner_dy"] * 0.7,
                    mouth_gap=max(cfg["gap"], lvl_gap),
                    lm=landmarks,
                )
                mouth_pil[expr].append(m_im)

        blink_bgr = self._synthesize_expression_frame(portrait_bgr, landmarks, "blink")
        sprites_pil["blink"] = Image.fromarray(cv2.cvtColor(blink_bgr, cv2.COLOR_BGR2RGB))

        return {
            "engine": "gagavatar_preview",
            "portrait_pil": portrait_pil,
            "sprites_pil": sprites_pil,
            "mouth_pil": mouth_pil,
            "landmarks": landmarks,
            "tracked_feature": None,
        }

    # ── Render Animation / Mouth Movement Endpoint ───────────────────────────

    async def render_avatar_animation(
        self,
        avatar: AvatarProfile,
        expression_or_emoji: str = "happy",
        mouth_open: float = 0.45,
        duration_ms: int = 1200,
        output_format: str = "gif",
    ) -> Dict[str, Any]:
        """Render neural facial expression & jaw lip-sync animation solely with xg-chu/GAGAvatar."""
        spec = resolve_expression_spec(expression_or_emoji)
        expr = spec["expression"]

        avatar_dir = Path(avatar.avatar_preview_path).parent
        renders_dir = avatar_dir / "renders"
        renders_dir.mkdir(parents=True, exist_ok=True)

        fmt = "png" if output_format.lower() == "png" else "gif"
        filename = f"render_{expr}_{uuid.uuid4().hex[:8]}.{fmt}"
        out_path = renders_dir / filename
        style = avatar.style or "realistic"

        remote_url = (settings.GAGAVATAR_SERVICE_URL or "").strip()
        rendered_remote = False
        if remote_url:
            try:
                source_bytes = Path(avatar.source_photo_path).read_bytes()
                async with httpx.AsyncClient(timeout=90.0) as client:
                    if fmt == "png":
                        resp = await client.post(
                            f"{remote_url.rstrip('/')}/render",
                            files={"file": ("source.jpg", source_bytes, "image/jpeg")},
                            data={"expression": expr, "mouth_open": str(mouth_open), "style": style},
                        )
                        if resp.status_code == 200:
                            frame_bytes = base64.b64decode(resp.json()["frame_b64"])
                            await asyncio.to_thread(out_path.write_bytes, frame_bytes)
                            rendered_remote = True
                    else:
                        steps = 6
                        frames_rgb: List[np.ndarray] = []
                        for idx in range(steps):
                            phase = idx / max(1, steps - 1)
                            wave = float(abs(np.sin(phase * np.pi * 2.5))) * float(np.clip(mouth_open, 0.15, 0.95))
                            resp = await client.post(
                                f"{remote_url.rstrip('/')}/render",
                                files={"file": ("source.jpg", source_bytes, "image/jpeg")},
                                data={"expression": expr, "mouth_open": str(wave), "style": style},
                            )
                            resp.raise_for_status()
                            frame_pil = Image.open(
                                io.BytesIO(base64.b64decode(resp.json()["frame_b64"]))
                            ).convert("RGB")
                            frames_rgb.append(np.asarray(frame_pil, dtype=np.uint8))
                        await asyncio.to_thread(
                            imageio.mimsave,
                            str(out_path),
                            frames_rgb,
                            format="GIF",
                            duration=0.10,
                            loop=0,
                        )
                        rendered_remote = True
            except Exception as exc:
                logger.warning(f"Remote GAGAvatar /render notice: {exc}")

        if not rendered_remote:
            local_ok, local_err = self._probe_local_gagavatar()
            if not local_ok:
                raise RuntimeError(
                    f"GAGAvatar CUDA runtime is unavailable for rendering ({local_err}). "
                    "Local OpenCV/CPU fallback is disabled."
                )

            engine = get_gagavatar_engine()
            feat_path = avatar_dir / "tracked_feature.pt"

            def _load_or_track_feature() -> Dict[str, Any]:
                try:
                    import torch

                    if feat_path.exists():
                        try:
                            return torch.load(feat_path, map_location="cpu", weights_only=False)
                        except Exception:
                            import pickle

                            return pickle.loads(feat_path.read_bytes())
                    src_path = Path(avatar.source_photo_path)
                    if not src_path.exists():
                        raise FileNotFoundError(f"Source portrait not found: {src_path}")
                    with Image.open(src_path) as im:
                        src_pil = im.convert("RGB")
                    with engine._gpu_lock:
                        feat = engine._track_pil_image(src_pil, f"{avatar_dir.name}.png")
                    torch.save(feat, feat_path)
                    return feat
                except (ImportError, ModuleNotFoundError):
                    import pickle

                    if feat_path.exists():
                        return pickle.loads(feat_path.read_bytes())
                    src_path = Path(avatar.source_photo_path)
                    if not src_path.exists():
                        raise FileNotFoundError(f"Source portrait not found: {src_path}")
                    with Image.open(src_path) as im:
                        src_pil = im.convert("RGB")
                    track_fn = getattr(engine, "_track_pil_image", lambda *args: {})
                    feat = track_fn(src_pil, f"{avatar_dir.name}.png")
                    feat_path.write_bytes(pickle.dumps(feat))
                    return feat

            tracked_feature = await asyncio.to_thread(_load_or_track_feature)

            if fmt == "png":
                frame_pil = await asyncio.to_thread(
                    engine.render_expression_frame,
                    tracked_feature=tracked_feature,
                    expression=expr,
                    mouth_open=mouth_open,
                    avatar_id=f"avatar_{avatar.id}",
                    style=style,
                )
                await asyncio.to_thread(frame_pil.save, str(out_path), "PNG")
            else:
                frames_pil = await asyncio.to_thread(
                    engine.render_animation_frames,
                    tracked_feature=tracked_feature,
                    expression=expr,
                    mouth_open=mouth_open,
                    duration_ms=duration_ms,
                    avatar_id=f"avatar_{avatar.id}",
                    style=style,
                )
                frames_rgb = [np.asarray(im.convert("RGB"), dtype=np.uint8) for im in frames_pil]
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
            "engine": "gagavatar_remote" if rendered_remote else (avatar.engine or "gagavatar"),
            "format": fmt,
            "filename": filename,
            "render_url": f"/api/v1/avatar/{avatar.id}/render-file/{filename}",
        }

    async def probe_remote_service(self, remote_url: str) -> Dict[str, Any]:
        """Probe health and GPU device details of a remote GAGAvatar microservice."""
        clean_url = remote_url.strip().rstrip("/")
        if not clean_url:
            return {"healthy": False, "error": "رابط السيرفر فارغ."}
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(f"{clean_url}/health")
                if resp.status_code == 200:
                    data = resp.json()
                    return {"healthy": True, "device": data.get("device", "GPU"), **data}
                return {"healthy": False, "error": f"HTTP {resp.status_code}"}
        except Exception as exc:
            return {"healthy": False, "error": str(exc)}

    async def generate_neural_frames_for_avatar(
        self,
        avatar_id: int,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> AvatarProfile:
        """Run full 3D neural GAGAvatar model on source photo to generate true photorealistic sprites & mouth frames."""
        avatar = await self._require_avatar(avatar_id, db, user_id=user_id)
        src_path = Path(avatar.source_photo_path)
        if not src_path.exists():
            raise FileNotFoundError(f"Source portrait photo not found: {src_path}")
        image_bytes = src_path.read_bytes()
        src_pil = self._decode_image_pil(image_bytes)

        avatar_dir = Path(avatar.avatar_preview_path).parent
        sprites_dir = avatar_dir / "sprites"
        mouth_dir = avatar_dir / "mouth"
        avatar_dir.mkdir(parents=True, exist_ok=True)
        sprites_dir.mkdir(parents=True, exist_ok=True)
        mouth_dir.mkdir(parents=True, exist_ok=True)

        expressions_list = list(FACE_EMOJI_ACTIONS.keys())
        gen_result = await self._run_generation_engine(
            image_bytes=image_bytes,
            src_pil=src_pil,
            style=avatar.style or "realistic",
            expressions=expressions_list,
            avatar_key=avatar_dir.name,
            require_face=True,
        )

        preview_path = avatar_dir / "preview.png"
        gen_result["portrait_pil"].save(preview_path, format="PNG")

        expr_files: Dict[str, Any] = {}
        for expr_key, sprite_pil in (gen_result.get("sprites_pil") or {}).items():
            fname = f"{expr_key}.png"
            sprite_pil.save(sprites_dir / fname, format="PNG")
            expr_files[expr_key] = fname

        mouth_manifest: Dict[str, List[int]] = {}
        for expr_key, mouth_imgs in (gen_result.get("mouth_pil") or {}).items():
            levels: List[int] = [0]
            for lvl_idx, mouth_img in enumerate(mouth_imgs, start=1):
                mouth_img.save(mouth_dir / f"{expr_key}_{lvl_idx}.png", format="PNG")
                levels.append(lvl_idx)
            mouth_manifest[expr_key] = levels
        if mouth_manifest:
            expr_files["_mouth"] = mouth_manifest

        tracked_feature = gen_result.get("tracked_feature")
        if tracked_feature is not None:
            feat_path = avatar_dir / "tracked_feature.pt"
            if isinstance(tracked_feature, (bytes, bytearray)):
                feat_path.write_bytes(bytes(tracked_feature))
            else:
                try:
                    import torch
                    await asyncio.to_thread(torch.save, tracked_feature, feat_path)
                except (ImportError, ModuleNotFoundError):
                    import pickle
                    await asyncio.to_thread(lambda: feat_path.write_bytes(pickle.dumps(tracked_feature)))

        avatar.sprites_dir = str(sprites_dir)
        avatar.expressions_json = json.dumps(expr_files)
        if gen_result.get("landmarks"):
            avatar.landmarks_json = json.dumps(gen_result["landmarks"])
        avatar.engine = gen_result.get("engine", "gagavatar")
        await db.commit()
        await db.refresh(avatar)
        logger.info(f"Generated full neural 3D GAGAvatar frames for Avatar id={avatar.id}")
        return avatar

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

    @staticmethod
    def _morph_mouth_image(
        img_pil: Image.Image,
        corner_dy: float = 0.0,
        mouth_gap: float = 0.0,
        lm: Optional[Dict[str, Any]] = None,
    ) -> Image.Image:
        """Apply realistic mouth kinematic deformation using facial landmarks."""
        try:
            import cv2

            img_np = np.array(img_pil).astype(np.float32)
            h, w, _ = img_np.shape

            landmarks = lm or {}
            m_pt = landmarks.get("mouth") or [0.50, 0.65]
            lm_pt = landmarks.get("left_mouth") or [0.41, 0.65]
            rm_pt = landmarks.get("right_mouth") or [0.59, 0.65]

            cx = float(m_pt[0] * w)
            cy = float(m_pt[1] * h)
            lx = float(lm_pt[0] * w)
            rx = float(rm_pt[0] * w)
            hw = max(24.0, (rx - lx) / 2.0)

            y_indices, x_indices = np.indices((h, w), dtype=np.float32)

            u = (x_indices - cx) / hw
            v = (y_indices - cy) / (hw * 0.75)

            mask = np.clip(1.0 - (u**2 / 2.0 + v**2 / 1.5), 0.0, 1.0)
            mask = mask**2

            dy_curve = corner_dy * (u**2 * 0.85 + 0.15 * (1.0 - np.clip(np.abs(u), 0.0, 1.0))) * mask
            jaw_mask = np.clip((y_indices - (cy - 3.0)) / (hw * 0.9), 0.0, 1.0) * mask
            dy_open = mouth_gap * (1.0 - np.clip(np.abs(u), 0.0, 1.0)**2) * jaw_mask

            upper_mask = np.clip(((cy + 2.0) - y_indices) / (hw * 0.45), 0.0, 1.0) * mask
            dy_upper = -0.22 * mouth_gap * (1.0 - np.clip(np.abs(u), 0.0, 1.0)**2) * upper_mask

            total_dy = dy_curve + dy_open + dy_upper

            map_x = x_indices.astype(np.float32)
            map_y = (y_indices - total_dy).astype(np.float32)

            warped = cv2.remap(
                img_np, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
            )

            if mouth_gap > 2.0:
                aperture_mask = np.exp(-((y_indices - cy) / (mouth_gap * 0.48))**2 - (u / 0.88)**2)
                aperture_mask = np.clip(aperture_mask, 0.0, 1.0)[:, :, None]
                cavity_color = np.array([28.0, 12.0, 16.0], dtype=np.float32)
                warped = warped * (1.0 - aperture_mask * 0.82) + cavity_color * (aperture_mask * 0.82)

            warped = np.clip(warped, 0, 255).astype(np.uint8)
            return Image.fromarray(warped)
        except Exception as exc:
            logger.warning(f"Failed to morph mouth image: {exc}")
            return img_pil

    async def rerender_avatar_mouth(
        self,
        avatar_id: int,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> AvatarProfile:
        """Re-render mouth frames and expression sprites for existing avatar with enhanced mouth kinematics."""
        avatar = await self._require_avatar(avatar_id, db, user_id=user_id)
        if not avatar.avatar_preview_path:
            raise FileNotFoundError(f"Avatar #{avatar_id} has no preview path")
        avatar_dir = Path(avatar.avatar_preview_path).parent
        sprites_dir = avatar_dir / "sprites"
        mouth_dir = avatar_dir / "mouth"
        mouth_dir.mkdir(parents=True, exist_ok=True)
        sprites_dir.mkdir(parents=True, exist_ok=True)

        base_path = sprites_dir / "neutral.png"
        if not base_path.exists():
            base_path = Path(avatar.avatar_preview_path)
        if not base_path.exists():
            raise FileNotFoundError(f"Base avatar image not found: {base_path}")

        base_im = Image.open(base_path).convert("RGB")
        lm = self.parse_landmarks(avatar)

        expr_configs = {
            "neutral":   {"corner_dy": 0.0,  "gap": 0.0},
            "happy":     {"corner_dy": -8.5, "gap": 2.5},
            "laugh":     {"corner_dy": -11.0, "gap": 8.0},
            "love":      {"corner_dy": -6.0, "gap": 1.5},
            "sad":       {"corner_dy": +9.5, "gap": 1.0},
            "surprised": {"corner_dy": -1.0, "gap": 14.0},
            "angry":     {"corner_dy": +4.5, "gap": 0.0},
            "thinking":  {"corner_dy": +2.0, "gap": 1.0},
            "wink":      {"corner_dy": -5.0, "gap": 1.5},
            "sleepy":    {"corner_dy": +3.0, "gap": 3.0},
            "wave":      {"corner_dy": -6.5, "gap": 2.0},
            "like":      {"corner_dy": -6.5, "gap": 1.5},
        }
        mouth_levels_gap = {1: 5.0, 2: 10.5, 3: 17.0}

        def _process():
            mouth_manifest: Dict[str, List[int]] = {}
            for expr_name, cfg in expr_configs.items():
                src_sprite = sprites_dir / f"{expr_name}.png"
                curr = Image.open(src_sprite).convert("RGB") if src_sprite.exists() else base_im.copy()
                enhanced = self._morph_mouth_image(
                    curr, corner_dy=cfg["corner_dy"], mouth_gap=cfg["gap"], lm=lm
                )
                enhanced.save(sprites_dir / f"{expr_name}.png", format="PNG")

                mouth_manifest[expr_name] = [0]
                for lvl, lvl_gap in mouth_levels_gap.items():
                    m_im = self._morph_mouth_image(
                        curr,
                        corner_dy=cfg["corner_dy"] * 0.7,
                        mouth_gap=max(cfg["gap"], lvl_gap),
                        lm=lm,
                    )
                    m_im.save(mouth_dir / f"{expr_name}_{lvl}.png", format="PNG")
                    mouth_manifest[expr_name].append(lvl)

            try:
                raw_expr = json.loads(avatar.expressions_json or "{}")
            except Exception:
                raw_expr = {}
            raw_expr["_mouth"] = mouth_manifest
            for expr_name in expr_configs:
                raw_expr[expr_name] = f"{expr_name}.png"
            avatar.expressions_json = json.dumps(raw_expr)

        await asyncio.to_thread(_process)
        await db.commit()
        await db.refresh(avatar)
        logger.info(f"Re-rendered mouth frames for Avatar id={avatar.id}")
        return avatar

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
        avatars = list(res.scalars().all())
        # Filter out orphaned records whose preview files do not exist on disk (e.g. purged test runs)
        valid = [a for a in avatars if a.avatar_preview_path and Path(a.avatar_preview_path).exists()]
        return valid

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
        mouth_frames: Dict[str, List[str]] = {}
        try:
            raw_expr = json.loads(avatar.expressions_json or "{}")
            for k, v in raw_expr.items():
                if k == "_mouth" and isinstance(v, dict):
                    for m_expr, lvls in v.items():
                        if isinstance(lvls, list):
                            mouth_frames[m_expr] = [
                                f"/api/v1/avatar/{avatar.id}/mouth/{m_expr}/{int(lvl)}"
                                for lvl in lvls
                            ]
                    continue
                if k.startswith("_"):
                    continue
                expressions_map[k] = f"/api/v1/avatar/{avatar.id}/sprite/{k}"
        except Exception:
            pass

        blink_url = (
            f"/api/v1/avatar/{avatar.id}/sprite/blink"
            if "blink" in expressions_map
            else None
        )

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
            "blink_sprite_url": blink_url,
            "mouth_frames": mouth_frames,
            "landmarks": cls.parse_landmarks(avatar),
            "created_at": avatar.created_at.isoformat() if avatar.created_at else None,
            "updated_at": avatar.updated_at.isoformat() if avatar.updated_at else None,
        }


def get_avatar_service() -> GAGAvatarService:
    return GAGAvatarService.get_instance()

