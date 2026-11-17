"""AvatarProfile ORM model — stores GAGAvatar-generated user avatars & review lifecycle."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class AvatarProfile(Base):
    """Stores a user's generated 3D/portrait avatar, normalized landmarks, and approval state."""

    __tablename__ = "avatar_profiles"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    personality_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("personalities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    source_photo_path: Mapped[str] = mapped_column(String(500))
    avatar_preview_path: Mapped[str] = mapped_column(String(500))
    sprites_dir: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    landmarks_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expressions_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    engine: Mapped[str] = mapped_column(String(50), default="gagavatar")
    style: Mapped[str] = mapped_column(String(50), default="realistic")
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending_review",
        index=True,  # "pending_review" | "approved" | "rejected"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    rejection_reason: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

