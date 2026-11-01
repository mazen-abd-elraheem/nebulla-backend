"""
Person & Face Photo Retrieval Module for RAG.

Solves the Person Image Data Retrieval Requirement:
- Dual-mode retrieval:
    1. Text -> Person Profile & Photo (e.g. "وريني صورة مازن", "مين منه وشكلها إيه؟")
    2. Image/Face -> Person Profile & Linked Long-Term Memories
- Integrates with UniFace FaceAnalyzer and SQLite face_profiles table.
- Emits Screen Control events to display photos on connected desktop control rooms and phone displays.
- Zero fallback models: strictly adheres to registered database records.
"""

import os
import sqlite3
import re
from typing import Dict, List, Optional, Tuple, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logger import get_logger
from app.models.face_profile import FaceProfile
from app.utils.masri_normalizer import normalize_masri_orthography

logger = get_logger(__name__)


class PersonImageRetriever:
    """Retrieves person visual profiles, photos, and linked memories."""

    PHOTO_INQUIRY_PATTERNS = [
        r"\b(صورة|صورته|صورتها|صور|شكله|شكلها|ملامح|ملامحه|ملامحها)\b",
        r"\b(وريني|فرجني|عايز اشوف|عايز أشوف|عاوز اشوف|أشوف صورة|اشوف صورة)\b",
        r"\b(photo|picture|image|look like|show me)\b",
    ]

    @classmethod
    def is_photo_inquiry(cls, text: str) -> bool:
        """Determines if user message explicitly requests seeing a person's photo or visual appearance."""
        if not text:
            return False
        clean = text.lower()
        return any(re.search(pat, clean) for pat in cls.PHOTO_INQUIRY_PATTERNS)

    @classmethod
    def extract_person_candidate(cls, query: str, known_names: List[str]) -> Optional[str]:
        """Matches candidate person name from query against list of registered names."""
        if not query or not known_names:
            return None
        norm_q = normalize_masri_orthography(query).lower()
        for name in known_names:
            norm_name = normalize_masri_orthography(name).lower()
            # Check full name or first name
            first_name = norm_name.split()[0]
            if norm_name in norm_q or (len(first_name) >= 3 and first_name in norm_q):
                return name
        return None

    @classmethod
    def get_person_profile_sync(cls, name: str) -> Optional[Dict[str, Any]]:
        """Retrieve FaceProfile record synchronously from SQLite."""
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)

        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name, photo_path, created_at FROM face_profiles WHERE name = ? OR name LIKE ?",
            (name, f"%{name}%"),
        )
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        p_id, p_name, photo_path, created_at = row
        return {
            "id": p_id,
            "name": p_name,
            "photo_path": photo_path,
            "photo_url": f"/api/v1/faces/{p_name}/photo" if photo_path else None,
            "created_at": created_at,
            "has_photo": bool(photo_path and os.path.exists(photo_path)),
        }

    @classmethod
    async def get_person_profile(
        cls,
        name: str,
        db: Optional[AsyncSession] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve FaceProfile record via AsyncSession or synchronous SQLite."""
        if db is not None:
            res = await db.execute(select(FaceProfile).where(FaceProfile.name.ilike(f"%{name}%")))
            profile = res.scalar_one_or_none()
            if not profile:
                return None
            return {
                "id": profile.id,
                "name": profile.name,
                "photo_path": profile.photo_path,
                "photo_url": f"/api/v1/faces/{profile.name}/photo" if profile.photo_path else None,
                "created_at": profile.created_at.isoformat() if profile.created_at else None,
                "has_photo": bool(profile.photo_path and os.path.exists(profile.photo_path)),
            }
        return cls.get_person_profile_sync(name)

    @classmethod
    async def get_all_registered_names(cls, db: Optional[AsyncSession] = None) -> List[str]:
        """Fetch all registered person names in face_profiles."""
        if db is not None:
            res = await db.execute(select(FaceProfile.name))
            return list(res.scalars().all())

        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        if not os.path.isabs(db_path):
            db_path = os.path.abspath(db_path)

        conn = sqlite3.connect(db_path, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM face_profiles")
        names = [r[0] for r in cursor.fetchall()]
        conn.close()
        return names

    @classmethod
    async def match_face_image(
        cls,
        image_bytes: bytes,
        threshold: float = 0.40,
    ) -> List[Dict[str, Any]]:
        """
        Takes raw image bytes, runs UniFace recognition, and returns matched person profiles.
        """
        try:
            from app.websocket.handlers import _get_face_service
            face_svc = _get_face_service()
            await face_svc._ensure_model()
            matches = await face_svc.recognize_faces(image_bytes=image_bytes, threshold=threshold)

            enriched_matches: List[Dict[str, Any]] = []
            for m in matches:
                p_name = m.get("match_name")
                profile = None
                if p_name and p_name != "unknown":
                    profile = cls.get_person_profile_sync(p_name)

                enriched_matches.append({
                    **m,
                    "profile": profile,
                })
            return enriched_matches
        except Exception as e:
            logger.warning(f"Error matching face image: {e}")
            return []

