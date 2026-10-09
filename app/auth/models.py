"""
Auth Models — API key + session for backend REST access.
Devices authenticate with a pairing code over WebSocket (doc §6 security).
Admin users authenticate with JWT for REST endpoints (control room, settings, etc.).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class APIKey(Base):
    """
    Pre-issued API keys for Flutter desktop & admin tools.
    Short-lived sessions are linked to a key.
    """
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128))           # human label, e.g. "Control Room PC"
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
