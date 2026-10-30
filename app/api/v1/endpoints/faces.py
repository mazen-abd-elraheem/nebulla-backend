"""
Face Management & Vision API Endpoints.
Provides REST APIs for:
  - Face registration (from image or video)
  - Face recognition / Person identification (1:N matching)
  - Face verification / Image-to-image comparison (1:1 matching)
  - Video face extraction (selecting the clearest face shots from video)
  - Face profile listing and photo serving
  - Live face detection status
"""

import asyncio
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_current_user, get_optional_user
from app.db.session import get_db
from app.models.face_profile import FaceProfile
from app.services.vision.camera_streamer import get_camera_streamer
from app.websocket.handlers import _get_face_service

router = APIRouter()

# ──────────────────────────────────────────────────────────────────────────────
# 1. Registration (تسجيل وحفظ الأشخاص)
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/register",
    summary="Register a person with a photo",
    description="Upload a photo of a person to detect their face, save their profile, and extract their 512-D embedding.",
    status_code=status.HTTP_200_OK,
)
async def register_face(
    name: str = Form(..., description="Full name or identifier of the person"),
    file: UploadFile = File(..., description="Image file (JPEG/PNG) containing the person's face"),
    db: AsyncSession = Depends(get_db),
    _user: Optional[str] = Depends(get_optional_user),
):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file received.")

    face_service = _get_face_service()
    await face_service.ensure_db_loaded(db)

    try:
        result = await face_service.register_face_from_image(name=name, image_bytes=image_bytes, db=db)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register face: {str(e)}")


@router.post(
    "/register-from-video",
    summary="Register a person from a video",
    description="Upload a video of a person. The system automatically inspects all frames, selects the sharpest/clearest face shot, and registers them.",
    status_code=status.HTTP_201_CREATED,
)
async def register_face_from_video(
    name: str = Form(..., description="Full name or identifier of the person"),
    file: UploadFile = File(..., description="Video file (MP4/AVI/MOV/MKV)"),
    sample_interval_sec: float = Form(0.5, description="Interval in seconds between analyzed frames"),
    db: AsyncSession = Depends(get_db),
):
    video_bytes = await file.read()
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Empty video file received.")

    face_service = _get_face_service()
    await face_service.ensure_db_loaded(db)

    try:
        result = await face_service.register_face_from_video(
            name=name,
            video_bytes=video_bytes,
            db=db,
            sample_interval_sec=sample_interval_sec,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register face from video: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# 2. Person Identification / Recognition (تعريف الأشخاص)
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/recognize",
    summary="Identify people in an image",
    description="Detect all faces in an uploaded photo and identify each person by comparing them with all registered face profiles.",
)
async def recognize_people(
    file: UploadFile = File(..., description="Image file containing one or more people"),
    threshold: float = Query(0.40, ge=0.0, le=1.0, description="Similarity threshold for positive identification (default: 0.40)"),
    db: AsyncSession = Depends(get_db),
):
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file received.")

    face_service = _get_face_service()
    await face_service.ensure_db_loaded(db)

    faces = await face_service.recognize_faces(image_bytes=image_bytes, threshold=threshold)
    return {
        "detected_count": len(faces),
        "threshold": threshold,
        "faces": faces,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 3. Face Comparison / Verification (المقارنة بالصور 1:1)
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/compare",
    summary="Compare two face images (1:1 Verification)",
    description="Upload two images to compare the primary faces and determine whether they belong to the same person.",
)
async def compare_two_faces(
    image1: UploadFile = File(..., description="First image file"),
    image2: UploadFile = File(..., description="Second image file"),
    threshold: float = Query(0.40, ge=0.0, le=1.0, description="Match decision threshold (default: 0.40)"),
):
    img1_bytes = await image1.read()
    img2_bytes = await image2.read()

    if not img1_bytes or not img2_bytes:
        raise HTTPException(status_code=400, detail="Both image files are required for comparison.")

    face_service = _get_face_service()
    result = await face_service.compare_faces(img1_bytes=img1_bytes, img2_bytes=img2_bytes, threshold=threshold)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


# ──────────────────────────────────────────────────────────────────────────────
# 4. Video Face Extraction (واختار الصور من الفيديوهات)
# ──────────────────────────────────────────────────────────────────────────────

@router.post(
    "/extract-from-video",
    summary="Extract and select best face images from video",
    description="Upload a video to scan frames, calculate sharpness/clarity (Laplacian variance), and extract the top clearest face crops with timestamps.",
)
async def extract_faces_from_video(
    file: UploadFile = File(..., description="Video file (MP4, AVI, MOV, etc.)"),
    sample_interval_sec: float = Query(1.0, ge=0.1, le=10.0, description="Sampling interval in seconds between inspected frames"),
    min_confidence: float = Query(0.60, ge=0.1, le=1.0, description="Minimum face detection confidence score"),
    max_faces: int = Query(10, ge=1, le=50, description="Maximum number of highest-quality face crops to return"),
):
    video_bytes = await file.read()
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Empty video file received.")

    face_service = _get_face_service()
    faces = await face_service.extract_best_faces_from_video(
        video_bytes=video_bytes,
        sample_interval_sec=sample_interval_sec,
        min_confidence=min_confidence,
        max_faces=max_faces,
    )

    return {
        "extracted_count": len(faces),
        "faces": faces,
    }


@router.post(
    "/recognize-from-video",
    summary="Identify people in a video and get match percentages (التعرف على الأشخاص ونسبة التطابق في الفيديو)",
    description=(
        "Upload a video file (MP4, MOV, AVI). The system scans frames, detects faces, "
        "identifies them against all registered persons, and calculates the exact biometric match percentage "
        "and timestamps where they appear."
    ),
)
async def recognize_people_from_video(
    file: UploadFile = File(..., description="Video file (MP4, MOV, AVI, etc.)"),
    threshold: float = Query(0.40, ge=0.0, le=1.0, description="Similarity threshold for positive identification (default: 0.40)"),
    sample_interval_sec: float = Query(0.5, ge=0.1, le=5.0, description="Interval in seconds between analyzed frames"),
    min_confidence: float = Query(0.60, ge=0.1, le=1.0, description="Minimum face detection confidence score"),
    max_faces: int = Query(30, ge=1, le=100, description="Maximum number of face detections to analyze"),
    db: AsyncSession = Depends(get_db),
):
    video_bytes = await file.read()
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Empty video file received.")

    face_service = _get_face_service()
    await face_service.ensure_db_loaded(db)

    result = await face_service.recognize_faces_from_video(
        video_bytes=video_bytes,
        threshold=threshold,
        sample_interval_sec=sample_interval_sec,
        min_confidence=min_confidence,
        max_faces=max_faces,
    )
    return result


@router.post(
    "/compare-video-to-image",
    summary="Compare video to reference image (مقارنة فيديو مع صورة مباشرة وحساب نسبة التطابق)",
    description=(
        "Upload a video and a reference photo. The system checks if the person in the photo appears "
        "in the video and returns whether it's a match, the highest match percentage, and timestamp."
    ),
)
async def compare_video_to_image(
    video: UploadFile = File(..., description="Video file to search inside"),
    image: UploadFile = File(..., description="Reference photo of the person to find"),
    threshold: float = Query(0.40, ge=0.0, le=1.0, description="Match decision threshold (default: 0.40)"),
    sample_interval_sec: float = Query(0.5, ge=0.1, le=5.0, description="Sampling interval in seconds"),
):
    video_bytes = await video.read()
    image_bytes = await image.read()

    if not video_bytes or not image_bytes:
        raise HTTPException(status_code=400, detail="Both video and reference image are required.")

    face_service = _get_face_service()
    result = await face_service.compare_video_to_image(
        video_bytes=video_bytes,
        image_bytes=image_bytes,
        threshold=threshold,
        sample_interval_sec=sample_interval_sec,
    )

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return result


# ──────────────────────────────────────────────────────────────────────────────
# 5. Profiles Management (التخزين والإدارة)
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/",
    summary="List all registered face profiles",
    description="Retrieve all registered persons stored in the database.",
)
async def list_registered_faces(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FaceProfile).order_by(FaceProfile.name))
    profiles = result.scalars().all()
    face_list = [
        {
            "id": p.id,
            "name": p.name,
            "photo_path": p.photo_path,
            "photo_url": f"/api/v1/faces/{p.name}/photo" if p.photo_path else None,
            "created_at": p.created_at.isoformat() if p.created_at else None,
        }
        for p in profiles
    ]

    return {
        "count": len(profiles),
        "profiles": face_list,
        "faces": face_list,
    }


@router.get("/current", summary="Get live face detection and recognition status")
async def get_current_face(
    _user: Optional[str] = Depends(get_optional_user),
):
    face_service = _get_face_service()
    return face_service.get_current_face_info()


# ──────────────────────────────────────────────────────────────────────────────
# 5. Real-Time Camera Stream & Video Visualization (البث المباشر ورسم الوجوه)
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/live-feed",
    summary="Live Laptop Camera Stream with Real-time Face HUD (بث كاميرا اللاب المباشر)",
    description=(
        "Streams real-time video directly from the laptop webcam using MJPEG. "
        "Every frame is analyzed by UniFace to detect faces, identify registered persons, "
        "and draw high-tech HUD bounding boxes, names, match %, and 5-point facial landmarks."
    ),
)
async def live_camera_feed(
    camera_index: int = Query(0, ge=0, le=10, description="Webcam device index (default: 0)"),
    db: AsyncSession = Depends(get_db),
):
    face_service = _get_face_service()
    await face_service.ensure_db_loaded(db)
    streamer = get_camera_streamer()
    streamer.camera_index = camera_index
    try:
        return StreamingResponse(
            streamer.get_stream(),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start camera feed: {str(e)}")


@router.get(
    "/camera/devices",
    summary="List available camera devices (كشف الكاميرات المتصلة بالجهاز)",
    description="Probes and returns all currently accessible physical camera devices.",
)
async def get_camera_devices():
    streamer = get_camera_streamer()
    return streamer.get_available_cameras()


@router.get(
    "/camera/status",
    summary="Get webcam streaming status (حالة الكاميرا وعدد المشاهدين)",
    description="Check whether the laptop webcam is currently streaming, active viewers count, and live FPS.",
)
async def get_camera_status():
    streamer = get_camera_streamer()
    return streamer.get_status()


@router.post(
    "/camera/stop",
    summary="Stop camera and release hardware lock (إيقاف الكاميرا وفصلها)",
    description="Immediately stops the laptop webcam capture and releases the camera hardware.",
)
async def stop_camera():
    streamer = get_camera_streamer()
    streamer.stop()
    return {"message": "Camera stopped successfully and hardware released.", "status": streamer.get_status()}


@router.get(
    "/camera/snapshot",
    summary="Capture snapshot from webcam (التقاط صورة فورية من الكاميرا)",
    description="Returns an instant high-resolution JPEG snapshot from the laptop webcam with face HUD.",
)
async def get_camera_snapshot(db: AsyncSession = Depends(get_db)):
    face_service = _get_face_service()
    await face_service.ensure_db_loaded(db)
    streamer = get_camera_streamer()
    jpeg_bytes = streamer.get_snapshot()
    if not jpeg_bytes:
        raise HTTPException(status_code=500, detail="Failed to capture snapshot from webcam.")
    return Response(content=jpeg_bytes, media_type="image/jpeg")


@router.post(
    "/annotate-video",
    summary="Annotate Video with Face HUD (رسم الوجوه ونسب التطابق وتصدير الفيديو)",
    description=(
        "Upload a video file (MP4, MOV, AVI). The system renders the comprehensive high-tech HUD "
        "(bounding boxes, registered identities, match %, landmarks, and timeline) onto every frame, "
        "transcodes it to web-compatible H.264 MP4, and returns the downloadable and playable video file."
    ),
)
async def annotate_video(
    file: UploadFile = File(..., description="Video file to annotate (MP4, MOV, AVI)"),
    threshold: float = Query(0.40, ge=0.0, le=1.0, description="Match threshold (default: 0.40)"),
    db: AsyncSession = Depends(get_db),
):
    video_bytes = await file.read()
    if not video_bytes:
        raise HTTPException(status_code=400, detail="Empty video file received.")

    face_service = _get_face_service()
    await face_service.ensure_db_loaded(db)

    try:
        output_path, summary = await face_service.annotate_video_file(
            video_bytes=video_bytes,
            threshold=threshold,
        )
        return FileResponse(
            path=output_path,
            media_type="video/mp4",
            filename=f"annotated_{Path(file.filename or 'video').stem}.mp4",
            headers={
                "X-Total-Frames": str(summary.get("total_frames_processed", 0)),
                "X-Total-Detections": str(summary.get("total_detections", 0)),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to annotate video: {str(e)}")


# ──────────────────────────────────────────────────────────────────────────────
# 6. Profile Retrieval & Photo Serving (يجب أن تبقى في النهاية لتجنب تداخل الـ Wildcard)
# ──────────────────────────────────────────────────────────────────────────────

@router.get(
    "/{name}",
    summary="Get face profile details",
    description="Retrieve registration info and photo URL for a specific person.",
)
async def get_face_profile(name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FaceProfile).where(FaceProfile.name == name))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Person '{name}' not found.")

    return {
        "id": profile.id,
        "name": profile.name,
        "photo_path": profile.photo_path,
        "photo_url": f"/api/v1/faces/{profile.name}/photo" if profile.photo_path else None,
        "created_at": profile.created_at.isoformat() if profile.created_at else None,
    }


@router.get(
    "/{name}/photo",
    summary="Get registered person face photo",
    description="Serve the thumbnail image of the registered person.",
)
async def get_face_photo(name: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(FaceProfile).where(FaceProfile.name == name))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Person '{name}' not found.")

    if not profile.photo_path or not os.path.exists(profile.photo_path):
        raise HTTPException(status_code=404, detail=f"Photo for '{name}' does not exist on disk.")

    return FileResponse(profile.photo_path, media_type="image/jpeg")


@router.delete(
    "/{name}",
    summary="Delete a face profile",
    description="Delete a registered person and their photo from the database.",
)
async def delete_face_profile(
    name: str,
    db: AsyncSession = Depends(get_db),
    _user: Optional[str] = Depends(get_optional_user),
):
    face_service = _get_face_service()
    deleted = await face_service.delete_face(name=name, db=db)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Person '{name}' not found.")

    return {"message": f"Person '{name}' was successfully deleted."}



