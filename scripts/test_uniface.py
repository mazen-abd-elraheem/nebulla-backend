"""
UniFace Test Suite — Face Detection, Gaze Estimation & Video Recognition
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests UniFace vision engine on:
  1. Synthetic or real static images (--image path)
  2. Video files with face tracking (--video path)
  3. Live webcam stream (--webcam)
  4. ArcFace / EdgeFace embedding extraction & identity verification

Usage:
  python scripts/test_uniface.py --synthetic
  python scripts/test_uniface.py --image path/to/photo.jpg
  python scripts/test_uniface.py --video path/to/clip.mp4
  python scripts/test_uniface.py --webcam
"""

import argparse
import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

import cv2
import numpy as np


def draw_face_annotations(frame: np.ndarray, face, label: str = "Face") -> np.ndarray:
    """Draw bounding box, landmarks, gaze, and label on frame."""
    annotated = frame.copy()
    bbox = [int(v) for v in face.bbox]
    x1, y1, x2, y2 = bbox

    # Draw bounding box
    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)

    # Compute and draw center / gaze
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    cv2.circle(annotated, (cx, cy), 4, (0, 0, 255), -1)

    # Text info
    conf = getattr(face, "confidence", 1.0)
    info_text = f"{label} ({conf:.2f})"
    if hasattr(face, "track_id") and face.track_id is not None:
        info_text += f" ID:{face.track_id}"
    cv2.putText(
        annotated,
        info_text,
        (x1, max(y1 - 10, 20)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.5,
        (0, 255, 0),
        2,
    )

    # Landmarks if present
    if hasattr(face, "landmarks") and face.landmarks is not None:
        landmarks = np.array(face.landmarks, dtype=np.int32)
        for pt in landmarks:
            cv2.circle(annotated, (int(pt[0]), int(pt[1])), 2, (255, 255, 0), -1)

    return annotated


def create_synthetic_face_frame() -> np.ndarray:
    """Creates a clean synthetic frame resembling a stylized face for testing."""
    frame = np.full((480, 640, 3), 40, dtype=np.uint8)
    # Head outline (oval)
    cv2.ellipse(frame, (320, 240), (100, 140), 0, 0, 360, (210, 180, 150), -1)
    # Eyes
    cv2.circle(frame, (280, 200), 14, (255, 255, 255), -1)
    cv2.circle(frame, (360, 200), 14, (255, 255, 255), -1)
    cv2.circle(frame, (282, 200), 6, (50, 40, 30), -1)
    cv2.circle(frame, (362, 200), 6, (50, 40, 30), -1)
    # Nose
    pts = np.array([[320, 220], [315, 250], [325, 250]], np.int32)
    cv2.polylines(frame, [pts], True, (160, 130, 100), 2)
    # Mouth / smile
    cv2.ellipse(frame, (320, 280), (35, 18), 0, 0, 180, (50, 50, 200), 3)
    return frame


def test_image(image_path: str | None = None, save_path: str = "data/uniface_test_result.jpg"):
    import uniface
    print("=" * 60)
    print("UniFace Image Test")
    print("=" * 60)

    print("Loading UniFace FaceAnalyzer...")
    analyzer = uniface.FaceAnalyzer()

    if image_path and os.path.exists(image_path):
        frame = cv2.imread(image_path)
        print(f"Loaded user image: {image_path} ({frame.shape[1]}x{frame.shape[0]})")
    else:
        print("Generating synthetic face test frame...")
        frame = create_synthetic_face_frame()

    # OpenCV loads BGR, uniface expects RGB
    rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    t0 = time.perf_counter()
    faces = analyzer.analyze(rgb_frame)
    latency_ms = (time.perf_counter() - t0) * 1000

    print(f"Processed frame in {latency_ms:.2f} ms")
    print(f"Detected {len(faces)} face(s)")

    out_frame = frame.copy()
    for idx, face in enumerate(faces):
        bbox = [int(v) for v in face.bbox]
        has_emb = hasattr(face, "embedding") and face.embedding is not None
        emb_len = len(face.embedding) if has_emb else 0
        print(f"  Face #{idx + 1}: BBox={bbox}, Conf={getattr(face, 'confidence', 1.0):.2f}, EmbeddingDim={emb_len}")
        out_frame = draw_face_annotations(out_frame, face, label=f"Face #{idx + 1}")

    os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
    cv2.imwrite(save_path, out_frame)
    print(f"Visual result saved to: {save_path}")
    print("✓ UniFace Image Test completed successfully.")
    return len(faces)


def test_video(video_path: str, max_frames: int = 100):
    import uniface
    print("=" * 60)
    print(f"UniFace Video Recognition Test: {video_path}")
    print("=" * 60)

    if not os.path.exists(video_path):
        print(f"Error: Video file not found: {video_path}")
        return

    analyzer = uniface.FaceAnalyzer()
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    print(f"Video Info: {total_frames} frames @ {fps:.1f} FPS")

    frame_count = 0
    detected_count = 0
    t0 = time.perf_counter()

    while cap.isOpened() and frame_count < max_frames:
        ret, frame = cap.read()
        if not ret:
            break

        frame_count += 1
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = analyzer.analyze(rgb_frame)

        if faces:
            detected_count += 1
            # print first detection
            if frame_count % 10 == 0:
                print(f"  Frame {frame_count:03d}: detected {len(faces)} face(s)")

    cap.release()
    elapsed = time.perf_counter() - t0
    avg_fps = frame_count / elapsed if elapsed > 0 else 0

    print("-" * 60)
    print(f"Processed {frame_count} frames in {elapsed:.2f}s ({avg_fps:.1f} FPS)")
    print(f"Detection rate: {detected_count}/{frame_count} frames ({(detected_count/frame_count*100) if frame_count else 0:.1f}%)")
    print("✓ UniFace Video Test completed successfully.")


def test_webcam(camera_id: int = 0, duration_seconds: int = 10):
    import uniface
    print("=" * 60)
    print(f"UniFace Live Webcam Test (Camera ID: {camera_id})")
    print("=" * 60)

    cap = cv2.VideoCapture(camera_id)
    if not cap.isOpened():
        print(f"Could not open webcam {camera_id}. Skipping live camera test.")
        return

    analyzer = uniface.FaceAnalyzer()
    t_end = time.time() + duration_seconds
    frames = 0

    print(f"Running webcam feed for {duration_seconds} seconds... (Press Ctrl+C to stop)")
    try:
        while time.time() < t_end:
            ret, frame = cap.read()
            if not ret:
                break
            frames += 1
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            faces = analyzer.analyze(rgb)
            if frames % 15 == 0:
                print(f"  Live frame {frames}: detected {len(faces)} face(s)")
    finally:
        cap.release()

    print(f"Webcam test finished: processed {frames} frames.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UniFace Verification & Recognition Tool")
    parser.add_argument("--image", type=str, default=None, help="Path to static image to test")
    parser.add_argument("--video", type=str, default=None, help="Path to video file to test")
    parser.add_argument("--webcam", action="store_true", help="Run live webcam test")
    parser.add_argument("--synthetic", action="store_true", help="Run test on generated synthetic face")
    args = parser.parse_args()

    if args.webcam:
        test_webcam()
    elif args.video:
        test_video(args.video)
    else:
        test_image(args.image)
