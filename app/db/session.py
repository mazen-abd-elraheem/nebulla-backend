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

from sqlalchemy import event

connect_args = {"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    future=True,
    connect_args=connect_args,
)

if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

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
    from sqlalchemy import text
    from app.models import (  # noqa: F401  — import to register models
        device, personality, memory, conversation, signal, calibration, tracking, log, face_profile, user
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
                if "created_at" not in cols:
                    connection.execute(text("ALTER TABLE face_profiles ADD COLUMN created_at DATETIME"))
            if "personalities" in tables:
                cols = [c["name"] for c in inspector.get_columns("personalities")]
                if "user_id" not in cols:
                    connection.execute(text("ALTER TABLE personalities ADD COLUMN user_id INTEGER REFERENCES users(id)"))
                if "updated_at" not in cols:
                    connection.execute(text("ALTER TABLE personalities ADD COLUMN updated_at DATETIME"))

        await conn.run_sync(_migrate)
    logger.info("Database initialised")

    # Seed or configure default personality 1 (Mazen - Digital Twin)
    from sqlalchemy import select
    from app.models.personality import Personality
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Personality).where(Personality.id == 1))
        existing_p = result.scalar_one_or_none()
        if not existing_p:
            default_p = Personality(
                id=1,
                name="مازن (Mazen) - التوأم الرقمي",
                description="التوأم الرقمي الرسمي لفريق نيبولا بصوت مازن الطبيعي",
                system_prompt="أنت مازن، التوأم الرقمي المصري الذكي. بتتكلم بالمصري العامي العفوي وبنبرتك الطبيعية وبتخلط مصطلحات إنجليزي في السياق التقني.",
                dialect="cairo",
                language_mix="ar_en",
                voice_sample_path="data/voice_samples/personality_1.wav",
                is_active=True,
            )
            session.add(default_p)
            await session.commit()
            logger.info("Default personality seeded (id=1: Mazen)")
        else:
            if not existing_p.voice_sample_path or existing_p.name == "Nebula":
                existing_p.name = "مازن (Mazen) - التوأم الرقمي"
                existing_p.voice_sample_path = "data/voice_samples/personality_1.wav"
                existing_p.description = "التوأم الرقمي الرسمي لفريق نيبولا بصوت مازن الطبيعي"
                await session.commit()
                logger.info("Updated personality 1 to Mazen with clean reference voice")

        # Seed core personalized RAG memories for Mazen (doc §1 RAG & personalized grounding)
        from app.models.memory import Memory
        mem_res = await session.execute(select(Memory.content).where(Memory.personality_id == 1))
        existing_mem_contents = set(mem_res.scalars().all())

        personalized_seeds = [
            "مازن هو المهندس ومطور روبوت نيبولا الرئيسي، وهو من مواليد عام 2000.",
            "مازن يفضل أكل الخضروات ولا يحب أكل الفواكه.",
            "مشروع تخرج مازن هو روبوت نيبولا (Nebula) للذكاء الاصطناعي والتوأم الرقمي.",
            "الروبوت نيبولا يمتلك 12 محرك سيرفو فائق الدقة ومتصل بنظام أمان متقدم.",
            "الروبوت نيبولا تم تزويده بكاميرا تدعم تتبع الوجوه بسرعة 60 إطار في الثانية.",
        ]
        new_count = 0
        for text_content in personalized_seeds:
            if text_content not in existing_mem_contents:
                session.add(Memory(content=text_content, personality_id=1, source="system", importance=5))
                new_count += 1
        if new_count > 0:
            await session.commit()
            logger.info(f"Seeded {new_count} personalized RAG memories for Mazen")


async def get_db() -> AsyncSession:  # type: ignore[return]
    """FastAPI dependency: yields an async DB session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
