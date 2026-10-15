"""
Tracking ORM Model — vision and hardware telemetry time-series logs.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class TrackingRecord(Base):
    """
    Periodic sensor and tracking data snapshot.
    """
    __tablename__ = "tracking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    face_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    gaze_x: Mapped[float | None] = mapped_column(Float, nullable=True)
    gaze_y: Mapped[float | None] = mapped_column(Float, nullable=True)
    distance_cm: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
