"""
Unit tests for `llm_voice_clone` endpoint & handler:
- Audio/wav response
- JSON response with return_json=True
- Strict Zero Fallback model enforcement (HTTP 422)
- Text cleaning (markdown, bracket tags, emojis)
- Empty text validation (HTTP 400)
"""

import base64
import json
import os
from unittest.mock import AsyncMock, MagicMock
import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.voice_clone import (
    handle_llm_voice_clone,
    LLMVoiceCloneRequest,
    LLMVoiceCloneResponse,
)


@pytest.mark.asyncio
async def test_llm_voice_clone_wav_response():
    dummy_wav = b"RIFF" + b"\x00" * 4000
    mock_svc = MagicMock()
    mock_svc.has_voice_sample.return_value = True
    mock_svc.get_sample_path.return_value = os.path.abspath(__file__)
    mock_svc.synthesize = AsyncMock(return_value=dummy_wav)

    resp = await handle_llm_voice_clone(
        text="[happy] صباح الفل يا نيبولا! [wave]",
        personality_id=1,
        return_json=False,
        svc=mock_svc,
    )
    assert resp.status_code == 200
    assert resp.media_type == "audio/wav"
    assert resp.body == dummy_wav

    called_text = mock_svc.synthesize.call_args[1]["text"]
    assert "[happy]" not in called_text
    assert "[wave]" not in called_text


@pytest.mark.asyncio
async def test_llm_voice_clone_json_response():
    dummy_wav = b"RIFF" + b"\x00" * 4000
    mock_svc = MagicMock()
    mock_svc.has_voice_sample.return_value = True
    mock_svc.get_sample_path.return_value = os.path.abspath(__file__)
    mock_svc.synthesize = AsyncMock(return_value=dummy_wav)

    resp = await handle_llm_voice_clone(
        text="أهلاً بك، أنا توأمك الرقمي وجاهز لمساعدتك.",
        personality_id=1,
        return_json=True,
        svc=mock_svc,
    )
    assert resp.status_code == 200
    data = json.loads(resp.body.decode("utf-8"))
    assert data["status"] == "success"
    assert data["model_used"] == "VoiceTut-TTS"
    assert data["personality_id"] == 1
    assert "audio_base64" in data
    decoded = base64.b64decode(data["audio_base64"])
    assert decoded == dummy_wav
    assert data["audio_url"] == "/api/v1/voice-clone/llm_voice_clone?personality_id=1"


@pytest.mark.asyncio
async def test_llm_voice_clone_zero_fallback():
    mock_svc = MagicMock()
    mock_svc.has_voice_sample.return_value = False
    mock_svc.get_sample_path.return_value = None

    with pytest.raises(HTTPException) as exc_info:
        await handle_llm_voice_clone(
            text="كلام لشخصية غير مسجلة صوتياً",
            personality_id=88888,
            return_json=True,
            svc=mock_svc,
        )

    assert exc_info.value.status_code == 422
    assert "يرجى تسجيل عينة صوتك أولاً" in exc_info.value.detail
    assert "Zero Fallback" in exc_info.value.detail


@pytest.mark.asyncio
async def test_llm_voice_clone_empty_text():
    mock_svc = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await handle_llm_voice_clone(
            text="   ",
            personality_id=1,
            svc=mock_svc,
        )

    assert exc_info.value.status_code == 400


def test_llm_voice_clone_request_fallback_keys():
    # 1. additionalProp1 fallback
    req = LLMVoiceCloneRequest.model_validate({"additionalProp1": "اهلا بيك"})
    assert req.text == "اهلا بيك"

    # 2. nested dictionary fallback
    req2 = LLMVoiceCloneRequest.model_validate({"additionalProp1": {"msg": "صباح الفل"}})
    assert req2.text == "صباح الفل"

    # 3. prompt / message fallback
    req3 = LLMVoiceCloneRequest.model_validate({"prompt": "ازيك يا نيبولا"})
    assert req3.text == "ازيك يا نيبولا"


def test_repair_malformed_json_user_syntax():
    from app.main import repair_malformed_json

    broken_input = '{\n  "additionalProp1": {" اهلا بيك يا صديقي"}\n}'
    repaired = repair_malformed_json(broken_input)
    parsed = json.loads(repaired)
    assert parsed["additionalProp1"] == " اهلا بيك يا صديقي"

    req = LLMVoiceCloneRequest.model_validate(parsed)
    assert req.text == "اهلا بيك يا صديقي"

