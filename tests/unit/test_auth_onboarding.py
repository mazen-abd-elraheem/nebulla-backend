"""Unit tests for onboarding memory seeding in `app.auth.router`."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.auth.router import OnboardingAnswersRequest, save_onboarding_answers


def _make_mock_db() -> MagicMock:
    """Create a minimal AsyncSession mock supporting add/commit/rollback."""
    mock_db = MagicMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()
    return mock_db


@pytest.mark.asyncio
async def test_save_onboarding_answers_calls_rag_with_content_no_duplicate_db_add():
    mock_db = _make_mock_db()
    mock_rag = MagicMock()
    mock_rag.add_memory = AsyncMock(return_value=101)

    body = OnboardingAnswersRequest(
        answers={
            "interaction_style": "صوتي تفاعلي",
            "interest_domain": "البرمجة والتقنية",
            "personal_fact": "اسمي مازن",
        }
    )

    with patch("app.services.memory.rag_service.RAGService", return_value=mock_rag):
        result = await save_onboarding_answers(
            body=body,
            current_user=None,
            db=mock_db,
        )

    assert result["success"] is True
    assert result["saved_memories_count"] == 3
    assert mock_rag.add_memory.await_count == 3

    # Ensure RAGService.add_memory owns DB persistence (no duplicate manual db.add)
    mock_db.add.assert_not_called()

    for call in mock_rag.add_memory.await_args_list:
        assert "text" not in call.kwargs
        assert call.kwargs["personality_id"] == 1
        assert call.kwargs["source"] == "onboarding"
        assert call.kwargs["importance"] == 8
        assert call.kwargs["db"] is mock_db
        assert isinstance(call.kwargs["content"], str) and call.kwargs["content"]


@pytest.mark.asyncio
async def test_save_onboarding_answers_falls_back_to_direct_memory_on_rag_failure():
    mock_db = _make_mock_db()
    mock_rag = MagicMock()
    mock_rag.add_memory = AsyncMock(side_effect=RuntimeError("vector store offline"))

    body = OnboardingAnswersRequest(
        answers={
            "interaction_style": "نصي فقط",
            "interest_domain": "",
            "personal_fact": "",
        }
    )

    with patch("app.services.memory.rag_service.RAGService", return_value=mock_rag):
        result = await save_onboarding_answers(
            body=body,
            current_user=None,
            db=mock_db,
        )

    assert result["success"] is True
    assert result["saved_memories_count"] == 1
    mock_db.rollback.assert_awaited_once()
    mock_db.add.assert_called_once()
    added_mem = mock_db.add.call_args.args[0]
    assert added_mem.personality_id == 1
    assert added_mem.source == "onboarding"
    assert added_mem.importance == 8
    assert "نصي فقط" in added_mem.content
