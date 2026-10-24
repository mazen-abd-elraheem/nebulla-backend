import json
import pickle
from datetime import datetime
from typing import Any, List, Optional, Union

import numpy as np
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
    embedding: Mapped[bytes] = mapped_column(LargeBinary)
    photo_path: Mapped[Optional[str]] = mapped_column(String(256), nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __init__(self, **kwargs):
        if "embedding" in kwargs:
            raw_emb = kwargs["embedding"]
            if not isinstance(raw_emb, bytes):
                kwargs["embedding"] = self.serialize_embedding(raw_emb)
        super().__init__(**kwargs)

    @staticmethod
    def serialize_embedding(vec: Union[List[float], np.ndarray, bytes, Any]) -> bytes:
        """Standardize any embedding format into float32 bytes for database storage."""
        if isinstance(vec, bytes):
            return vec
        if isinstance(vec, (list, tuple, np.ndarray)):
            return np.array(vec, dtype=np.float32).tobytes()
        return pickle.dumps(vec)

    def get_embedding_vector(self) -> Optional[np.ndarray]:
        """Convert stored binary embedding into a 1D numpy float array."""
        if not self.embedding:
            return None
        try:
            arr = np.frombuffer(self.embedding, dtype=np.float32)
            if arr.size > 0:
                return arr
        except Exception:
            pass
        try:
            val = pickle.loads(self.embedding)
            return np.array(val, dtype=np.float32).flatten()
        except Exception:
            pass
        try:
            val = json.loads(self.embedding.decode("utf-8"))
            return np.array(val, dtype=np.float32).flatten()
        except Exception:
            pass
        return None
