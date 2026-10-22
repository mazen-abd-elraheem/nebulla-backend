"""
SQLAlchemy async session factory.

Tables (doc §6 database):
  devices, personalities, memories, conversations, messages,
  signals, calibration, tracking, logs
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models."""
    pass


async def init_db() -> None:
    """Create all tables on startup (dev/simple mode — use Alembic for production)."""
    from app.models import (  # noqa: F401  — import to register models
        device, personality, memory, conversation, signal, calibration, tracking, log, face_profile
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        def _migrate(connection):
            from sqlalchemy import inspect, text
            inspector = inspect(connection)
            tables = inspector.get_table_names()
            if "conversations" in tables:
                cols = [c["name"] for c in inspector.get_columns("conversations")]
                if "personality_id" not in cols:
                    connection.execute(text("ALTER TABLE conversations ADD COLUMN personality_id INTEGER REFERENCES personalities(id)"))
            if "face_profiles" in tables:
                cols = [c["name"] for c in inspector.get_columns("face_profiles")]
                if "photo_path" not in cols:
                    connection.execute(text("ALTER TABLE face_profiles ADD COLUMN photo_path VARCHAR(256)"))

        await conn.run_sync(_migrate)
    logger.info("Database initialised")

    # Seed default personality if table is empty
    from sqlalchemy import select
    from app.models.personality import Personality
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Personality).limit(1))
        if not result.scalar_one_or_none():
            default_p = Personality(
                id=1,
                name="Nebula",
                description="الشخصية الافتراضية للروبوت نيبولا",
                system_prompt="أنت توأم رقمي مصري. بتتكلم بالمصري العامي وبتخلط إنجليزي زي أي مصري عادي.",
                dialect="cairo",
                language_mix="ar_en",
                is_active=True,
            )
            session.add(default_p)
            await session.commit()
            logger.info("Default personality seeded (id=1)")


async def get_db() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
