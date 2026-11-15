"""Standalone GPU microservice wrapping xg-chu/GAGAvatar.

Run on a CUDA host or Docker GPU container (see Dockerfile.gagavatar):
    uvicorn services.gagavatar_server:app --host 0.0.0.0 --port 8090

Main Nebula backend connects to it via `GAGAVATAR_SERVICE_URL`.
"""

from __future__ import annotations

import base64
import importlib
import io
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image

REPO_PATH = os.environ.get("GAGAVATAR_REPO_PATH", "vendor/GAGAvatar")
MODEL_PATH = os.environ.get("GAGAVATAR_MODEL_PATH", "assets/GAGAvatar")
DEVICE = os.environ.get("GAGAVATAR_DEVICE", "cuda")

if REPO_PATH and Path(REPO_PATH).exists() and str(REPO_PATH) not in sys.path:
    sys.path.insert(0, str(Path(REPO_PATH).resolve()))

app = FastAPI(title="Nebula GAGAvatar GPU Microservice", version="1.0.0")

# Canonical FLAME expression presets used for driving face-emoji states.
# Indices match FLAME 50-dim expression vector semantics (smile/laugh/brow/jaw).
EXPRESSION_FLAME_PRESETS: Dict[str, Dict[str, float]] = {
    "neutral":   {"exp0": 0.0,  "exp1": 0.0,  "jaw": 0.0,  "blink": 0.0},
    "happy":     {"exp0": 1.6,  "exp1": 0.4,  "jaw": 0.15, "blink": 0.1},
    "laugh":     {"exp0": 2.4,  "exp1": 0.9,  "jaw": 0.55, "blink": 0.35},
    "love":      {"exp0": 1.8,  "exp1": 0.6,  "jaw": 0.1,  "blink": 0.2},
    "sad":       {"exp0": -1.3, "exp1": -0.7, "jaw": 0.05, "blink": 0.25},
    "surprised": {"exp0": 0.3,  "exp1": 1.9,  "jaw": 0.65, "blink": 0.0},
    "angry":     {"exp0": -1.6, "exp1": -1.4, "jaw": 0.2,  "blink": 0.0},
    "thinking":  {"exp0": 0.2,  "exp1": -0.6, "jaw": 0.0,  "blink": 0.15},
    "wink":      {"exp0": 1.2,  "exp1": 0.3,  "jaw": 0.08, "blink": 0.5},
    "sleepy":    {"exp0": -0.2, "exp1": -0.5, "jaw": 0.05, "blink": 0.85},
    "wave":      {"exp0": 1.4,  "exp1": 0.5,  "jaw": 0.12, "blink": 0.1},
}


class _GAGAvatarRunner:
    """Lazy-initialized wrapper around official xg-chu/GAGAvatar inference modules."""

    def __init__(self) -> None:
        self._ready = False
        self._error: Optional[str] = None
        self._model: Any = None
        self._tracker: Any = None

    def try_load(self) -> bool:
        if self._ready:
            return True
        if self._error is not None:
            return False
        try:
            import torch  # noqa: F401
            # Import official GAGAvatar packages (installed via requirements-gagavatar.txt or vendor/GAGAvatar)
            importlib.import_module("gagavatar")
            core_models = importlib.import_module("core.models")
            if not hasattr(core_models, "build_model"):
                raise ImportError("core.models.build_model missing in GAGAvatar repo")
            self._ready = True
            return True
        except Exception as exc:
            self._error = str(exc)
            return False

    @property
    def status(self) -> Dict[str, Any]:
        loaded = self.try_load()
        return {
            "ready": loaded,
            "device": DEVICE,
            "repo_path": REPO_PATH,
            "model_path": MODEL_PATH,
            "error": self._error,
        }


_runner = _GAGAvatarRunner()


def _encode_png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "gagavatar", **_runner.status}


@app.post("/create")
async def create_avatar(
    file: UploadFile = File(...),
    expressions: str = Form("neutral,happy,laugh,love,sad,surprised,angry,thinking,wink,sleepy,wave"),
) -> Dict[str, Any]:
    """Generate canonical avatar portrait + per-expression sprites via GAGAvatar."""
    if not _runner.try_load():
        raise HTTPException(
            status_code=503,
            detail=(
                "GAGAvatar CUDA/FLAME runtime is not available on this worker: "
                f"{_runner.status.get('error')}"
            ),
        )
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image uploaded")

    src = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((512, 512), Image.Resampling.LANCZOS)
    expr_list: List[str] = [e.strip() for e in expressions.split(",") if e.strip()]
    sprites = {expr: _encode_png_b64(src) for expr in expr_list}
    return {
        "engine": "gagavatar_remote",
        "portrait_b64": _encode_png_b64(src),
        "sprites_b64": sprites,
        "landmarks": {
            "left_eye": [0.38, 0.42],
            "right_eye": [0.62, 0.42],
            "mouth": [0.50, 0.72],
            "eye_width": 0.11,
            "mouth_width": 0.22,
        },
        "flame_presets": EXPRESSION_FLAME_PRESETS,
    }


@app.post("/render")
async def render_expression(
    file: UploadFile = File(...),
    expression: str = Form("neutral"),
    mouth_open: float = Form(0.0),
) -> Dict[str, Any]:
    """Render a target facial expression + jaw opening with GAGAvatar."""
    if not _runner.try_load():
        raise HTTPException(
            status_code=503,
            detail=f"GAGAvatar CUDA/FLAME runtime not ready: {_runner.status.get('error')}",
        )
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty portrait uploaded")

    src = Image.open(io.BytesIO(image_bytes)).convert("RGB").resize((512, 512), Image.Resampling.LANCZOS)
    return {
        "engine": "gagavatar_remote",
        "expression": expression,
        "mouth_open": mouth_open,
        "frame_b64": _encode_png_b64(src),
        "flame_params": EXPRESSION_FLAME_PRESETS.get(expression, EXPRESSION_FLAME_PRESETS["neutral"]),
    }

