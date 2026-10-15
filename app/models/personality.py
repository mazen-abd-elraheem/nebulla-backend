"""
Personality ORM Model — robot persona and voice configuration.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Personality(Base):
    """
    Personality profile for the digital twin robot.
    """
    __tablename__ = "personalities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    dialect: Mapped[str] = mapped_column(String(64), default="cairo")
    language_mix: Mapped[str] = mapped_column(String(64), default="ar_en")
    voice_sample_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
