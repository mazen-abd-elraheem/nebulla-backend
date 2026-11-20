"""
Unit tests for Multiple Known Persons per User, Relationship & Tone Customization,
and System Prompt Grounding.
"""

try:
    import pytest
except ImportError:
    class _MockPytest:
        class mark:
            @staticmethod
            def asyncio(fn):
                return fn
    pytest = _MockPytest()
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.db.session import init_db, AsyncSessionLocal
from app.models.user import User
from app.models.contact import Contact
from app.models.personality import Personality
from app.services.ai.context_builder import build_grounding_context
from app.core.security import get_password_hash


@pytest.mark.asyncio
async def test_create_and_manage_user_known_people():
    """Verify creating multiple known people for a user with specific relationships and tones."""
    await init_db()

    async with AsyncSessionLocal() as db:
        # Create a test user
        email = "person_test_user@example.com"
        res = await db.execute(select(User).where(User.email == email))
        user = res.scalar_one_or_none()
        if not user:
            user = User(
                full_name="د. أحمد كمال",
                email=email,
                hashed_password=get_password_hash("Secret1234"),
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        # Ensure active personality exists
        p_res = await db.execute(select(Personality).where(Personality.id == 1))
        if not p_res.scalar_one_or_none():
            db.add(Personality(id=1, name="نيبولا", is_active=True, dialect="cairo"))
            await db.commit()

        # Add 3 distinct known contacts with varying relationships and custom tones
        c1 = Contact(
            user_id=user.id,
            name="ماما",
            relationship="أمي",
            tone="حنين وودود جداً",
            phone_number="01012345678",
            is_allowlisted=True,
        )
        c2 = Contact(
            user_id=user.id,
            name="كريم",
            relationship="صديق مقرب",
            tone="عفوي وهزار ومرح",
            phone_number="01198765432",
            is_allowlisted=True,
        )
        c3 = Contact(
            user_id=user.id,
            name="م. طارق",
            relationship="مديري في العمل",
            tone="رسمي ومهني",
            phone_number="",
            is_allowlisted=True,
        )
        db.add_all([c1, c2, c3])
        await db.commit()

        # Verify contacts are persisted and queryable
        q = await db.execute(select(Contact).where(Contact.user_id == user.id))
        contacts = list(q.scalars().all())
        assert len(contacts) >= 3

        # Test ContextBuilder integration: prompt should ground known people and custom tones
        prompt, memories, grounding, pid = await build_grounding_context(
            db=db,
            personality_id=1,
            message="ماما بتسلم عليك وعايز أكلم كريم",
        )

        assert "ماما" in prompt
        assert "أمي" in prompt
        assert "حنين وودود جداً" in prompt
        assert "كريم" in prompt
        assert "صديق مقرب" in prompt
        assert "عفوي وهزار ومرح" in prompt
        assert "م. طارق" in prompt
        assert "مديري في العمل" in prompt
        assert "رسمي ومهني" in prompt
