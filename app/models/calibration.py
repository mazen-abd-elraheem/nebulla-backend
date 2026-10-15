"""
Calibration ORM Model — servo limits, home angles, and channel mapping.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class ServoCalibration(Base):
    """
    Hardware calibration data per servo joint (ESP32 channels 0-11).
    """
    __tablename__ = "servo_calibrations"

    servo_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(128), nullable=False)
    min_angle: Mapped[float] = mapped_column(Float, default=0.0)
    max_angle: Mapped[float] = mapped_column(Float, default=180.0)
    home_angle: Mapped[float] = mapped_column(Float, default=90.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
