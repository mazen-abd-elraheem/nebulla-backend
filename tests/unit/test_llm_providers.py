"""Unit tests for LLM providers and pipeline helper functions."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.providers.llm.base import BaseLLMProvider, DEFAULT_SYSTEM_PROMPT
from app.providers.llm.factory import get_llm_provider
from app.providers.llm.local_ollama import LocalOllamaProvider
from app.providers.llm.openai_provider import OpenAIProvider
from app.providers.llm.anthropic_provider import AnthropicProvider
from app.services.ai.pipeline import clean_text_for_tts, _extract_emotion


def test_factory_returns_correct_providers():
    p_local = get_llm_provider("local")
    assert isinstance(p_local, LocalOllamaProvider)

    p_openai = get_llm_provider("openai")
    assert isinstance(p_openai, OpenAIProvider)

    p_anthropic = get_llm_provider("anthropic")
    assert isinstance(p_anthropic, AnthropicProvider)

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_llm_provider("unknown_provider")


def test_clean_text_for_tts():
    # Tag at beginning and end
    raw = "[happy] أهلاً يا صديقي! [wave]"
    cleaned = clean_text_for_tts(raw)
    assert cleaned == "أهلاً يا صديقي!"

    # Multiple tags
    raw2 = "تمام جداً [like] [greet] ونلتقي غداً"
    assert clean_text_for_tts(raw2) == "تمام جداً ونلتقي غداً"

    # Only tags
    assert clean_text_for_tts("[wave] [happy]") == ""

    # Normal text without tags
    assert clean_text_for_tts("صباح الخير يا فندم") == "صباح الخير يا فندم"


def test_extract_emotion():
    assert _extract_emotion("أهلاً بك! [happy]") == "happy"
    assert _extract_emotion("للأسف مش قادر أساعدك [sad]") == "sad"
    assert _extract_emotion("بجد؟! [surprised]") == "surprised"
    assert _extract_emotion("أنا فرحان جداً") == "happy"
    assert _extract_emotion("حزين لسماع ذلك") == "sad"
    assert _extract_emotion("الجو مشمس اليوم") == "neutral"


@pytest.mark.asyncio
async def test_local_ollama_streaming():
    provider = LocalOllamaProvider()

    mock_lines = [
        '{"message": {"content": "أهلاً"}, "done": false}',
        '{"message": {"content": " بك"}, "done": false}',
        '{"message": {"content": "!"}, "done": true}',
    ]

    async def mock_aiter_lines():
        for line in mock_lines:
            yield line

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.aiter_lines = mock_aiter_lines

    mock_client = MagicMock()
    mock_client.stream = MagicMock()
    mock_client.stream.return_value.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_client.stream.return_value.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient") as mock_http_client:
        mock_http_client.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_http_client.return_value.__aexit__ = AsyncMock(return_value=None)

        tokens = []
        async for t in provider.generate_stream(
            prompt="ازيك",
            context=["المستخدم اسمه مازن"],
            system_prompt="أنت مساعد مصري",
            history=[{"role": "user", "content": "مرحبا"}, {"role": "robot", "content": "أهلا"}],
        ):
            tokens.append(t)

        assert "".join(tokens) == "أهلاً بك!"


@pytest.mark.asyncio
async def test_openai_streaming():
    provider = OpenAIProvider()

    # Mock chunk objects
    def make_chunk(text):
        choice = MagicMock()
        choice.delta.content = text
        chunk = MagicMock()
        chunk.choices = [choice]
        return chunk

    async def mock_stream():
        yield make_chunk("مرحباً")
        yield make_chunk(" يا")
        yield make_chunk(" صديقي")

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())
    provider._client = mock_client

    tokens = []
    async for t in provider.generate_stream(
        prompt="مين أنت؟",
        context=["معلومة سابقة"],
        system_prompt="شخصية مخصصة",
        history=[{"role": "user", "content": "سؤال سابق"}],
    ):
        tokens.append(t)

    assert "".join(tokens) == "مرحباً يا صديقي"
    call_args = mock_client.chat.completions.create.call_args[1]
    messages = call_args["messages"]
    assert any("شخصية مخصصة" in m.get("content", "") for m in messages)
    assert any("معلومة سابقة" in m.get("content", "") for m in messages)
    assert messages[-1]["content"] == "مين أنت؟"


@pytest.mark.asyncio
async def test_anthropic_missing_package():
    provider = AnthropicProvider()
    with patch.dict("sys.modules", {"anthropic": None}):
        provider._client = None
        tokens = []
        async for t in provider.generate_stream("سؤال"):
            tokens.append(t)
        assert any("anthropic غير مثبتة" in t for t in tokens)


def test_arabic_gesture_tags_and_cleaning():
    from app.services.ai.pipeline import _is_sentence_end
    # Arabic emotion tags
    raw = "[فرحان] صباح الخير يا هندسة [تلويح]"
    cleaned = clean_text_for_tts(raw)
    assert cleaned == "صباح الخير يا هندسة"
    assert _extract_emotion("شكراً لك! [فرحان]") == "happy"
    assert _extract_emotion("للأسف حصلت مشكلة [حزين]") == "sad"
    assert _extract_emotion("مش معقول! [متفاجئ]") == "surprised"

    # Incomplete open tag bracket does not trigger sentence end prematurely
    assert _is_sentence_end("أهلاً يا صديقي! [hap") is False
    assert _is_sentence_end("أهلاً يا صديقي! [happy]") is True


@pytest.mark.asyncio
async def test_openai_model_fallback_and_reset():
    from app.core.config import settings
    provider = OpenAIProvider()
    provider._client = MagicMock()
    provider.reset_client()
    assert provider._client is None

    # Test fallback to gpt-4o-mini when settings.LLM_MODEL is a local model
    mock_client = MagicMock()
    async def empty_stream():
        if False:
            yield None
    mock_client.chat.completions.create = AsyncMock(return_value=empty_stream())
    provider._client = mock_client

    with patch("app.core.config.settings.LLM_MODEL", "llama3"):
        async for _ in provider.generate_stream("سؤال"):
            pass
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert call_kwargs["max_tokens"] >= 200


@pytest.mark.asyncio
async def test_signal_planner_arabic_and_deduplication():
    from app.services.motion.signal_planner import SignalPlanner
    planner = SignalPlanner()
    # [wave] [happy] -> happy also maps to wave, should only trigger wave ONCE
    commands = await planner.extract_from_response("مرحباً بك! [wave] [happy]")
    # Built-in wave has 4 joint commands
    assert len(commands) == 4

    # Arabic tags: [فرحان] maps to wave
    arabic_cmds = await planner.extract_from_response("أهلاً يا باشا [فرحان]")
    assert len(arabic_cmds) == 4
