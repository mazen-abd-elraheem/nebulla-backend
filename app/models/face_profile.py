from sqlalchemy import Column, Integer, String, JSON
from app.db.session import Base

class FaceProfile(Base):
    __tablename__ = "face_profiles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    embedding = Column(JSON, nullable=False)  # List of floats
