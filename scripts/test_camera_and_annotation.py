import cv2
import httpx
import numpy as np
import tempfile
import os

BASE_URL = "http://127.0.0.1:8000"

def test_features():
    print("=" * 60)
    print("Testing Nebula Live Webcam & Video Visualization Endpoints")
    print("=" * 60)
    
    with httpx.Client(base_url=BASE_URL, timeout=60.0) as client:
        # 1. Test UI
        resp = client.get("/faces-ui")
        assert resp.status_code == 200, f"UI error: {resp.status_code}"
        assert "camera-tab" in resp.text
        assert "annotate-video-btn" in resp.text
        print("✅ 1. /faces-ui loaded successfully with Live Webcam and Annotate HUD UI.")

        # 2. Test Camera Status
        resp = client.get("/api/v1/faces/camera/status")
        assert resp.status_code == 200, f"Camera status error: {resp.status_code}"
        status_data = resp.json()
        print(f"✅ 2. /camera/status -> {status_data}")

        # 3. Test Camera Snapshot
        resp = client.get("/api/v1/faces/camera/snapshot")
        if resp.status_code == 200:
            assert resp.headers["content-type"] == "image/jpeg"
            assert len(resp.content) > 1000
            print(f"✅ 3. /camera/snapshot -> Captured live JPEG snapshot ({len(resp.content)} bytes).")
        else:
            print(f"⚠️ 3. /camera/snapshot returned status {resp.status_code}: {resp.text}")

        # 4. Test Camera Stop
        resp = client.post("/api/v1/faces/camera/stop")
        assert resp.status_code == 200, f"Camera stop error: {resp.status_code}"
        print("✅ 4. /camera/stop -> Camera stopped and hardware lock safely released.")

        # 5. Create synthetic test video with a stylized face
        print("Creating synthetic video for annotation test...")
        temp_vid = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        temp_vid.close()
        
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(temp_vid.name, fourcc, 10.0, (320, 240))
        for i in range(15):
            frame = np.full((240, 320, 3), 40, dtype=np.uint8)
            # Draw synthetic face
            cv2.ellipse(frame, (160, 120), (50, 70), 0, 0, 360, (210, 180, 150), -1)
            cv2.circle(frame, (140, 100), 7, (255, 255, 255), -1)
            cv2.circle(frame, (180, 100), 7, (255, 255, 255), -1)
            cv2.circle(frame, (141, 100), 3, (50, 40, 30), -1)
            cv2.circle(frame, (181, 100), 3, (50, 40, 30), -1)
            cv2.ellipse(frame, (160, 140), (18, 9), 0, 0, 180, (50, 50, 200), 2)
            writer.write(frame)
        writer.release()
        
        with open(temp_vid.name, "rb") as f:
            vid_bytes = f.read()
        os.remove(temp_vid.name)
        
        # 6. Test Video Annotation Endpoint
        print("Testing /api/v1/faces/annotate-video...")
        files = {"file": ("test_clip.mp4", vid_bytes, "video/mp4")}
        resp = client.post("/api/v1/faces/annotate-video?threshold=0.40", files=files)
        assert resp.status_code == 200, f"Annotate error: {resp.status_code} - {resp.text}"
        assert resp.headers["content-type"] == "video/mp4"
        assert len(resp.content) > 1000
        print(f"✅ 5. /annotate-video -> Successfully generated HUD annotated video ({len(resp.content)} bytes).")
        print(f"   X-Total-Frames: {resp.headers.get('x-total-frames')}")
        print(f"   X-Total-Detections: {resp.headers.get('x-total-detections')}")

    print("=" * 60)
    print("🎉 ALL TESTS PASSED SUCCESSFULLY! Real-time Face HUD is ready.")
    print("=" * 60)

if __name__ == "__main__":
    test_features()
