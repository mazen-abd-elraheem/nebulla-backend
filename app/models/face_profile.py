import json
from datetime import datetime
from typing import Any
from sqlalchemy import DateTime, Integer, LargeBinary, String
from sqlalchemy.types import TypeDecorator
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class EmbeddingType(TypeDecorator):
    """Transparently serialize list of floats to JSON bytes for BLOB storage."""
    impl = LargeBinary
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> bytes | None:
        if value is None:
            return None
        if isinstance(value, (list, tuple)):
            return json.dumps(list(value)).encode("utf-8")
        if isinstance(value, bytes):
            return value
        try:
            import numpy as np
            if isinstance(value, np.ndarray):
                return json.dumps(value.tolist()).encode("utf-8")
        except ImportError:
            pass
        return str(value).encode("utf-8")

    def process_result_value(self, value: Any, dialect: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, bytes):
            try:
                return json.loads(value.decode("utf-8"))
            except Exception:
                return value
        return value


class FaceProfile(Base):
    __tablename__ = "face_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    embedding: Mapped[Any] = mapped_column(EmbeddingType)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

