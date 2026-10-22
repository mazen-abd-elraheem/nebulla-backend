"""
Unit tests for SQLAlchemy ORM models.
Tests table creation, relationships, and CRUD operations with an in-memory SQLite database.
"""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy import select

from app.db.session import Base
from app.models import (
    Device,
    Personality,
    Memory,
    Conversation,
    Message,
    Signal,
    ServoCalibration,
    TrackingRecord,
    SystemLog,
    FaceProfile,
)


@pytest_asyncio.fixture
async def async_session():
    """Create an isolated in-memory SQLite database session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.asyncio
async def test_device_crud(async_session: AsyncSession):
    dev = Device(
        device_id="esp32-robot-01",
        device_type="esp",
        name="Main Robot Chassis",
        is_connected=True,
        battery_voltage=7.8,
        distance_cm=65.2,
    )
    async_session.add(dev)
    await async_session.commit()

    saved = (await async_session.execute(select(Device).where(Device.device_id == "esp32-robot-01"))).scalar_one()
    assert saved.id is not None
    assert saved.device_type == "esp"
    assert saved.battery_voltage == 7.8


@pytest.mark.asyncio
async def test_personality_and_memory_relationship(async_session: AsyncSession):
    # Create personality
    p = Personality(
        name="Cleo",
        description="Egyptian Arabic AI Assistant",
        dialect="cairo",
        system_prompt="أنت كليو، روبوت مصري ذكي ومرح",
        is_active=True,
    )
    async_session.add(p)
    await async_session.commit()

    # Add memories linked to Cleo
    m1 = Memory(
        personality_id=p.id,
        content="اسم المستخدم أحمد ويعمل مهندس برمجيات",
        importance=8,
        source="conversation",
    )
    m2 = Memory(
        personality_id=p.id,
        content="المستخدم يفضل التحدث بالعامية المصرية",
        importance=7,
        source="manual",
    )
    async_session.add_all([m1, m2])
    await async_session.commit()

    # Query personality with memories
    result = await async_session.execute(select(Personality).where(Personality.id == p.id))
    fetched_p = result.scalar_one()
    memories = (await async_session.execute(select(Memory).where(Memory.personality_id == p.id))).scalars().all()
    assert len(memories) == 2


@pytest.mark.asyncio
async def test_conversation_and_messages(async_session: AsyncSession):
    conv = Conversation(session_id="session-xyz-123")
    async_session.add(conv)
    await async_session.commit()

    msg1 = Message(
        conversation_id=conv.id,
        role="user",
        content="أهلاً يا نيبولا، عامل إيه؟",
        emotion="neutral",
    )
    msg2 = Message(
        conversation_id=conv.id,
        role="assistant",
        content="تمام الحمد لله يا صاحبي! [wave]",
        emotion="happy",
        stt_latency_ms=250.0,
        llm_latency_ms=450.0,
        tts_latency_ms=300.0,
        total_latency_ms=1000.0,
    )
    async_session.add_all([msg1, msg2])
    await async_session.commit()

    # Verify messages
    res = await async_session.execute(select(Message).where(Message.conversation_id == conv.id))
    messages = res.scalars().all()
    assert len(messages) == 2
    assert messages[1].emotion == "happy"
    assert messages[1].total_latency_ms == 1000.0


@pytest.mark.asyncio
async def test_signal_and_calibration(async_session: AsyncSession):
    # Signal
    sig = Signal(
        name="greet",
        description="Raise hand and greet",
        joint_commands_json='[{"t":"joint","id":5,"deg":45,"ms":500}]',
        emotion_tag="happy",
    )
    async_session.add(sig)

    # Calibration
    cal = ServoCalibration(
        servo_id=5,
        label="shoulder_pitch",
        min_angle=10.0,
        max_angle=170.0,
        home_angle=90.0,
    )
    async_session.add(cal)
    await async_session.commit()

    saved_sig = await async_session.get(Signal, sig.id)
    saved_cal = await async_session.get(ServoCalibration, 5)
    assert saved_sig.name == "greet"
    assert saved_cal.label == "shoulder_pitch"
    assert saved_cal.home_angle == 90.0


@pytest.mark.asyncio
async def test_tracking_and_logs(async_session: AsyncSession):
    trk = TrackingRecord(device_id="esp32-main", face_detected=True, distance_cm=18.5)
    log = SystemLog(level="WARNING", source="motion_guard", message="Obstacle detected closer than 20cm")
    async_session.add_all([trk, log])
    await async_session.commit()

    saved_trk = await async_session.get(TrackingRecord, trk.id)
    saved_log = await async_session.get(SystemLog, log.id)
    assert saved_trk.distance_cm == 18.5
    assert saved_trk.face_detected is True
    assert saved_log.level == "WARNING"


@pytest.mark.asyncio
async def test_face_profile(async_session: AsyncSession):
    face = FaceProfile(name="Ahmed", embedding=b"\x00\x01\x02\x03")
    async_session.add(face)
    await async_session.commit()

    saved_face = (await async_session.execute(select(FaceProfile).where(FaceProfile.name == "Ahmed"))).scalar_one()
    assert saved_face.id is not None
    assert saved_face.name == "Ahmed"
    assert saved_face.embedding == b"\x00\x01\x02\x03"

