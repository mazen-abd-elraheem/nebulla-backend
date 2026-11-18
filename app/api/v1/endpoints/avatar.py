"""Avatar API Endpoints — Creation (GAGAvatar), Preview/Approve/Reject/Recreate, and Emoji Expressions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import get_optional_user
from app.db.session import get_db
from app.models.user import User
from app.services.avatar.emoji_actions import list_emoji_action_catalog
from app.services.avatar.gagavatar_service import GAGAvatarService, get_avatar_service

router = APIRouter()


class AvatarRejectRequest(BaseModel):
    reason: Optional[str] = None


class AvatarRenderRequest(BaseModel):
    expression: Optional[str] = None
    face_emoji: Optional[str] = None
    mouth_open: float = 0.45
    duration_ms: int = 1200
    format: str = "gif"


async def _resolve_authenticated_user_id(sub: Optional[str], db: AsyncSession) -> Optional[int]:
    """Map JWT subject to database User.id (returns None for unauthenticated/dev mode)."""
    if not sub or sub in ("dev_user", "api_key_client", "control_room_desktop"):
        return None
    if sub.isdigit():
        u = await db.get(User, int(sub))
        return u.id if u else None
    sub_lower = sub.lower()
    res = await db.execute(select(User).where((User.email == sub_lower) | (User.username == sub_lower)))
    u = res.scalar_one_or_none()
    return u.id if u else None


@router.get("/emojis/map", summary="List supported face emojis & FLAME avatar expressions")
async def get_emoji_action_map() -> Dict[str, Any]:
    items = list_emoji_action_catalog()
    return {"count": len(items), "emojis": items}


@router.get("/status", summary="Check GAGAvatar GPU worker & fallback engine readiness")
async def get_avatar_engine_status(
    svc: GAGAvatarService = Depends(get_avatar_service),
) -> Dict[str, Any]:
    return await svc.get_runtime_status()


@router.post("/create", summary="Create a draft avatar from an uploaded photo", status_code=status.HTTP_201_CREATED)
async def create_avatar(
    file: UploadFile = File(..., description="Clear frontal photo of user face (JPEG/PNG)"),
    name: Optional[str] = Form(None),
    personality_id: Optional[int] = Form(None),
    style: str = Form("realistic"),
    require_face: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    sub: Optional[str] = Depends(get_optional_user),
    svc: GAGAvatarService = Depends(get_avatar_service),
) -> Dict[str, Any]:
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="ملف الصورة فارغ.")

    user_id = await _resolve_authenticated_user_id(sub, db)
    pid = personality_id if personality_id and personality_id > 0 else None
    try:
        profile = await svc.create_avatar_from_photo(
            image_bytes=image_bytes,
            db=db,
            user_id=user_id,
            personality_id=pid,
            name=name,
            style=style,
            require_face=require_face,
            allow_local_animator=True,
        )
        return {
            "status": "pending_review",
            "message": "تم إنشاء الأفاتار، راجعه واختار اعتماد أو إعادة إنشاء.",
            "avatar": svc.serialize_avatar(profile),
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"فشل إنشاء الأفاتار: {exc}")


@router.get("/active", summary="Get currently active approved avatar")
async def get_active_avatar(
    personality_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    sub: Optional[str] = Depends(get_optional_user),
    svc: GAGAvatarService = Depends(get_avatar_service),
) -> Dict[str, Any]:
    user_id = await _resolve_authenticated_user_id(sub, db)
    avatar = await svc.get_active_avatar(db=db, user_id=user_id, personality_id=personality_id)
    if avatar is not None:
        avatar = await svc.upgrade_legacy_avatar_if_needed(avatar=avatar, db=db)
    elif user_id is not None:
        user = await db.get(User, user_id)
        if user is not None:
            avatar = await svc.ensure_active_avatar_from_user(user=user, db=db)
    if not avatar:
        return {"has_avatar": False, "avatar": None}
    return {"has_avatar": True, "avatar": svc.serialize_avatar(avatar)}


@router.get("/list", summary="List generated avatars & review history")
async def list_avatars(
    personality_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    sub: Optional[str] = Depends(get_optional_user),
    svc: GAGAvatarService = Depends(get_avatar_service),
) -> Dict[str, Any]:
    user_id = await _resolve_authenticated_user_id(sub, db)
    items = await svc.list_avatars(db=db, user_id=user_id, personality_id=personality_id)
    return {"count": len(items), "avatars": [svc.serialize_avatar(a) for a in items]}


@router.get("/{avatar_id}", summary="Get avatar details by ID")
async def get_avatar_by_id(
    avatar_id: int,
    db: AsyncSession = Depends(get_db),
    sub: Optional[str] = Depends(get_optional_user),
    svc: GAGAvatarService = Depends(get_avatar_service),
) -> Dict[str, Any]:
    user_id = await _resolve_authenticated_user_id(sub, db)
    avatar = await svc.get_avatar(avatar_id=avatar_id, db=db, user_id=user_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="الأفاتار غير موجود.")
    return {"avatar": svc.serialize_avatar(avatar)}


@router.post("/{avatar_id}/approve", summary="Approve a draft avatar and set it active")
async def approve_avatar(
    avatar_id: int,
    db: AsyncSession = Depends(get_db),
    sub: Optional[str] = Depends(get_optional_user),
    svc: GAGAvatarService = Depends(get_avatar_service),
) -> Dict[str, Any]:
    user_id = await _resolve_authenticated_user_id(sub, db)
    try:
        avatar = await svc.approve_avatar(avatar_id=avatar_id, db=db, user_id=user_id)
        # Keep user's profile photo & personal Personality synced with the approved avatar
        if user_id is not None:
            from app.models.personality import Personality

            user = await db.get(User, user_id)
            if user is not None:
                user.avatar_url = f"/api/v1/avatar/{avatar.id}/preview"
                db.add(user)
            p_res = await db.execute(
                select(Personality).where(Personality.user_id == user_id).limit(1)
            )
            persona = p_res.scalar_one_or_none()
            if persona is not None:
                persona.image_path = avatar.avatar_preview_path
                db.add(persona)
            await db.commit()
        return {
            "status": "approved",
            "message": "تم اعتماد الأفاتار وتفعيله بنجاح.",
            "avatar": svc.serialize_avatar(avatar),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="الأفاتار غير موجود.")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{avatar_id}/reject", summary="Reject a generated avatar preview")
async def reject_avatar(
    avatar_id: int,
    body: Optional[AvatarRejectRequest] = None,
    db: AsyncSession = Depends(get_db),
    sub: Optional[str] = Depends(get_optional_user),
    svc: GAGAvatarService = Depends(get_avatar_service),
) -> Dict[str, Any]:
    user_id = await _resolve_authenticated_user_id(sub, db)
    try:
        reason = body.reason if body else None
        avatar = await svc.reject_avatar(avatar_id=avatar_id, db=db, reason=reason, user_id=user_id)
        return {
            "status": "rejected",
            "message": "تم رفض الأفاتار، يمكنك إنشاء أفاتار جديد.",
            "avatar": svc.serialize_avatar(avatar),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="الأفاتار غير موجود.")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))


@router.post("/{avatar_id}/recreate", summary="Reject current draft and regenerate a new avatar")
async def recreate_avatar(
    avatar_id: int,
    file: Optional[UploadFile] = File(None, description="Optional replacement photo"),
    style: Optional[str] = Form(None),
    reason: Optional[str] = Form(None),
    require_face: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    sub: Optional[str] = Depends(get_optional_user),
    svc: GAGAvatarService = Depends(get_avatar_service),
) -> Dict[str, Any]:
    user_id = await _resolve_authenticated_user_id(sub, db)
    image_bytes = await file.read() if file is not None else None
    try:
        avatar = await svc.recreate_avatar(
            avatar_id=avatar_id,
            db=db,
            image_bytes=image_bytes,
            style=style,
            reason=reason,
            user_id=user_id,
            require_face=require_face,
            allow_local_animator=True,
        )
        return {
            "status": "pending_review",
            "message": "تم إنشاء نسخة جديدة من الأفاتار للمراجعة.",
            "avatar": svc.serialize_avatar(avatar),
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="الأفاتار غير موجود.")
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{avatar_id}/render", summary="Render animated facial expression & mouth movement for an emoji")
async def render_avatar_expression(
    avatar_id: int,
    body: AvatarRenderRequest,
    db: AsyncSession = Depends(get_db),
    sub: Optional[str] = Depends(get_optional_user),
    svc: GAGAvatarService = Depends(get_avatar_service),
) -> Dict[str, Any]:
    user_id = await _resolve_authenticated_user_id(sub, db)
    avatar = await svc.get_avatar(avatar_id=avatar_id, db=db, user_id=user_id)
    if not avatar:
        raise HTTPException(status_code=404, detail="الأفاتار غير موجود.")

    key = body.face_emoji or body.expression or "happy"
    try:
        return await svc.render_avatar_animation(
            avatar=avatar,
            expression_or_emoji=key,
            mouth_open=body.mouth_open,
            duration_ms=body.duration_ms,
            output_format=body.format,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


async def _resolve_avatar_and_asset(
    avatar_id: int,
    db: AsyncSession,
    svc: GAGAvatarService,
    asset_type: str = "preview",
    expression: str | None = None,
    level: int = 0,
) -> Path | None:
    """
    Robust fallback resolver for avatar assets:
    1. Looks up target avatar ID.
    2. If missing or files wiped, falls back to active avatar or newest valid avatar on disk.
    3. For expressions/mouth frames, gracefully degrades to neutral or preview image.
    """
    avatar = await svc.get_avatar(avatar_id, db)
    if not avatar or not avatar.avatar_preview_path or not Path(avatar.avatar_preview_path).exists():
        # Fallback 1: Active approved avatar
        avatar = await svc.get_active_avatar(db)
        if not avatar or not avatar.avatar_preview_path or not Path(avatar.avatar_preview_path).exists():
            # Fallback 2: Any existing valid avatar
            valid_list = await svc.list_avatars(db)
            avatar = valid_list[0] if valid_list else None

    if not avatar:
        return None

    if asset_type == "preview":
        if avatar.avatar_preview_path and Path(avatar.avatar_preview_path).exists():
            return Path(avatar.avatar_preview_path)

    elif asset_type == "source":
        if avatar.source_photo_path and Path(avatar.source_photo_path).exists():
            return Path(avatar.source_photo_path)
        if avatar.avatar_preview_path and Path(avatar.avatar_preview_path).exists():
            return Path(avatar.avatar_preview_path)

    elif asset_type == "sprite":
        safe_name = Path(expression).name if expression else "neutral"
        if avatar.sprites_dir:
            cand = Path(avatar.sprites_dir) / f"{safe_name}.png"
            if cand.exists():
                return cand
            cand_neutral = Path(avatar.sprites_dir) / "neutral.png"
            if cand_neutral.exists():
                return cand_neutral
        if avatar.avatar_preview_path and Path(avatar.avatar_preview_path).exists():
            return Path(avatar.avatar_preview_path)

    elif asset_type == "mouth":
        safe_expr = Path(expression).name if expression else "neutral"
        safe_lvl = max(0, min(int(level), 3))
        avatar_dir = Path(avatar.avatar_preview_path).parent
        if safe_lvl > 0:
            cand_mouth = avatar_dir / "mouth" / f"{safe_expr}_{safe_lvl}.png"
            if cand_mouth.exists():
                return cand_mouth
            cand_mouth_neutral = avatar_dir / "mouth" / f"neutral_{safe_lvl}.png"
            if cand_mouth_neutral.exists():
                return cand_mouth_neutral
        if avatar.sprites_dir:
            cand_sprite = Path(avatar.sprites_dir) / f"{safe_expr}.png"
            if cand_sprite.exists():
                return cand_sprite
            cand_sprite_neutral = Path(avatar.sprites_dir) / "neutral.png"
            if cand_sprite_neutral.exists():
                return cand_sprite_neutral
        if avatar.avatar_preview_path and Path(avatar.avatar_preview_path).exists():
            return Path(avatar.avatar_preview_path)

    return None


@router.get("/{avatar_id}/preview", summary="Serve avatar preview image (PNG)")
async def serve_avatar_preview(
    avatar_id: int,
    db: AsyncSession = Depends(get_db),
    svc: GAGAvatarService = Depends(get_avatar_service),
):
    asset_path = await _resolve_avatar_and_asset(avatar_id, db, svc, asset_type="preview")
    if not asset_path or not asset_path.exists():
        raise HTTPException(status_code=404, detail="صورة الأفاتار غير موجودة.")
    return FileResponse(
        str(asset_path),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{avatar_id}/source", summary="Serve source photo used to build avatar")
async def serve_avatar_source(
    avatar_id: int,
    db: AsyncSession = Depends(get_db),
    svc: GAGAvatarService = Depends(get_avatar_service),
):
    asset_path = await _resolve_avatar_and_asset(avatar_id, db, svc, asset_type="source")
    if not asset_path or not asset_path.exists():
        raise HTTPException(status_code=404, detail="الصورة الأصلية غير موجودة.")
    media_type = "image/jpeg" if asset_path.suffix.lower() in [".jpg", ".jpeg"] else "image/png"
    return FileResponse(str(asset_path), media_type=media_type, headers={"Cache-Control": "no-store"})


@router.get("/{avatar_id}/sprite/{expression}", summary="Serve expression sprite image (PNG)")
async def serve_avatar_sprite(
    avatar_id: int,
    expression: str,
    db: AsyncSession = Depends(get_db),
    svc: GAGAvatarService = Depends(get_avatar_service),
):
    asset_path = await _resolve_avatar_and_asset(
        avatar_id, db, svc, asset_type="sprite", expression=expression
    )
    if not asset_path or not asset_path.exists():
        raise HTTPException(status_code=404, detail="التعبير المطلوب غير موجود.")
    return FileResponse(str(asset_path), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/{avatar_id}/mouth/{expression}/{level}", summary="Serve GAGAvatar neural mouth-open frame PNG")
async def serve_avatar_mouth_frame(
    avatar_id: int,
    expression: str,
    level: int,
    db: AsyncSession = Depends(get_db),
    svc: GAGAvatarService = Depends(get_avatar_service),
):
    asset_path = await _resolve_avatar_and_asset(
        avatar_id, db, svc, asset_type="mouth", expression=expression, level=level
    )
    if not asset_path or not asset_path.exists():
        raise HTTPException(status_code=404, detail="إطار حركة الفم غير موجود.")
    return FileResponse(str(asset_path), media_type="image/png", headers={"Cache-Control": "no-store"})


@router.get("/{avatar_id}/render-file/{filename}", summary="Serve generated animation GIF/PNG")
async def serve_render_artifact(
    avatar_id: int,
    filename: str,
    db: AsyncSession = Depends(get_db),
    svc: GAGAvatarService = Depends(get_avatar_service),
):
    avatar = await svc.get_avatar(avatar_id, db)
    if not avatar:
        raise HTTPException(status_code=404, detail="الأفاتار غير موجود.")

    safe_name = Path(filename).name
    renders_dir = Path(avatar.avatar_preview_path).parent / "renders"
    file_path = renders_dir / safe_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="ملف الحركة غير موجود.")

    media_type = "image/gif" if file_path.suffix.lower() == ".gif" else "image/png"
    return FileResponse(str(file_path), media_type=media_type, headers={"Cache-Control": "no-store"})
