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
from unittest.mock import AsyncMock, patch

import cv2
import httpx
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _build_synthetic_face_jpeg() -> bytes:
    """Draw a high-contrast synthetic portrait image for offline smoke testing."""
    canvas = np.full((360, 360, 3), (235, 240, 246), dtype=np.uint8)
    # Face oval (BGR)
    cv2.ellipse(canvas, (180, 175), (82, 105), 0, 0, 360, (165, 195, 225), -1)
    # Eyes
    cv2.circle(canvas, (148, 152), 10, (45, 45, 50), -1)
    cv2.circle(canvas, (212, 152), 10, (45, 45, 50), -1)
    # Brows
    cv2.line(canvas, (132, 132), (164, 130), (40, 35, 35), 4)
    cv2.line(canvas, (196, 130), (228, 132), (40, 35, 35), 4)
    # Mouth
    cv2.ellipse(canvas, (180, 222), (26, 10), 0, 0, 180, (90, 95, 185), 4)

    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
    buf = io.BytesIO()
    Image.fromarray(rgb).save(buf, format="JPEG", quality=92)
    return buf.getvalue()


async def run_flow(base_url: str | None, photo_path: str | None) -> None:
    if photo_path:
        photo_bytes = Path(photo_path).read_bytes()
        require_face = "true"
        print(f"[1/7] Loaded photo: {photo_path} ({len(photo_bytes)} bytes)")
    else:
        photo_bytes = _build_synthetic_face_jpeg()
        # Allow synthetic smoke portrait if Haar/UniFace misses stylized drawing
        require_face = "false"
        print(f"[1/7] Generated synthetic test portrait ({len(photo_bytes)} bytes)")

    client_ctx = None
    in_process_patches = []

    if base_url:
        client = httpx.AsyncClient(base_url=base_url.rstrip("/"), timeout=60.0)
        print(f"[*] Connecting to live server: {base_url}")
    else:
        from app.db.session import init_db
        from app.main import app

        await init_db()
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://inprocess.test",
            timeout=60.0,
        )
        print("[*] Running in-process FastAPI verification")

    try:
        client_ctx = client

        # Check runtime & emoji map
        r_status = await client.get("/api/v1/avatar/status")
        r_status.raise_for_status()
        print(f"[2/7] Avatar Engine Status: {r_status.json()['preferred_engine']}")

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
        print(f"[3/7] Created Draft #1 (id={draft1['id']}, status={draft1['status']}, engine={draft1['engine']})")

        # Fetch preview PNG
        r_prev = await client.get(draft1["preview_url"])
        r_prev.raise_for_status()
        print(f"      Preview image verified: {len(r_prev.content)} bytes")

        # Step 2: Reject & Recreate draft #2
        r_rec = await client.post(
            f"/api/v1/avatar/{draft1['id']}/recreate",
            data={"style": "studio_3d", "reason": "Test regeneration", "require_face": require_face},
        )
        r_rec.raise_for_status()
        draft2 = r_rec.json()["avatar"]
        print(f"[4/7] Recreated Draft #2 (id={draft2['id']}, attempt={draft2['attempt_number']}, style={draft2['style']})")

        # Step 3: Approve draft #2
        r_app = await client.post(f"/api/v1/avatar/{draft2['id']}/approve")
        r_app.raise_for_status()
        approved = r_app.json()["avatar"]
        print(f"[5/7] Approved Avatar id={approved['id']} (is_active={approved['is_active']})")

        # Step 4: Render emoji expression animation (😊 & 😂)
        for emoji in ("😊", "😂"):
            r_rend = await client.post(
                f"/api/v1/avatar/{approved['id']}/render",
                json={"face_emoji": emoji, "mouth_open": 0.65, "duration_ms": 600, "format": "gif"},
            )
            r_rend.raise_for_status()
            rmeta = r_rend.json()
            r_gif = await client.get(rmeta["render_url"])
            r_gif.raise_for_status()
            print(f"[6/7] Rendered {emoji} ({rmeta['expression']}): {len(r_gif.content)} bytes GIF")

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
            json={"message": "أهلاً يا نيبولا", "session_id": "script-avatar-smoke", "return_audio": True},
        )
        r_chat.raise_for_status()
        cdata = r_chat.json()
        print(
            f"[7/7] Chat Result -> face_emoji={cdata.get('face_emoji')} "
            f"expression={cdata.get('expression')} "
            f"cleaned_reply='{cdata.get('cleaned_reply')}' "
            f"has_voice_sample={cdata.get('has_voice_sample')}"
        )
        print("\n✅ All avatar creation, reject/recreate, approve, emoji animation, and chat checks passed!")
    finally:
        for p in in_process_patches:
            p.stop()
        if client_ctx is not None:
            await client_ctx.aclose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify GAGAvatar & Face-Emoji end-to-end flow.")
    parser.add_argument("--base-url", default=None, help="Live server URL (omit to run in-process ASGI)")
    parser.add_argument("--photo", default=None, help="Optional path to a real face JPEG/PNG file")
    args = parser.parse_args()
    asyncio.run(run_flow(args.base_url, args.photo))


if __name__ == "__main__":
    main()

