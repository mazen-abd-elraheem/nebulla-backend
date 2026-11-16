"""Integration tests for GAGAvatar REST APIs & Chat Face-Emoji + Cloned Voice pipeline."""

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.db.session import init_db
from app.main import app
from app.services.avatar.gagavatar_service import GAGAvatarService


def _fake_photo_bytes() -> bytes:
    img = Image.new("RGB", (300, 300), color=(210, 175, 150))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _mock_gagavatar_engine() -> MagicMock:
    engine = MagicMock()
    engine.probe.return_value = (
        True,
        None,
        {"cuda_available": True, "cuda_device": "Mock CUDA GPU"},
    )

    def _track_and_generate(src_pil, style, expressions, avatar_key):
        sprites = {
            expr: Image.new("RGB", (512, 512), color=(50 + i * 8, 125, 200))
            for i, expr in enumerate(expressions)
        }
        sprites["blink"] = Image.new("RGB", (512, 512), color=(70, 125, 195))
        mouth_pil = {
            expr: [Image.new("RGB", (512, 512), color=(80 + lvl * 20, 130, 205)) for lvl in (1, 2, 3)]
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


@pytest.mark.asyncio
async def test_avatar_api_create_preview_recreate_approve_render_and_chat(tmp_path):
    await init_db()
    test_svc = GAGAvatarService(output_dir=str(tmp_path / "api_avatars"))
    mock_engine = _mock_gagavatar_engine()

    with (
        patch("app.api.v1.endpoints.avatar.get_avatar_service", return_value=test_svc),
        patch("app.services.avatar.gagavatar_service.GAGAvatarService.get_instance", return_value=test_svc),
        patch("app.services.avatar.gagavatar_service.get_gagavatar_engine", return_value=mock_engine),
    ):
        app.dependency_overrides.clear()
        from app.api.v1.endpoints.avatar import get_avatar_service as dep_get_svc
        app.dependency_overrides[dep_get_svc] = lambda: test_svc

        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                # 1. Discover emoji catalog & engine status
                r_map = await client.get("/api/v1/avatar/emojis/map")
                assert r_map.status_code == 200
                emojis = {item["face_emoji"] for item in r_map.json()["emojis"]}
                assert "😊" in emojis and "😂" in emojis and "😮" in emojis

                r_status = await client.get("/api/v1/avatar/status")
                assert r_status.status_code == 200
                status_payload = r_status.json()
                assert status_payload["preferred_engine"] == "gagavatar"
                assert status_payload["strict_gagavatar_only"] is True
                assert status_payload["local_fallback_enabled"] is False

                # 2. Upload photo -> creates pending_review draft #1
                r_create = await client.post(
                    "/api/v1/avatar/create",
                    files={"file": ("selfie.jpg", _fake_photo_bytes(), "image/jpeg")},
                    data={"name": "امير", "style": "realistic"},
                )
                assert r_create.status_code == 201
                body1 = r_create.json()
                assert body1["status"] == "pending_review"
                avatar1 = body1["avatar"]
                avatar1_id = avatar1["id"]
                assert avatar1["engine"] == "gagavatar"
                assert avatar1["is_active"] is False
                assert avatar1["blink_sprite_url"] == f"/api/v1/avatar/{avatar1_id}/sprite/blink"
                assert len(avatar1["mouth_frames"]["happy"]) == 4

                # Fetch preview image, sprite PNG, blink sprite, and mouth levels 0..3
                r_prev = await client.get(avatar1["preview_url"])
                assert r_prev.status_code == 200
                assert r_prev.headers["content-type"] == "image/png"
                assert r_prev.content[:4] == b"\x89PNG"

                r_sprite = await client.get(avatar1["sprites"]["happy"])
                assert r_sprite.status_code == 200
                assert r_sprite.content[:4] == b"\x89PNG"

                r_blink = await client.get(avatar1["blink_sprite_url"])
                assert r_blink.status_code == 200
                assert r_blink.content[:4] == b"\x89PNG"

                for mouth_url in avatar1["mouth_frames"]["happy"]:
                    r_mouth = await client.get(mouth_url)
                    assert r_mouth.status_code == 200
                    assert r_mouth.content[:4] == b"\x89PNG"

                # 3. User doesn't like draft #1 -> recreate draft #2
                r_recreate = await client.post(
                    f"/api/v1/avatar/{avatar1_id}/recreate",
                    data={"style": "studio_3d", "reason": "عايز شكل أوضح"},
                )
                assert r_recreate.status_code == 200
                avatar2 = r_recreate.json()["avatar"]
                avatar2_id = avatar2["id"]
                assert avatar2_id != avatar1_id
                assert avatar2["attempt_number"] == 2
                assert avatar2["status"] == "pending_review"

                # 4. Approve draft #2 -> becomes active
                r_approve = await client.post(f"/api/v1/avatar/{avatar2_id}/approve")
                assert r_approve.status_code == 200
                assert r_approve.json()["avatar"]["is_active"] is True

                r_active = await client.get("/api/v1/avatar/active")
                assert r_active.status_code == 200
                assert r_active.json()["has_avatar"] is True
                assert r_active.json()["avatar"]["id"] == avatar2_id

                # 5. Render animated GIF for face emoji 😂
                r_render = await client.post(
                    f"/api/v1/avatar/{avatar2_id}/render",
                    json={"face_emoji": "😂", "mouth_open": 0.7, "duration_ms": 700, "format": "gif"},
                )
                assert r_render.status_code == 200
                render_info = r_render.json()
                assert render_info["expression"] == "laugh"
                assert render_info["face_emoji"] == "😂"
                r_gif = await client.get(render_info["render_url"])
                assert r_gif.status_code == 200
                assert r_gif.content[:3] == b"GIF"

                # 6. Chat endpoint emits face_emoji + expression + cleaned_reply without reading emoji aloud
                mock_reply = "منور الدنيا يا فندم! مبسوط إني بتكلم معاك 😂"
                with patch("app.providers.llm.local_ollama.LocalOllamaProvider.generate", new_callable=AsyncMock) as mock_gen:
                    mock_gen.return_value = mock_reply
                    r_chat = await client.post(
                        "/api/v1/conversations/chat",
                        json={
                            "message": "إزيك يا نيبولا",
                            "session_id": "test-avatar-emoji-chat-001",
                            "return_audio": False,
                        },
                    )
                    assert r_chat.status_code == 200
                    chat_data = r_chat.json()
                    assert chat_data["face_emoji"] == "😂"
                    assert chat_data["expression"] == "laugh"
                    assert chat_data["emotion"] == "laugh"
                    assert "😂" not in chat_data["cleaned_reply"]
                    assert chat_data["avatar_action"]["speak_mouth"] is True
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_avatar_studio_ui_route_serves_html():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/avatar-ui")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")
        assert "/api/v1/avatar/list" in resp.text
        assert "GAGAvatar" in resp.text

