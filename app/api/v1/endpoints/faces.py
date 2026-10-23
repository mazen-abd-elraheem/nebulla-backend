import asyncio
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.auth.jwt import get_current_user
from app.db.session import get_db
from app.models.face_profile import FaceProfile
from app.websocket.handlers import _get_face_service

router = APIRouter()

MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MB cap

@router.post("/register", summary="Register a new face")
async def register_face(
    name: str = Form(..., description="Name of the person"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    clean_name = name.strip()
    if not clean_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Name cannot be empty")

    # Read image with bounded size limit to prevent memory exhaustion
    jpeg_bytes = await file.read(MAX_IMAGE_BYTES + 1)
    if len(jpeg_bytes) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image size exceeds the 5MB limit",
        )

    # Validate image signature (JPEG or PNG)
    if not (jpeg_bytes.startswith(b"\xff\xd8") or jpeg_bytes.startswith(b"\x89PNG\r\n\x1a\n")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image format. Only valid JPEG or PNG files are supported.",
        )

    # Get the singleton face service
    face_service = _get_face_service()
    
    # Extract embedding
    loop = asyncio.get_event_loop()
    emb = await loop.run_in_executor(None, face_service.extract_embedding_sync, jpeg_bytes)
    
    if not emb:
        raise HTTPException(status_code=400, detail="Could not detect a face or extract embedding")
        
    # Save to database as binary bytes (float32 array)
    import numpy as np
    emb_bytes = np.array(emb, dtype=np.float32).tobytes() if isinstance(emb, (list, np.ndarray)) else emb
    face_profile = FaceProfile(name=clean_name, embedding=emb_bytes)
    db.add(face_profile)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Face name '{name}' is already registered.")
        
    # Update known embeddings in the service
    await face_service.reload_known_faces(db)
    
    return {"message": "Face registered successfully", "name": clean_name, "embedding_size": len(emb)}


@router.get("", summary="List all registered face profiles")
async def list_faces(
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    from sqlalchemy import select
    res = await db.execute(select(FaceProfile))
    profiles = res.scalars().all()
    return {
        "faces": [
            {"id": p.id, "name": p.name, "created_at": p.created_at.isoformat() if hasattr(p, "created_at") and p.created_at else None}
            for p in profiles
        ]
    }


@router.delete("/{name}", summary="Delete a registered face profile")
async def delete_face(
    name: str,
    db: AsyncSession = Depends(get_db),
    _user: str = Depends(get_current_user),
):
    from sqlalchemy import select, delete
    res = await db.execute(select(FaceProfile).where(FaceProfile.name == name))
    profile = res.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Face profile '{name}' not found")
    await db.delete(profile)
    await db.commit()

    face_service = _get_face_service()
    await face_service.reload_known_faces(db)
    return {"message": f"Face profile '{name}' deleted successfully"}


@router.get("/current", summary="Get live face detection and recognition status")
async def get_current_face(
    _user: str = Depends(get_current_user),
):
    face_service = _get_face_service()
    return face_service.get_current_face_info()

