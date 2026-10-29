"""Integration tests for Face Registration and UniFace Vision Service endpoints."""

import io
import pytest
from httpx import AsyncClient, ASGITransport
from PIL import Image

from app.main import app
from app.core.config import settings


@pytest.fixture
def auth_headers():
    return {"X-API-Key": settings.PAIRING_SECRET}


def _create_test_image_bytes() -> bytes:
    """Create a minimal 100x100 JPEG test image."""
    img = Image.new("RGB", (100, 100), color=(200, 150, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.mark.asyncio
async def test_face_api_lifecycle(auth_headers):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Get current face info
        res_current = await client.get("/api/v1/faces/current", headers=auth_headers)
        assert res_current.status_code == 200
        assert "detected" in res_current.json()

        # 2. List registered faces (should return a list)
        res_list = await client.get("/api/v1/faces", headers=auth_headers)
        assert res_list.status_code == 200
        assert "faces" in res_list.json()

        # 3. Register a face with a test image (mock embedding extraction for headless CI)
        from unittest.mock import patch
        img_bytes = _create_test_image_bytes()
        files = {"file": ("test_person.jpg", img_bytes, "image/jpeg")}
        data = {"name": "TestPerson"}
        with patch("app.services.vision.face_service.FaceService.extract_embedding_sync", return_value=[0.05] * 128):
            res_reg = await client.post("/api/v1/faces/register", data=data, files=files, headers=auth_headers)
        assert res_reg.status_code == 200

        # 4. Verify listed
        res_list2 = await client.get("/api/v1/faces", headers=auth_headers)
        assert res_list2.status_code == 200
        names = [f["name"] for f in res_list2.json()["faces"]]
        assert "TestPerson" in names

        # 5. Clean up / delete test face
        res_del = await client.delete("/api/v1/faces/TestPerson", headers=auth_headers)
        assert res_del.status_code == 200
