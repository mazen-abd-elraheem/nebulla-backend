"""Unit tests for AIPipeline orchestrating STT, LLM, and TTS with DB persistence."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from app.services.ai.pipeline import AIPipeline
from app.db.session import AsyncSessionLocal, init_db
from app.models.conversation import Conversation, Message
from app.models.personality import Personality


import uuid

@pytest.mark.asyncio
async def test_aipipeline_flow_and_clean_tts():
    await init_db()

    session_id = f"test-session-{uuid.uuid4().hex}"
    pipeline = AIPipeline(session_id=session_id)

    # Mock providers
    mock_stt = MagicMock()
    mock_stt.transcribe = AsyncMock(return_value="صباح الخير")
    pipeline._stt = mock_stt

    async def mock_llm_stream(*args, **kwargs):
        yield "أهلاً "
        yield "وسهلاً بك! "
        yield "[happy] [wave]"

    mock_llm = MagicMock()
    mock_llm.generate_stream = mock_llm_stream
    pipeline._llm = mock_llm

    mock_tts = MagicMock()
    mock_tts.synthesize = AsyncMock(return_value=b"fake_wav_audio")
    pipeline._tts = mock_tts

    # Run pipeline
    dummy_audio = b"dummy_audio_bytes"
    await pipeline._run_pipeline(dummy_audio)

    # Verify STT was called
    mock_stt.transcribe.assert_called_once_with(dummy_audio)

    # Verify TTS calls received CLEANED text without [happy] or [wave]
    tts_calls = [call.args[0] for call in mock_tts.synthesize.call_args_list]
    for text_sent_to_tts in tts_calls:
        assert "[" not in text_sent_to_tts
        assert "]" not in text_sent_to_tts
        assert "happy" not in text_sent_to_tts
        assert "wave" not in text_sent_to_tts

    # Wait briefly for background DB save task
    import asyncio
    await asyncio.sleep(0.2)

    # Verify conversation & message were persisted in DB
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Conversation).where(Conversation.session_id == session_id)
        )
        conv = res.scalar_one_or_none()
        assert conv is not None

        msg_res = await session.execute(
            select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
        )
        messages = msg_res.scalars().all()
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[0].content == "صباح الخير"
        assert messages[1].role == "robot"
        assert "أهلاً وسهلاً بك!" in messages[1].content
        assert messages[1].emotion == "happy"
        assert messages[1].llm_latency_ms is not None
        assert messages[1].total_latency_ms is not None


@pytest.mark.asyncio
async def test_aipipeline_reload_providers():
    pipeline = AIPipeline()
    old_llm = pipeline._llm

    with patch("app.core.config.settings.LLM_PROVIDER", "openai"):
        pipeline.reload_providers()
        assert pipeline._llm != old_llm
        from app.providers.llm.openai_provider import OpenAIProvider
        assert isinstance(pipeline._llm, OpenAIProvider)
