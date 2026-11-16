"""Standalone end-to-end verification script for the GAGAvatar & Face-Emoji service.

Usage examples:
  1) In-process against FastAPI ASGI (no separate server needed):
       py -3.12 scripts/test_avatar_flow.py

  2) Against a live local or Railway server:
       py -3.12 scripts/test_avatar_flow.py --base-url https://your-app.up.railway.app

  3) With a real frontal photo:
       py -3.12 scripts/test_avatar_flow.py --photo path/to/face.jpg
"""

from __future__ import annotations

import argparse
import asyncio
import io
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import numpy as np
from PIL import Image, ImageDraw

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _build_synthetic_face_jpeg() -> bytes:
    """Build a synthetic RGB JPEG buffer for --mock smoke testing."""
    img = Image.new("RGB", (360, 360), color=(235, 240, 246))
    draw = ImageDraw.Draw(img)
    draw.ellipse((98, 70, 262, 280), fill=(225, 195, 165))
    draw.ellipse((138, 142, 158, 162), fill=(45, 45, 50))
    draw.ellipse((202, 142, 222, 162), fill=(45, 45, 50))
    draw.arc((154, 200, 206, 232), start=10, end=170, fill=(185, 95, 90), width=4)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _resolve_default_photo() -> Path | None:
    candidates = [
        PROJECT_ROOT / "data" / "images" / "ahmed.png",
        PROJECT_ROOT / "221d295a997516a0eb6e125ec4b71ad605519ae9 (12).jpg",
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _build_mock_engine() -> MagicMock:
    from app.services.avatar.gagavatar_service import GAGAvatarService

    engine = MagicMock()
    engine.probe.return_value = (
        True,
        None,
        {"cuda_available": True, "cuda_device": "Mock CUDA GPU"},
    )

    def _track_and_generate(src_pil, style, expressions, avatar_key):
        sprites = {
            expr: Image.new("RGB", (512, 512), color=(50 + i * 10, 120, 200))
            for i, expr in enumerate(expressions)
        }
        sprites["blink"] = Image.new("RGB", (512, 512), color=(70, 120, 195))
        mouth_pil = {
            expr: [Image.new("RGB", (512, 512), color=(80 + lvl * 20, 125, 205)) for lvl in (1, 2, 3)]
            for expr in expressions
        }
        return {
            "engine": "gagavatar",
            "portrait_pil": sprites.get("neutral", next(iter(sprites.values()))).copy(),
            "sprites_pil": sprites,
            "mouth_pil": mouth_pil,
            "landmarks": GAGAvatarService._default_landmarks(),
            "tracked_feature": {"shapecode": [0.0], "expcode": [0.0]},
        }

    engine.track_and_generate_avatar.side_effect = _track_and_generate
    engine.render_expression_frame.return_value = Image.new("RGB", (512, 512), color=(90, 145, 215))
    engine.render_animation_frames.return_value = [
        Image.new("RGB", (512, 512), color=(85 + i * 12, 140, 210)) for i in range(6)
    ]
    return engine


async def run_flow(base_url: str | None, photo_path: str | None, use_mock: bool = False) -> None:
    chosen_photo = Path(photo_path) if photo_path else _resolve_default_photo()
    if chosen_photo and chosen_photo.exists() and not use_mock:
        photo_bytes = chosen_photo.read_bytes()
        require_face = "true"
        print(f"[1/8] Loaded real photo: {chosen_photo} ({len(photo_bytes)} bytes)")
    else:
        photo_bytes = _build_synthetic_face_jpeg()
        require_face = "false"
        if not use_mock:
            use_mock = base_url is None
        print(f"[1/8] Generated synthetic portrait ({len(photo_bytes)} bytes, mock={use_mock})")

    client_ctx = None
    in_process_patches = []

    if base_url:
        client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=180.0)
        print(f"[*] Connecting to live server: {base_url}")
    else:
        from app.db.session import init_db
        from app.main import app

        await init_db()
        if use_mock:
            p_eng = patch(
                "app.services.avatar.gagavatar_service.get_gagavatar_engine",
                return_value=_build_mock_engine(),
            )
            p_eng.start()
            in_process_patches.append(p_eng)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://inprocess.test",
            timeout=180.0,
        )
        print("[*] Running in-process FastAPI verification")

    try:
        client_ctx = client

        # Check runtime & emoji map
        r_status = await client.get("/api/v1/avatar/status")
        r_status.raise_for_status()
        status_json = r_status.json()
        print(
            f"[2/8] Avatar Engine Status: {status_json['preferred_engine']} "
            f"(strict={status_json.get('strict_gagavatar_only')}, "
            f"fallback={status_json.get('local_fallback_enabled')}, "
            f"cuda={status_json.get('cuda_device')})"
        )

        r_emojis = await client.get("/api/v1/avatar/emojis/map")
        r_emojis.raise_for_status()
        print(f"[*] Supported Face Emojis: {r_emojis.json()['count']}")

        # Step 1: Create draft #1
        r_create = await client.post(
            "/api/v1/avatar/create",
            files={"file": ("user_photo.jpg", photo_bytes, "image/jpeg")},
            data={"name": "TestUser", "style": "realistic", "require_face": require_face},
        )
        if r_create.status_code >= 400:
            raise RuntimeError(f"POST /avatar/create failed {r_create.status_code}: {r_create.text}")
        draft1 = r_create.json()["avatar"]
        print(f"[3/8] Created Draft #1 (id={draft1['id']}, status={draft1['status']}, engine={draft1['engine']})")
        assert draft1["engine"] in ("gagavatar", "gagavatar_remote"), f"Unexpected engine: {draft1['engine']}"

        # Fetch preview PNG, blink sprite, and mouth opening levels 0..3
        r_prev = await client.get(draft1["preview_url"])
        r_prev.raise_for_status()
        assert r_prev.content[:4] == b"\x89PNG"
        print(f"      Preview image verified: {len(r_prev.content)} bytes")

        blink_url = draft1.get("blink_sprite_url")
        assert blink_url, "Missing blink_sprite_url on GAGAvatar payload"
        r_blink = await client.get(blink_url)
        r_blink.raise_for_status()
        assert r_blink.content[:4] == b"\x89PNG"
        print(f"      Blink sprite verified: {len(r_blink.content)} bytes")

        happy_mouth_urls = (draft1.get("mouth_frames") or {}).get("happy") or []
        assert len(happy_mouth_urls) == 4, f"Expected 4 mouth levels (0..3), got {len(happy_mouth_urls)}"
        for lvl_idx, m_url in enumerate(happy_mouth_urls):
            r_mouth = await client.get(m_url)
            r_mouth.raise_for_status()
            assert r_mouth.content[:4] == b"\x89PNG"
        print(f"      Neural mouth frames (levels 0..3) verified for 'happy'")

        # Step 2: Reject & Recreate draft #2
        r_rec = await client.post(
            f"/api/v1/avatar/{draft1['id']}/recreate",
            data={"style": "studio_3d", "reason": "Test regeneration", "require_face": require_face},
        )
        r_rec.raise_for_status()
        draft2 = r_rec.json()["avatar"]
        print(f"[4/8] Recreated Draft #2 (id={draft2['id']}, attempt={draft2['attempt_number']}, style={draft2['style']})")

        # Step 3: Approve draft #2
        r_app = await client.post(f"/api/v1/avatar/{draft2['id']}/approve")
        r_app.raise_for_status()
        approved = r_app.json()["avatar"]
        print(f"[5/8] Approved Avatar id={approved['id']} (is_active={approved['is_active']})")

        # Step 4: Render emoji expression animation (😊 & 😂) in GIF + PNG
        for emoji in ("😊", "😂"):
            r_rend = await client.post(
                f"/api/v1/avatar/{approved['id']}/render",
                json={"face_emoji": emoji, "mouth_open": 0.65, "duration_ms": 600, "format": "gif"},
            )
            r_rend.raise_for_status()
            rmeta = r_rend.json()
            r_gif = await client.get(rmeta["render_url"])
            r_gif.raise_for_status()
            assert r_gif.content[:3] == b"GIF"
            print(f"[6/8] Rendered GIF {emoji} ({rmeta['expression']}): {len(r_gif.content)} bytes")

        r_png_rend = await client.post(
            f"/api/v1/avatar/{approved['id']}/render",
            json={"face_emoji": "😮", "mouth_open": 0.85, "format": "png"},
        )
        r_png_rend.raise_for_status()
        png_meta = r_png_rend.json()
        r_png = await client.get(png_meta["render_url"])
        r_png.raise_for_status()
        assert r_png.content[:4] == b"\x89PNG"
        print(f"[7/8] Rendered PNG 😮 ({png_meta['expression']}): {len(r_png.content)} bytes")

        # Step 5: Test Chat Face-Emoji + TTS Speech Cleaning
        if not base_url:
            p = patch(
                "app.providers.llm.local_ollama.LocalOllamaProvider.generate",
                new_callable=AsyncMock,
                return_value="أهلاً بيك يا بطل! منور الدنيا النهاردة 😊",
            )
            p.start()
            in_process_patches.append(p)

        r_chat = await client.post(
            "/api/v1/conversations/chat",
            json={"message": "أهلاً يا نيبولا", "session_id": "script-avatar-smoke", "return_audio": False},
        )
        r_chat.raise_for_status()
        cdata = r_chat.json()
        print(
            f"[8/8] Chat Result -> face_emoji={cdata.get('face_emoji')} "
            f"expression={cdata.get('expression')} "
            f"cleaned_reply='{cdata.get('cleaned_reply')}'"
        )
        print("\n[OK] All GAGAvatar creation, sprites, blink, mouth levels 0..3, approve, render, and chat checks passed!")
    finally:
        for p in in_process_patches:
            p.stop()
        if client_ctx is not None:
            await client_ctx.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify GAGAvatar & Face-Emoji end-to-end flow.")
    parser.add_argument("--base-url", default=None, help="Live server URL (omit to run in-process ASGI)")
    parser.add_argument("--photo", default=None, help="Optional path to a real face JPEG/PNG file")
    parser.add_argument("--mock", action="store_true", help="Force mocked GAGAvatar engine for offline CI smoke")
    args = parser.parse_args()
    asyncio.run(run_flow(args.base_url, args.photo, use_mock=args.mock))


if __name__ == "__main__":
    main()

