import io
import time
import pytest
import numpy as np
import cv2
from unittest.mock import AsyncMock, MagicMock, patch
from app.models.face_profile import FaceProfile
from app.services.vision.face_service import FaceService, FaceResult


@pytest.fixture
def mock_uniface():
    mock_uf = MagicMock()
    mock_analyzer = MagicMock()
    mock_face = MagicMock()
    mock_face.bbox = [0, 0, 100, 100]
    mock_face.confidence = 0.95
    mock_face.embedding = np.array([0.1] * 128, dtype=np.float32)
    mock_analyzer.analyze.return_value = [mock_face]
    mock_uf.FaceAnalyzer.return_value = mock_analyzer

    with patch.dict("sys.modules", {"uniface": mock_uf}):
        yield mock_uf


@pytest.mark.asyncio
async def test_process_frame_with_recognition(mock_uniface):
    service = FaceService()
    service._analyzer = mock_uniface.FaceAnalyzer()
    service._known_embeddings = {"user_recognized": np.array([0.1] * 128, dtype=np.float32)}

    with patch("PIL.Image.open") as mock_img_open, \
         patch("numpy.array") as mock_np_array, \
         patch("app.services.vision.face_service.manager.send_to_phone") as mock_send:

        mock_img = MagicMock()
        mock_img_open.return_value.convert.return_value = mock_img

        mock_array = MagicMock()
        mock_array.shape = (240, 320, 3)
        mock_np_array.return_value = mock_array

        dummy_jpeg = b"dummy_data"
        result = await service.process_frame(dummy_jpeg)

        assert result is not None
        assert result.detected is True
        assert result.face_id == "user_recognized"

        mock_send.assert_called()


@pytest.mark.asyncio
async def test_process_frame_no_face(mock_uniface):
    service = FaceService()
    analyzer = mock_uniface.FaceAnalyzer()
    analyzer.analyze.return_value = []
    service._analyzer = analyzer

    with patch("app.services.vision.face_service.FaceService._decode_image") as mock_decode:
        mock_decode.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        result = await service.process_frame(b"dummy")
        assert result is None


@pytest.mark.asyncio
async def test_process_frame_disabled():
    service = FaceService()
    service._analyzer = "disabled"
    result = await service.process_frame(b"dummy")
    assert result is None


def test_decode_image_valid_and_invalid():
    # Valid synthetic image
    img = np.ones((50, 50, 3), dtype=np.uint8) * 120
    _, buf = cv2.imencode(".jpg", img)
    decoded = FaceService._decode_image(buf.tobytes())
    assert decoded is not None
    assert decoded.shape == (50, 50, 3)

    # Invalid bytes
    decoded_invalid = FaceService._decode_image(b"invalid_corrupt_data")
    assert decoded_invalid is None


def test_crop_face():
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    bbox = [50, 50, 150, 150]
    cropped = FaceService._crop_face(img, bbox, margin_pct=0.2)
    assert cropped is not None
    assert cropped.shape[0] > 0 and cropped.shape[1] > 0


def test_calculate_match_percentage():
    # Edge cases
    assert FaceService._calculate_match_percentage(-0.5) == 0.0
    assert FaceService._calculate_match_percentage(0.0) == 0.0
    assert FaceService._calculate_match_percentage(1.0) == 100.0
    assert FaceService._calculate_match_percentage(1.2) == 100.0

    # Below threshold (0.40)
    pct_low = FaceService._calculate_match_percentage(0.2, threshold=0.40)
    assert 0.0 < pct_low < 50.0

    # At threshold (0.40) -> 93.0%
    pct_thresh = FaceService._calculate_match_percentage(0.40, threshold=0.40)
    assert pytest.approx(pct_thresh, 0.1) == 93.0

    # Genuine match around 0.497 -> ~99.11%
    pct_ahmed = FaceService._calculate_match_percentage(0.497, threshold=0.40)
    assert 98.5 <= pct_ahmed <= 99.5

    # High match (0.70) -> 100.0%
    pct_high = FaceService._calculate_match_percentage(0.70, threshold=0.40)
    assert pct_high == 100.0


def test_get_current_face_info():
    service = FaceService()

    # Case 1: No previous detection
    info = service.get_current_face_info()
    assert info["detected"] is False
    assert info["is_recent"] is False
    assert info["face_id"] is None

    # Case 2: Recent detection
    service.last_result = FaceResult(detected=True, face_id="Alice", confidence=0.98)
    service.last_detection_time = time.time()
    info = service.get_current_face_info()
    assert info["detected"] is True
    assert info["is_recent"] is True
    assert info["face_id"] == "Alice"
    assert info["confidence"] == 0.98

    # Case 3: Stale detection (> 20 seconds ago)
    service.last_detection_time = time.time() - 30.0
    info_stale = service.get_current_face_info()
    assert info_stale["detected"] is True
    assert info_stale["is_recent"] is False


def test_match_embedding():
    service = FaceService()
    target_vec = np.array([1.0, 0.0, 0.0], dtype=np.float32)

    # Empty known embeddings
    best_name, sim = service._match_embedding(target_vec)
    assert best_name is None
    assert sim == 0.0

    # With known embeddings
    service._known_embeddings = {
        "UserA": np.array([1.0, 0.0, 0.0], dtype=np.float32),
        "UserB": np.array([0.0, 1.0, 0.0], dtype=np.float32),
    }
    best_name, sim = service._match_embedding(target_vec)
    assert best_name == "UserA"
    assert pytest.approx(sim, 0.01) == 1.0


@pytest.mark.asyncio
async def test_reload_known_faces():
    service = FaceService()
    mock_db = AsyncMock()

    vec = np.ones(512, dtype=np.float32)
    profile = FaceProfile(name="TestPerson", embedding=vec)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [profile]
    mock_db.execute.return_value = mock_result

    count = await service.reload_known_faces(mock_db)
    assert count == 1
    assert "TestPerson" in service._known_embeddings
    # Vector should be normalized
    norm = np.linalg.norm(service._known_embeddings["TestPerson"])
    assert pytest.approx(norm, 0.01) == 1.0


def test_annotate_frame():
    service = FaceService()
    service._known_embeddings = {"UserKnown": np.ones(128, dtype=np.float32)}

    # Mock faces: one known, one unknown
    face_known = MagicMock()
    face_known.bbox = [20, 20, 80, 80]
    face_known.confidence = 0.96
    face_known.embedding = np.ones(128, dtype=np.float32)
    face_known.landmarks = np.array([[30, 40], [50, 40], [40, 50], [35, 65], [45, 65]], dtype=np.int32)

    face_unknown = MagicMock()
    face_unknown.bbox = [100, 100, 160, 160]
    face_unknown.confidence = 0.88
    face_unknown.embedding = np.zeros(128, dtype=np.float32)
    face_unknown.landmarks = None

    mock_analyzer = MagicMock()
    mock_analyzer.analyze.return_value = [face_known, face_unknown]
    service._analyzer = mock_analyzer

    frame = np.zeros((300, 300, 3), dtype=np.uint8)
    annotated, detections = service.annotate_frame(frame, threshold=0.40, fps=25.0, draw_landmarks=True)

    assert annotated is not None
    assert annotated.shape == frame.shape
    assert len(detections) == 2

    # Check known face detection
    d_known = next(d for d in detections if d["is_known"])
    assert d_known["name"] == "UserKnown"
    assert d_known["match_percentage"] > 90.0

    # Check unknown face detection
    d_unknown = next(d for d in detections if not d["is_known"])
    assert d_unknown["name"] is None
    assert d_unknown["confidence"] == 0.88


@pytest.mark.asyncio
async def test_recognize_faces(mock_uniface):
    service = FaceService()
    service._analyzer = mock_uniface.FaceAnalyzer()
    service._known_embeddings = {"RecognizedAlice": np.array([0.1] * 128, dtype=np.float32)}

    # Synthetic image
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)

    results = await service.recognize_faces(buf.tobytes(), threshold=0.40)
    assert len(results) == 1
    assert results[0]["name"] == "RecognizedAlice"
    assert results[0]["is_known"] is True
    assert results[0]["match_percentage"] > 90.0


@pytest.mark.asyncio
async def test_compare_faces(mock_uniface):
    service = FaceService()
    service._analyzer = mock_uniface.FaceAnalyzer()

    img = np.zeros((200, 200, 3), dtype=np.uint8)
    _, buf = cv2.imencode(".jpg", img)
    img_bytes = buf.tobytes()

    res = await service.compare_faces(img_bytes, img_bytes, threshold=0.40)
    assert res["is_match"] is True
    assert res["similarity"] > 0.99
    assert res["match_percentage"] == 100.0


@pytest.mark.asyncio
async def test_delete_face():
    service = FaceService()
    service._known_embeddings = {"PersonToDelete": np.zeros(128, dtype=np.float32)}

    mock_db = AsyncMock()
    mock_profile = FaceProfile(name="PersonToDelete", photo_path=None)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_profile
    mock_db.execute.return_value = mock_result

    success = await service.delete_face("PersonToDelete", mock_db)
    assert success is True
    assert "PersonToDelete" not in service._known_embeddings

    # Deleting non-existent person
    mock_result.scalar_one_or_none.return_value = None
    not_found = await service.delete_face("NonExistent", mock_db)
    assert not_found is False


