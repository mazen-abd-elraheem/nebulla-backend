"""Real xg-chu/GAGAvatar CUDA 3D Gaussian Splatting Engine Wrapper.

Provides thread-safe, VRAM-conscious inference on NVIDIA GPUs for:
1. Face tracking & canonical FLAME + DINOv2 feature extraction (`CoreEngine`).
2. Multi-expression 3DGS neural rendering (`GAGAvatarRuntime`) across all 12 canonical
   face-emoji expressions, eyelid blink frames, and jaw-open speaking frames.
3. On-demand real neural PNG/GIF rendering for API clients.
"""

from __future__ import annotations

import gc
import importlib
import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageEnhance

from app.core.config import settings
from app.core.logger import get_logger
from app.services.avatar.emoji_actions import FACE_EMOJI_ACTIONS

logger = get_logger(__name__)

# Disable TF & TorchInductor/Triton compilation (unsupported on Windows without Triton)
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")
os.environ["TORCH_COMPILE_DISABLE"] = "1"
os.environ["TORCHDYNAMO_DISABLE"] = "1"

# Empirically calibrated FLAME 2020 PCA expression coefficients + head poses on GAGAvatar.pt
# Distinctly tuned for clear, realistic mouth and lip kinematics (smile corners, frown downturn, speech jaw opening).
_EXPRESSION_RECIPES: Dict[str, Dict[str, Any]] = {
    "neutral": {"exp": {}, "jaw": 0.0, "rot": (0.0, 0.0, 0.0), "use_blink": 0.0, "use_wink": 0.0},
    "blink": {"exp": {}, "jaw": 0.0, "rot": (0.0, 0.0, 0.0), "use_blink": 1.0, "use_wink": 0.0},
    "happy": {"exp": {0: 3.5, 5: 0.6, 11: 1.2, 12: 0.8}, "jaw": 0.10, "rot": (0.0, 0.0, 0.0), "use_blink": 0.0, "use_wink": 0.0},
    "laugh": {"exp": {0: 4.2, 3: 1.8, 5: 1.2, 12: 1.0}, "jaw": 0.38, "rot": (-0.03, 0.0, 0.03), "use_blink": 0.0, "use_wink": 0.0},
    "love": {"exp": {0: 2.8, 11: 0.8, 12: 0.6}, "jaw": 0.08, "rot": (0.02, 0.04, 0.06), "use_blink": 0.0, "use_wink": 0.0},
    "sad": {"exp": {0: -2.8, 6: -2.5, 9: -2.0, 11: -1.5, 13: 2.2}, "jaw": 0.05, "rot": (0.06, 0.0, -0.04), "use_blink": 0.0, "use_wink": 0.0},
    "surprised": {"exp": {10: 3.5, 3: 1.6, 2: -1.8}, "jaw": 0.35, "rot": (-0.05, 0.0, 0.0), "use_blink": 0.0, "use_wink": 0.0},
    "angry": {"exp": {1: 3.2, 6: -2.5, 8: 1.8, 9: -1.8, 11: -2.0}, "jaw": 0.06, "rot": (0.04, 0.0, 0.0), "use_blink": 0.0, "use_wink": 0.0},
    "thinking": {"exp": {1: -2.2, 4: 2.0, 2: 0.8}, "jaw": 0.03, "rot": (-0.03, -0.10, 0.07), "use_blink": 0.0, "use_wink": 0.0},
    "wink": {"exp": {0: 2.4, 11: 0.6}, "jaw": 0.06, "rot": (0.0, 0.05, 0.06), "use_blink": 0.0, "use_wink": 1.0},
    "sleepy": {"exp": {9: -1.2, 3: 0.6}, "jaw": 0.12, "rot": (0.05, 0.0, -0.05), "use_blink": 0.9, "use_wink": 0.0},
    "wave": {"exp": {0: 2.8, 11: 1.0}, "jaw": 0.10, "rot": (-0.03, 0.06, 0.05), "use_blink": 0.0, "use_wink": 0.0},
    "like": {"exp": {0: 2.8, 11: 1.0}, "jaw": 0.08, "rot": (-0.02, 0.0, -0.04), "use_blink": 0.0, "use_wink": 0.0},
}

_JAW_LEVEL_PITCH: Dict[int, float] = {
    0: 0.0,
    1: 0.16,
    2: 0.30,
    3: 0.45,
}

_RENDER_BATCH_SIZE = 4


class GAGAvatarEngine:
    """Singleton CUDA engine wrapping CoreEngine (tracker) + GAGAvatarRuntime (3DGS renderer)."""

    _instance: Optional["GAGAvatarEngine"] = None
    _init_lock = threading.Lock()

    def __init__(self) -> None:
        self._gpu_lock = threading.RLock()
        self._runtime: Any = None
        self._blink_exp: Optional[Any] = None
        self._wink_exp: Optional[Any] = None
        self._torch_configured = False

    @classmethod
    def get_instance(cls) -> "GAGAvatarEngine":
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def _ensure_repo_on_path(self) -> None:
        repo_path = Path(settings.GAGAVATAR_REPO_PATH)
        if repo_path.exists():
            resolved = str(repo_path.resolve())
            if resolved not in sys.path:
                sys.path.insert(0, resolved)

    def _resolve_asset_paths(self) -> Tuple[Path, Path, Path]:
        model_dir = Path(settings.GAGAVATAR_MODEL_PATH)
        return (
            model_dir,
            model_dir / "GAGAvatar.pt",
            model_dir / "FLAME_with_eye.pt",
        )

    def _resolve_device(self) -> str:
        import torch

        pref = (settings.GAGAVATAR_DEVICE or "auto").strip().lower()
        if pref == "cuda":
            if not torch.cuda.is_available():
                raise RuntimeError("GAGAVATAR_DEVICE=cuda requested, but CUDA is not available.")
            return "cuda"
        if pref == "cpu":
            return "cpu"
        return "cuda" if torch.cuda.is_available() else "cpu"

    def _configure_torch_and_stubs(self) -> None:
        if self._torch_configured:
            return
        import inspect
        import warnings
        import torch

        warnings.filterwarnings("ignore", message="xFormers is not available", category=UserWarning)
        os.environ["TORCH_COMPILE_DISABLE"] = "1"
        os.environ["TORCHDYNAMO_DISABLE"] = "1"

        try:
            import torch._dynamo

            torch._dynamo.config.disable = True
            torch._dynamo.config.suppress_errors = True
        except Exception:
            pass

        # Bypass face_alignment's default compile=True + missing torch.compiler.save_cache_artifacts on Windows
        try:
            import face_alignment

            orig_init = face_alignment.FaceAlignment.__init__
            if not getattr(orig_init, "_nebula_no_compile_patched", False):
                has_compile_param = "compile" in inspect.signature(orig_init).parameters

                def _patched_fa_init(fa_self, *args: Any, **kwargs: Any) -> None:
                    if has_compile_param:
                        kwargs["compile"] = False
                    orig_init(fa_self, *args, **kwargs)

                _patched_fa_init._nebula_no_compile_patched = True  # type: ignore[attr-defined]
                face_alignment.FaceAlignment.__init__ = _patched_fa_init
        except Exception as exc:
            logger.debug(f"face_alignment compile guard skipped: {exc}")

        self._ensure_repo_on_path()
        try:
            vp = importlib.import_module("gagavatar.libs.utils_perceptual")
            vp.FacePerceptualLoss = torch.nn.Identity
        except Exception as exc:
            logger.debug(f"utils_perceptual patch skipped: {exc}")

        self._torch_configured = True

    def probe(self) -> Tuple[bool, Optional[str], Dict[str, Any]]:
        """Inspect CUDA, diff_gaussian_rasterization_32d, gagavatar runtime, and checkpoint assets."""
        self._ensure_repo_on_path()
        model_dir, ckpt_path, flame_path = self._resolve_asset_paths()
        info: Dict[str, Any] = {
            "model_dir": str(model_dir),
            "model_checkpoint_exists": ckpt_path.exists(),
            "flame_model_exists": flame_path.exists(),
            "cuda_available": False,
            "cuda_device": None,
            "rasterizer_available": False,
            "gagavatar_importable": False,
        }

        if not ckpt_path.exists():
            return False, f"GAGAvatar checkpoint missing at {ckpt_path}", info
        if not flame_path.exists():
            return False, f"FLAME_with_eye.pt missing at {flame_path}", info

        try:
            import torch

            info["cuda_available"] = bool(torch.cuda.is_available())
            if torch.cuda.is_available():
                info["cuda_device"] = torch.cuda.get_device_name(0)
            if not torch.cuda.is_available():
                return False, "CUDA GPU unavailable for diff_gaussian_rasterization_32d", info

            if importlib.util.find_spec("diff_gaussian_rasterization_32d") is None:
                return False, "diff_gaussian_rasterization_32d extension is not installed", info
            info["rasterizer_available"] = True

            import gagavatar.runtime  # noqa: F401
            info["gagavatar_importable"] = True
            return True, None, info
        except Exception as exc:
            return False, str(exc), info

    def _ensure_eye_exp_vectors(self) -> Tuple[Any, Any]:
        """Compute symmetric blink and asymmetric wink FLAME PCA expression vectors once."""
        if self._blink_exp is not None and self._wink_exp is not None:
            return self._blink_exp, self._wink_exp

        import torch

        _, _, flame_path = self._resolve_asset_paths()
        flame_ckpt = torch.load(flame_path, map_location="cpu", weights_only=True)
        fm = flame_ckpt["flame_model"]
        lmk = flame_ckpt["lmk_embeddings"]
        v = fm["v_template"].float()
        f = fm["f"].long()
        exp_dirs = fm["shapedirs"][:, :, 300:400].float()
        static_idx = lmk["static_lmk_faces_idx"].long()

        def verts_for_lmk(li: int) -> List[int]:
            return f[static_idx[li]].tolist()

        def solve_eyelids(
            close_right: bool,
            close_left: bool,
            right_strength: float,
            left_strength: float,
        ) -> torch.Tensor:
            r_up_y = v[verts_for_lmk(20) + verts_for_lmk(21), 1].mean()
            r_lo_y = v[verts_for_lmk(23) + verts_for_lmk(24), 1].mean()
            l_up_y = v[verts_for_lmk(26) + verts_for_lmk(27), 1].mean()
            l_lo_y = v[verts_for_lmk(29) + verts_for_lmk(30), 1].mean()

            rows_a = []
            rows_b = []
            targets = [
                ([20, 21], close_right, float(r_lo_y - r_up_y) * right_strength),
                ([26, 27], close_left, float(l_lo_y - l_up_y) * left_strength),
                ([23, 24], close_right, 0.25 * float(r_up_y - r_lo_y) * right_strength),
                ([29, 30], close_left, 0.25 * float(l_up_y - l_lo_y) * left_strength),
            ]
            for indices, active, target_dy in targets:
                for li in indices:
                    for vi in verts_for_lmk(li):
                        rows_a.append(exp_dirs[vi, 1, :])
                        rows_b.append(target_dy if active else 0.0)

            for li in range(31, 51):
                for vi in verts_for_lmk(li):
                    for coord in range(3):
                        rows_a.append(0.5 * exp_dirs[vi, coord, :])
                        rows_b.append(0.0)

            if close_right != close_left:
                open_indices = [25, 26, 27, 28, 29, 30] if close_right else [19, 20, 21, 22, 23, 24]
                for li in open_indices:
                    for vi in verts_for_lmk(li):
                        rows_a.append(1.5 * exp_dirs[vi, 1, :])
                        rows_b.append(0.0)

            a_mat = torch.stack(rows_a, dim=0)
            b_vec = torch.tensor(rows_b, dtype=torch.float32)
            lam = torch.linspace(1e-7, 2e-5, a_mat.shape[1])
            w = torch.linalg.solve(a_mat.T @ a_mat + torch.diag(lam), a_mat.T @ b_vec)
            return w.clamp(-4.5, 4.5)

        self._blink_exp = solve_eyelids(True, True, right_strength=1.45, left_strength=1.75)
        self._wink_exp = solve_eyelids(True, False, right_strength=1.60, left_strength=0.0)
        return self._blink_exp, self._wink_exp

    def build_motion_code(
        self,
        expression: str,
        mouth_level: int = 0,
        mouth_open: Optional[float] = None,
        blink: bool = False,
        rot_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> Any:
        """Build a 106-dim GAGAvatar motion vector: [exp(100), global_rot(3), jaw_pose(3)]."""
        import torch

        blink_vec, wink_vec = self._ensure_eye_exp_vectors()
        key = expression if expression in _EXPRESSION_RECIPES else "neutral"
        recipe = _EXPRESSION_RECIPES[key]

        code = torch.zeros(106, dtype=torch.float32)
        if recipe["use_blink"]:
            code[:100] += float(recipe["use_blink"]) * blink_vec
        if recipe["use_wink"]:
            code[:100] += float(recipe["use_wink"]) * wink_vec
        if blink:
            code[:100] = (code[:100] + blink_vec).clamp(-4.5, 4.5)

        for idx, val in recipe["exp"].items():
            code[int(idx)] = float(val)

        base_jaw = float(recipe["jaw"])
        if mouth_open is not None:
            m = float(np.clip(mouth_open, 0.0, 1.0))
            jaw_pitch = max(base_jaw if m < 0.08 else 0.0, m * 0.45)
            if m > 0.08:
                code[3] = float(code[3]) + min(1.2, m * 1.2)
        else:
            lvl = max(0, min(int(mouth_level), 3))
            if lvl == 0:
                jaw_pitch = base_jaw
            else:
                jaw_pitch = max(base_jaw, _JAW_LEVEL_PITCH[lvl])
                code[3] = float(code[3]) + (0.45 * lvl)

        code[103] = float(np.clip(jaw_pitch, -0.05, 0.50))
        rx, ry, rz = recipe["rot"]
        code[100] = rx + rot_offset[0]
        code[101] = ry + rot_offset[1]
        code[102] = rz + rot_offset[2]
        return code

    def _get_or_init_runtime(self) -> Any:
        if self._runtime is not None:
            return self._runtime

        self._configure_torch_and_stubs()
        import gagavatar.models  # noqa: F401
        models_mod = importlib.import_module("gagavatar.models.GAGAvatar.models")
        import torch

        models_mod.FacePerceptualLoss = torch.nn.Identity

        from gagavatar.assets import GAGAvatarAssets
        from gagavatar.runtime import GAGAvatarRuntime, GAGAvatarRuntimeConfig

        model_dir, ckpt_path, flame_path = self._resolve_asset_paths()
        device = self._resolve_device()
        cfg = GAGAvatarRuntimeConfig(
            assets=GAGAvatarAssets(
                root=model_dir,
                model_path=ckpt_path,
                flame_model_path=flame_path,
            ),
            device=device,
        )
        self._runtime = GAGAvatarRuntime(cfg)
        self._ensure_eye_exp_vectors()
        return self._runtime

    def _release_runtime_for_tracking(self) -> None:
        """Temporarily free cached GAGAvatarRuntime so TrackEngine fits comfortably in 6 GB VRAM."""
        import torch

        if self._runtime is not None:
            self._runtime = None
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def _track_pil_image(self, src_pil: Image.Image, track_key: str) -> Dict[str, Any]:
        """Run upstream CoreEngine.track_image and release tracker VRAM immediately afterward."""
        self._configure_torch_and_stubs()
        import torch
        from gagavatar.libs.GAGAvatar_track.engines import CoreEngine as TrackEngine

        self._release_runtime_for_tracking()
        device = self._resolve_device()

        rgb_np = np.array(src_pil.convert("RGB"), dtype=np.uint8, copy=True)
        image_chw = torch.from_numpy(rgb_np).permute(2, 0, 1).contiguous().float()

        tracker = TrackEngine(focal_length=12.0, device=device)
        try:
            tracked_map = tracker.track_image([image_chw], [track_key], if_matting=True)
        finally:
            del tracker
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        if not tracked_map or track_key not in tracked_map:
            raise ValueError(
                "لم يتم العثور على وجه واضح في الصورة عبر GAGAvatar Tracker. من فضلك استخدم صورة واضحة للوجه."
            )

        feature = tracked_map[track_key]
        for key in list(feature.keys()):
            if isinstance(feature[key], np.ndarray):
                feature[key] = torch.tensor(feature[key])
            elif torch.is_tensor(feature[key]):
                feature[key] = feature[key].detach().cpu()
        return feature

    @staticmethod
    def _tensor_to_pil(rgb_chw: Any, style: str = "realistic") -> Image.Image:
        arr = (
            rgb_chw.clamp(0.0, 1.0)
            .permute(1, 2, 0)
            .detach()
            .cpu()
            .numpy()
            * 255.0
        ).round().astype(np.uint8)
        img = Image.fromarray(arr, mode="RGB")
        if style == "studio_3d":
            img = ImageEnhance.Color(img).enhance(1.12)
            img = ImageEnhance.Contrast(img).enhance(1.06)
        elif style == "stylized":
            img = ImageEnhance.Color(img).enhance(1.24)
            img = ImageEnhance.Contrast(img).enhance(1.10)
        return img

    @staticmethod
    def extract_landmarks_from_feature(feature: Dict[str, Any]) -> Dict[str, Any]:
        """Compute canonical normalized [0..1] eye & mouth anchors from tracked 512x512 crop."""
        # GAGAvatar canonicalizes the tracked crop to centered frontal alignment in [-1, 1]
        return {
            "left_eye": [0.40, 0.44],
            "right_eye": [0.60, 0.44],
            "nose": [0.50, 0.54],
            "mouth": [0.50, 0.68],
            "left_mouth": [0.42, 0.68],
            "right_mouth": [0.58, 0.68],
            "eye_width": 0.11,
            "mouth_width": 0.20,
            "tracked_keys": sorted(str(k) for k in feature.keys()),
        }

    def _render_motion_list(
        self,
        feature: Dict[str, Any],
        motion_codes: List[Any],
        avatar_id: str,
        style: str = "realistic",
    ) -> List[Image.Image]:
        import torch

        runtime = self._get_or_init_runtime()
        runtime.set_tracked_avatar(feature, avatar_id=avatar_id)
        stacked = torch.stack(motion_codes, dim=0)
        rendered: List[Image.Image] = []
        with torch.no_grad():
            for start in range(0, len(stacked), _RENDER_BATCH_SIZE):
                chunk = stacked[start : start + _RENDER_BATCH_SIZE]
                batch = runtime.build_forward_batch(chunk)
                rgb_batch = runtime.render_rgb_batch(batch)
                for idx in range(rgb_batch.shape[0]):
                    rendered.append(self._tensor_to_pil(rgb_batch[idx], style=style))
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        return rendered

    def track_and_generate_avatar(
        self,
        src_pil: Image.Image,
        style: str,
        expressions: List[str],
        avatar_key: str,
    ) -> Dict[str, Any]:
        """Track user photo with GAGAvatar CoreEngine and render neural portrait, sprites & mouth levels."""
        import torch

        ok, err, _ = self.probe()
        if not ok:
            raise RuntimeError(f"GAGAvatar CUDA runtime unavailable: {err}")

        with self._gpu_lock:
            feature = self._track_pil_image(src_pil, f"{avatar_key}.png")

            clean_exprs = [e for e in expressions if e in FACE_EMOJI_ACTIONS]
            if "neutral" not in clean_exprs:
                clean_exprs.insert(0, "neutral")

            jobs: List[Tuple[str, Any, Any]] = []
            # 1. Neutral expression sprites + blink sprite
            for expr in clean_exprs:
                jobs.append(("sprite", expr, self.build_motion_code(expr, mouth_level=0)))
            jobs.append(("sprite", "blink", self.build_motion_code("blink", mouth_level=0)))

            # 2. Neural jaw-opening levels 1..3 for every expression (for emoji+speech lip-sync)
            for expr in clean_exprs:
                for lvl in (1, 2, 3):
                    jobs.append(("mouth", (expr, lvl), self.build_motion_code(expr, mouth_level=lvl)))

            rendered_imgs = self._render_motion_list(
                feature=feature,
                motion_codes=[j[2] for j in jobs],
                avatar_id=avatar_key,
                style=style,
            )

            sprites_pil: Dict[str, Image.Image] = {}
            mouth_pil: Dict[str, List[Image.Image]] = {expr: [] for expr in clean_exprs}
            for (kind, meta, _), img in zip(jobs, rendered_imgs):
                if kind == "sprite":
                    sprites_pil[str(meta)] = img
                else:
                    expr_name, _lvl = meta
                    mouth_pil[expr_name].append(img)

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            portrait_pil = sprites_pil["neutral"].copy()
            return {
                "engine": "gagavatar",
                "portrait_pil": portrait_pil,
                "sprites_pil": sprites_pil,
                "mouth_pil": mouth_pil,
                "landmarks": self.extract_landmarks_from_feature(feature),
                "tracked_feature": feature,
            }

    def render_expression_frame(
        self,
        tracked_feature: Dict[str, Any],
        expression: str,
        mouth_open: float = 0.0,
        avatar_id: str = "render",
        rot_offset: Tuple[float, float, float] = (0.0, 0.0, 0.0),
        style: str = "realistic",
    ) -> Image.Image:
        """Render a single 512x512 neural frame via GAGAvatarRuntime."""
        ok, err, _ = self.probe()
        if not ok:
            raise RuntimeError(f"GAGAvatar CUDA runtime unavailable: {err}")

        with self._gpu_lock:
            code = self.build_motion_code(
                expression=expression,
                mouth_open=mouth_open,
                rot_offset=rot_offset,
            )
            frames = self._render_motion_list(
                feature=tracked_feature,
                motion_codes=[code],
                avatar_id=avatar_id,
                style=style,
            )
            return frames[0]

    def render_animation_frames(
        self,
        tracked_feature: Dict[str, Any],
        expression: str,
        mouth_open: float = 0.45,
        duration_ms: int = 1200,
        avatar_id: str = "render",
        style: str = "realistic",
    ) -> List[Image.Image]:
        """Render a smooth sequence of neural speech + natural blink frames via GAGAvatarRuntime."""
        ok, err, _ = self.probe()
        if not ok:
            raise RuntimeError(f"GAGAvatar CUDA runtime unavailable: {err}")

        steps = max(6, min(16, duration_ms // 100))
        with self._gpu_lock:
            motion_codes = []
            for idx in range(steps):
                phase = idx / max(1, steps - 1)
                wave = float(abs(np.sin(phase * np.pi * 3.0))) * float(np.clip(mouth_open, 0.15, 0.95))
                blink_now = idx == (steps // 2)
                rot_off = (0.0, float(np.sin(phase * np.pi * 2.0)) * 0.035, 0.0)
                motion_codes.append(
                    self.build_motion_code(
                        expression=expression,
                        mouth_open=wave,
                        blink=blink_now,
                        rot_offset=rot_off,
                    )
                )
            return self._render_motion_list(
                feature=tracked_feature,
                motion_codes=motion_codes,
                avatar_id=avatar_id,
                style=style,
            )


def get_gagavatar_engine() -> GAGAvatarEngine:
    return GAGAvatarEngine.get_instance()

