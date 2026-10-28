"""
Unit & integration tests for the UniFace face recognition, comparison,
storage, and video extraction pipeline.
"""

import io
import os
import tempfile
import cv2
import numpy as np
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.session import Base, get_db
from app.main import app
from app.models.face_profile import FaceProfile
from app.services.vision.face_service import FaceService


@pytest_asyncio.fixture
async def async_session():
    """Create an isolated in-memory SQLite database session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()



def create_synthetic_face_image() -> bytes:
    """Generate a synthetic image with a simple drawn face shape for tests."""
    img = np.ones((300, 300, 3), dtype=np.uint8) * 200
    # Head circle
    cv2.circle(img, (150, 150), 80, (180, 190, 220), -1)
    # Eyes
    cv2.circle(img, (120, 130), 10, (50, 50, 50), -1)
    cv2.circle(img, (180, 130), 10, (50, 50, 50), -1)
    # Mouth
    cv2.ellipse(img, (150, 180), (30, 15), 0, 0, 180, (40, 40, 180), 3)

    _, buf = cv2.imencode(".jpg", img)
    return buf.tobytes()


def create_synthetic_video(duration_sec: float = 1.0, fps: float = 10.0) -> bytes:
    """Generate a synthetic MP4 video in memory."""
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_vid:
        temp_path = temp_vid.name

    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(temp_path, fourcc, fps, (200, 200))
        num_frames = int(duration_sec * fps)
        for i in range(num_frames):
            frame = np.ones((200, 200, 3), dtype=np.uint8) * (150 + i * 5)
            # Draw moving element
            cv2.circle(frame, (100 + i * 2, 100), 40, (100, 150, 200), -1)
            out.write(frame)
        out.release()

        with open(temp_path, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


@pytest.mark.asyncio
async def test_face_profile_serialization():
    """Test embedding conversion from vector to binary and back."""
    vec = np.random.randn(512).astype(np.float32)
    profile = FaceProfile(name="Test User", embedding=vec)

    recovered = profile.get_embedding_vector()
    assert recovered is not None
    assert recovered.shape == (512,)
    assert np.allclose(vec, recovered, atol=1e-5)


@pytest.mark.asyncio
async def test_cosine_similarity():
    """Test cosine similarity math."""
    v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v2 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    v3 = np.array([0.0, 1.0, 0.0], dtype=np.float32)

    sim_identical = FaceService._cosine_similarity(v1, v2)
    sim_orthogonal = FaceService._cosine_similarity(v1, v3)

    assert pytest.approx(sim_identical, 0.001) == 1.0
    assert pytest.approx(sim_orthogonal, 0.001) == 0.0


@pytest.mark.asyncio
async def test_laplacian_sharpness():
    """Test Laplacian variance sharpness calculator."""
    # Blurry image (flat)
    flat = np.ones((50, 50, 3), dtype=np.uint8) * 128
    sharpness_flat = FaceService._compute_laplacian_sharpness(flat)
    assert sharpness_flat == 0.0

    # Sharp image with edges
    sharp = np.zeros((50, 50, 3), dtype=np.uint8)
    sharp[::2, ::2] = 255
    sharpness_high = FaceService._compute_laplacian_sharpness(sharp)
    assert sharpness_high > 10.0


@pytest.mark.asyncio
async def test_faces_list_and_delete_endpoints(async_session: AsyncSession):
    """Test GET /api/v1/faces/ and DELETE /api/v1/faces/{name}."""
    # Add a mock profile
    p = FaceProfile(name="Ahmed Test", embedding=np.zeros(512, dtype=np.float32))
    async_session.add(p)
    await async_session.commit()

    async def override_get_db():
        yield async_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. List faces
            res = await client.get("/api/v1/faces/")
            assert res.status_code == 200
            data = res.json()
            assert "profiles" in data
            names = [item["name"] for item in data["profiles"]]
            assert "Ahmed Test" in names

            # 2. Get specific profile
            res_get = await client.get("/api/v1/faces/Ahmed Test")
            assert res_get.status_code == 200
            assert res_get.json()["name"] == "Ahmed Test"

            # 3. Delete profile
            res_del = await client.delete("/api/v1/faces/Ahmed Test")
            assert res_del.status_code == 200
            assert "deleted" in res_del.json()["message"]
    finally:
        app.dependency_overrides.pop(get_db, None)



@pytest.mark.asyncio
async def test_compare_endpoint_validation():
    """Test validation on compare endpoint with empty or invalid images."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Compare 2 synthetic blank images (no faces)
        img_bytes = create_synthetic_face_image()
        files = {
            "image1": ("img1.jpg", img_bytes, "image/jpeg"),
            "image2": ("img2.jpg", img_bytes, "image/jpeg"),
        }
        res = await client.post("/api/v1/faces/compare", files=files)
        # Should return 400 because synthetic drawing does not have a real human face or return similarity
        assert res.status_code in (200, 400)


@pytest.mark.asyncio
async def test_video_extraction_endpoint():
    """Test POST /api/v1/faces/extract-from-video endpoint."""
    video_bytes = create_synthetic_video(duration_sec=0.5, fps=10.0)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("test.mp4", video_bytes, "video/mp4")}
        res = await client.post(
            "/api/v1/faces/extract-from-video?sample_interval_sec=0.2&max_faces=5",
            files=files,
        )
        assert res.status_code == 200
        data = res.json()
        assert "extracted_count" in data
        assert "faces" in data


@pytest.mark.asyncio
async def test_recognize_from_video_endpoint():
    """Test POST /api/v1/faces/recognize-from-video endpoint."""
    video_bytes = create_synthetic_video(duration_sec=0.5, fps=10.0)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {"file": ("test.mp4", video_bytes, "video/mp4")}
        res = await client.post(
            "/api/v1/faces/recognize-from-video?sample_interval_sec=0.2&max_faces=5",
            files=files,
        )
        assert res.status_code == 200
        data = res.json()
        assert "total_faces_analyzed" in data
        assert "identified_persons" in data
        assert "timeline" in data


@pytest.mark.asyncio
async def test_compare_video_to_image_endpoint():
    """Test POST /api/v1/faces/compare-video-to-image endpoint."""
    video_bytes = create_synthetic_video(duration_sec=0.5, fps=10.0)
    img_bytes = create_synthetic_face_image()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        files = {
            "video": ("test.mp4", video_bytes, "video/mp4"),
            "image": ("face.jpg", img_bytes, "image/jpeg"),
        }
        res = await client.post(
            "/api/v1/faces/compare-video-to-image?sample_interval_sec=0.2",
            files=files,
        )
        assert res.status_code in (200, 400)

