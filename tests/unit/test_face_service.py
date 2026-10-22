import pytest
import asyncio
from unittest.mock import MagicMock, patch
from app.services.vision.face_service import FaceService, FaceResult

@pytest.fixture
def mock_uniface():
    mock_uf = MagicMock()
    # Mock FaceDetector
    mock_detector = MagicMock()
    mock_face = MagicMock()
    mock_face.bbox = [0, 0, 100, 100]
    mock_face.score = 0.95
    mock_detector.detect.return_value = [mock_face]
    
    mock_uf.FaceDetector.return_value = mock_detector
    
    # Mock recognizer
    mock_recognizer_class = MagicMock()
    mock_uf.recognition.ArcFace = mock_recognizer_class
    
    with patch.dict("sys.modules", {"uniface": mock_uf}):
        yield mock_uf

@pytest.mark.asyncio
async def test_process_frame_with_recognition(mock_uniface):
    service = FaceService()
    service._known_embeddings = {"user_recognized": [0.1] * 128}
    
    # Needs to be a valid jpeg bytes so PIL can open it
    # We will patch PIL.Image.open and numpy.array to avoid needing real image bytes
    with patch("PIL.Image.open") as mock_img_open, \
         patch("numpy.array") as mock_np_array, \
         patch("app.services.vision.face_service.manager.send_to_phone") as mock_send:
             
        mock_img = MagicMock()
        mock_img_open.return_value.convert.return_value = mock_img
        
        # mock shape for h, w
        mock_array = MagicMock()
        mock_array.shape = (240, 320, 3)
        mock_np_array.return_value = mock_array
        
        dummy_jpeg = b"dummy_data"
        result = await service.process_frame(dummy_jpeg)
        
        assert result is not None
        assert result.detected is True
        assert result.face_id == "user_recognized"
        
        mock_send.assert_called()
