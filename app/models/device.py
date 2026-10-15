"""
Device ORM Model — connected client devices (Phone, Desktop, ESP32).
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Device(Base):
    """
    Connected hardware and client devices.
    """
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    device_type: Mapped[str] = mapped_column(String(64), nullable=False)  # phone, esp32, desk
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_connected: Mapped[bool] = mapped_column(Boolean, default=False)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    battery_voltage: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
