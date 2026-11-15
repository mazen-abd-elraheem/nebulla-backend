"""Unit tests for Face-Emoji Action Protocol and GAGAvatar Avatar Service."""

import base64
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.db.session import AsyncSessionLocal, init_db
from app.services.avatar.emoji_actions import (
    FACE_EMOJI_ACTIONS,
    extract_emoji_and_emotion,
    list_emoji_action_catalog,
    strip_emojis_for_speech,
)
from app.services.avatar.gagavatar_service import GAGAvatarService
from app.utils.masri_normalizer import clean_llm_output_for_speech


def _make_portrait_jpeg_bytes(color=(195, 165, 145)) -> bytes:
    """Create a valid RGB JPEG image buffer for avatar pipeline unit tests."""
    img = Image.new("RGB", (320, 320), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_strip_emojis_and_clean_speech_for_voicetut():
    raw = "أهلاً بيك يا صديقي! 😊 مبسوط إني معاك 😂 [happy]"
    assert strip_emojis_for_speech("سلام 👋 تمام 👍") == "سلام تمام"
    cleaned = clean_llm_output_for_speech(raw)
    assert "😊" not in cleaned
    assert "😂" not in cleaned
    assert "[happy]" not in cleaned
    assert "أهلاً" in cleaned or "اهلا" in cleaned or "بيك" in cleaned


def test_extract_emoji_and_emotion_mapping():
    laugh_spec = extract_emoji_and_emotion("هههه دي نكتة حلوة 😂")
    assert laugh_spec["expression"] == "laugh"
    assert laugh_spec["face_emoji"] == "😂"
    assert laugh_spec["mouth_preset"] == "open_laugh"
    assert laugh_spec["speak_mouth"] is True
    assert laugh_spec["flame_params"]["jaw"] > 0.3

    sad_spec = extract_emoji_and_emotion("للأسف الخبر مش كويس 😢")
    assert sad_spec["expression"] == "sad"
    assert sad_spec["face_emoji"] == "😢"
    assert sad_spec["ws_mood"] == "sad"

    # Backward compatibility for bracket tags used by existing LLM prompts/tests
    tag_spec = extract_emoji_and_emotion("أهلاً يا باشا! [happy] [wave]")
    assert tag_spec["expression"] == "happy"

    catalog = list_emoji_action_catalog()
    assert len(catalog) == len(FACE_EMOJI_ACTIONS)


@pytest.mark.asyncio
async def test_avatar_lifecycle_create_reject_recreate_approve_and_render(tmp_path):
    await init_db()
    svc = GAGAvatarService(output_dir=str(tmp_path / "avatars"))
    photo_bytes = _make_portrait_jpeg_bytes()

    async with AsyncSessionLocal() as db:
        # 1. Create draft #1 (stubbing face detector bbox cleanly so unit test is deterministic)
        with patch.object(svc, "_detect_face_and_landmarks", return_value=((80, 60, 240, 240), None)):
            draft1 = await svc.create_avatar_from_photo(
                image_bytes=photo_bytes,
                db=db,
                name="مازن",
                style="realistic",
                require_face=True,
            )

            assert draft1.id > 0
            assert draft1.status == "pending_review"
            assert draft1.is_active is False
            assert draft1.attempt_number == 1
            assert Path(draft1.avatar_preview_path).exists()

            with Image.open(draft1.avatar_preview_path) as im:
                assert im.size == (512, 512)

            # Sprites exist for core face emojis
            assert (Path(draft1.sprites_dir) / "happy.png").exists()
            assert (Path(draft1.sprites_dir) / "laugh.png").exists()
            assert (Path(draft1.sprites_dir) / "sad.png").exists()

            # 2. User is not satisfied -> recreate draft #2
            draft2 = await svc.recreate_avatar(
                avatar_id=draft1.id,
                db=db,
                style="studio_3d",
                reason="الإضاءة محتاجة تحسين",
                require_face=True,
            )
            await db.refresh(draft1)
            assert draft1.status == "rejected"
            assert draft1.is_active is False
            assert draft2.status == "pending_review"
            assert draft2.is_active is False
            assert draft2.attempt_number == 2
            assert draft2.style == "studio_3d"

            # 3. Approve draft #2 -> active approved avatar
            approved = await svc.approve_avatar(avatar_id=draft2.id, db=db)
            assert approved.status == "approved"
            assert approved.is_active is True

            # 4. Render expression GIF + mouth animation
            render_meta = await svc.render_avatar_animation(
                avatar=approved,
                expression_or_emoji="😂",
                mouth_open=0.75,
                duration_ms=800,
                output_format="gif",
            )
            assert render_meta["expression"] == "laugh"
            assert render_meta["face_emoji"] == "😂"
            render_path = Path(approved.avatar_preview_path).parent / "renders" / render_meta["filename"]
            assert render_path.exists()
            assert render_path.read_bytes()[:3] == b"GIF"


@pytest.mark.asyncio
async def test_avatar_remote_gagavatar_bridge_priority(tmp_path, monkeypatch):
    await init_db()
    svc = GAGAvatarService(output_dir=str(tmp_path / "avatars_remote"))
    photo_bytes = _make_portrait_jpeg_bytes()

    png_buf = io.BytesIO()
    Image.new("RGB", (512, 512), color=(40, 120, 200)).save(png_buf, format="PNG")
    b64_png = base64.b64encode(png_buf.getvalue()).decode("ascii")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "engine": "gagavatar_remote",
        "portrait_b64": b64_png,
        "sprites_b64": {"neutral": b64_png, "happy": b64_png, "laugh": b64_png},
        "landmarks": {"left_eye": [0.35, 0.40], "right_eye": [0.65, 0.40], "mouth": [0.50, 0.72]},
    }

    monkeypatch.setattr("app.services.avatar.gagavatar_service.settings.GAGAVATAR_SERVICE_URL", "http://fake-gpu:8090")

    with patch("app.services.avatar.gagavatar_service.httpx.AsyncClient") as mock_client_cls:
        client_inst = AsyncMock()
        client_inst.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__.return_value = client_inst

        async with AsyncSessionLocal() as db:
            profile = await svc.create_avatar_from_photo(
                image_bytes=photo_bytes,
                db=db,
                name="RemoteTest",
                require_face=False,
            )
            assert profile.engine == "gagavatar_remote"
            assert Path(profile.avatar_preview_path).exists()

