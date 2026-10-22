import asyncio
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.db.session import get_db
from app.models.face_profile import FaceProfile
from app.websocket.handlers import _get_face_service

router = APIRouter()

@router.post("/register", summary="Register a new face")
async def register_face(
    name: str = Form(..., description="Name of the person"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    # Read image
    jpeg_bytes = await file.read()
    
    # Get the singleton face service
    face_service = _get_face_service()
    
    # Extract embedding
    loop = asyncio.get_event_loop()
    emb = await loop.run_in_executor(None, face_service.extract_embedding_sync, jpeg_bytes)
    
    if not emb:
        raise HTTPException(status_code=400, detail="Could not detect a face or extract embedding")
        
    # Save to database
    face_profile = FaceProfile(name=name, embedding=emb)
    db.add(face_profile)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Face name '{name}' is already registered.")
        
    # Update known embeddings in the service
    await face_service.reload_known_faces(db)
    
    return {"message": "Face registered successfully", "name": name, "embedding_size": len(emb)}
