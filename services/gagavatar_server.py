"""Standalone GPU microservice wrapping xg-chu/GAGAvatar.

Run on a CUDA host or Docker GPU container (see Dockerfile.gagavatar):
    uvicorn services.gagavatar_server:app --host 0.0.0.0 --port 8090

Main Nebula backend connects to it via `GAGAVATAR_SERVICE_URL`.
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image

REPO_PATH = os.environ.get("GAGAVATAR_REPO_PATH", "vendor/GAGAvatar")
MODEL_PATH = os.environ.get("GAGAVATAR_MODEL_PATH", "assets/GAGAvatar")
DEVICE = os.environ.get("GAGAVATAR_DEVICE", "cuda")

if REPO_PATH and Path(REPO_PATH).exists() and str(REPO_PATH) not in sys.path:
    sys.path.insert(0, str(Path(REPO_PATH).resolve()))

from app.services.avatar.gagavatar_engine import get_gagavatar_engine

app = FastAPI(title="Nebula GAGAvatar GPU Microservice", version="1.0.0")

EXPRESSION_FLAME_PRESETS: Dict[str, Dict[str, float]] = {
    "neutral":   {"exp0": 0.0,  "exp1": 0.0,  "jaw": 0.0,  "blink": 0.0},
    "happy":     {"exp0": 2.3,  "exp5": 0.6,  "jaw": 0.05, "blink": 0.0},
    "laugh":     {"exp0": 3.1,  "exp3": 1.0,  "jaw": 0.28, "blink": 0.0},
    "love":      {"exp0": 2.0,  "exp11": -1.1,"jaw": 0.04, "blink": 0.0},
    "sad":       {"exp0": -1.6, "exp6": -2.2, "jaw": 0.02, "blink": 0.0},
    "surprised": {"exp10": 2.5, "exp3": 1.2,  "jaw": 0.22, "blink": 0.0},
    "angry":     {"exp1": 2.8,  "exp6": -2.0, "jaw": 0.08, "blink": 0.0},
    "thinking":  {"exp1": -2.2, "exp4": 2.0,  "jaw": 0.0,  "blink": 0.0},
    "wink":      {"exp0": 1.8,  "wink": 1.0,  "jaw": 0.04, "blink": 0.0},
    "sleepy":    {"exp9": -0.8, "blink": 0.9, "jaw": 0.06},
    "wave":      {"exp0": 2.1,  "exp11": 1.2, "jaw": 0.10, "blink": 0.0},
    "like":      {"exp0": 2.0,  "exp11": 0.8, "jaw": 0.05, "blink": 0.0},
}


def _encode_png_b64(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


@app.get("/health")
async def health() -> Dict[str, Any]:
    ok, err, info = get_gagavatar_engine().probe()
    return {
        "status": "ok" if ok else "degraded",
        "service": "gagavatar",
        "ready": ok,
        "device": DEVICE,
        "repo_path": REPO_PATH,
        "model_path": MODEL_PATH,
        "error": err,
        **info,
    }


@app.post("/create")
async def create_avatar(
    file: UploadFile = File(...),
    expressions: str = Form("neutral,happy,laugh,love,sad,surprised,angry,thinking,wink,sleepy,wave,like"),
    style: str = Form("realistic"),
) -> Dict[str, Any]:
    """Generate canonical GAGAvatar portrait, per-expression sprites, and mouth frames."""
    engine = get_gagavatar_engine()
    ok, err, _ = engine.probe()
    if not ok:
        raise HTTPException(
            status_code=503,
            detail=f"GAGAvatar CUDA/FLAME runtime is not available on this worker: {err}",
        )
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image uploaded")

    src_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    expr_list: List[str] = [e.strip() for e in expressions.split(",") if e.strip()]
    avatar_key = f"remote_{uuid.uuid4().hex[:10]}"

    try:
        res = await asyncio.to_thread(
            engine.track_and_generate_avatar, src_pil, style, expr_list, avatar_key
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    sprites_b64 = {k: _encode_png_b64(v) for k, v in res["sprites_pil"].items()}
    mouth_b64 = {
        k: [_encode_png_b64(im) for im in imgs]
        for k, imgs in (res.get("mouth_pil") or {}).items()
    }

    feat_buf = io.BytesIO()
    import torch

    torch.save(res["tracked_feature"], feat_buf)
    return {
        "engine": "gagavatar_remote",
        "portrait_b64": _encode_png_b64(res["portrait_pil"]),
        "sprites_b64": sprites_b64,
        "mouth_b64": mouth_b64,
        "tracked_feature_b64": base64.b64encode(feat_buf.getvalue()).decode("ascii"),
        "landmarks": res["landmarks"],
        "flame_presets": EXPRESSION_FLAME_PRESETS,
    }


@app.post("/render")
async def render_expression(
    file: UploadFile = File(...),
    expression: str = Form("neutral"),
    mouth_open: float = Form(0.0),
    style: str = Form("realistic"),
) -> Dict[str, Any]:
    """Render a target facial expression + jaw opening solely with GAGAvatar."""
    engine = get_gagavatar_engine()
    ok, err, _ = engine.probe()
    if not ok:
        raise HTTPException(
            status_code=503,
            detail=f"GAGAvatar CUDA/FLAME runtime not ready: {err}",
        )
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty portrait uploaded")

    src_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    def _run_render() -> Image.Image:
        key = f"render_{uuid.uuid4().hex[:10]}"
        with engine._gpu_lock:
            feat = engine._track_pil_image(src_pil, f"{key}.png")
            return engine.render_expression_frame(
                tracked_feature=feat,
                expression=expression,
                mouth_open=mouth_open,
                avatar_id=key,
                style=style,
            )

    try:
        frame_pil = await asyncio.to_thread(_run_render)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    return {
        "engine": "gagavatar_remote",
        "expression": expression,
        "mouth_open": mouth_open,
        "frame_b64": _encode_png_b64(frame_pil),
        "flame_params": EXPRESSION_FLAME_PRESETS.get(expression, EXPRESSION_FLAME_PRESETS["neutral"]),
    }

