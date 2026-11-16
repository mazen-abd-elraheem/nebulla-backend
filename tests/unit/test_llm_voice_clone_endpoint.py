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
    SynthesizeRequest,
    _resolve_steps_and_params,
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


@pytest.mark.asyncio
async def test_upload_voice_sample_auto_enrolls_with_samples_kwarg(tmp_path):
    """Verify upload_voice_sample reads audio bytes via pathlib.Path and calls spk_svc.enroll(samples=...)."""
    from types import SimpleNamespace
    from unittest.mock import patch
    from app.api.v1.endpoints.voice_clone import upload_voice_sample

    sample_wav = tmp_path / "personality_7.wav"
    sample_wav.write_bytes(b"RIFF" + b"\x00" * 100)

    mock_svc = MagicMock()
    mock_svc.upload_sample = AsyncMock(return_value=str(sample_wav))

    fake_personality = SimpleNamespace(id=7, user_id=3, name="مازن", voice_sample_path=None)
    fake_res = MagicMock()
    fake_res.scalar_one_or_none.return_value = fake_personality

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=fake_res)
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    mock_spk_svc = MagicMock()
    mock_spk_svc.enroll = AsyncMock()

    with patch("app.services.voice_verification.speaker_service.get_speaker_service", return_value=mock_spk_svc):
        out = await upload_voice_sample(
            personality_id=7,
            file=MagicMock(),
            transcript="أهلاً بيكم",
            db=mock_db,
            _user=None,
            svc=mock_svc,
        )

    assert out["personality_id"] == 7
    assert out["path"] == str(sample_wav)
    mock_spk_svc.enroll.assert_awaited_once()
    kwargs = mock_spk_svc.enroll.call_args.kwargs
    assert "audio_data" not in kwargs
    assert kwargs["samples"] == sample_wav.read_bytes()
    assert kwargs["user_id"] == 3
    assert kwargs["speaker_name"] == "مازن"
    assert kwargs["personality_id"] == 7
    assert mock_db.commit.await_count == 2
    mock_db.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_voicetut_fast_defaults_and_step_clamp():
    """Verify fast 14-step defaults, 20-step ceiling clamp unless studio_hq=True, and explicit cfg=0.0 support."""
    from app.core.config import settings

    assert settings.VOICETUT_NUM_STEPS == 14
    assert settings.VOICETUT_MAX_STEPS == 20
    assert settings.VOICETUT_GUIDANCE_SCALE == 2.1

    req = SynthesizeRequest(text="أهلاً")
    assert req.num_steps == 14
    assert req.guidance_scale == 2.1
    assert req.speed == 1.0
    assert req.studio_hq is False

    llm_req = LLMVoiceCloneRequest()
    assert llm_req.num_steps == 14
    assert llm_req.guidance_scale == 2.1
    assert llm_req.speed == 1.0
    assert llm_req.studio_hq is False

    steps_clamped, cfg_clamped, spd = _resolve_steps_and_params(48, 2.6, 1.0, studio_hq=False)
    assert steps_clamped == 20
    assert cfg_clamped == 2.6
    assert spd == 1.0

    steps_hq, cfg_zero, _ = _resolve_steps_and_params(48, 0.0, 1.0, studio_hq=True)
    assert steps_hq == 48
    assert cfg_zero == 0.0

    mock_svc = MagicMock()
    mock_svc.has_voice_sample.return_value = True
    mock_svc.get_sample_path.return_value = os.path.abspath(__file__)
    mock_svc.synthesize = AsyncMock(return_value=b"RIFF" + b"\x00" * 4000)

    await handle_llm_voice_clone(
        text="بقولكم ايه",
        personality_id=1,
        num_steps=48,
        studio_hq=False,
        svc=mock_svc,
    )
    assert mock_svc.synthesize.call_args.kwargs["num_step"] == 20


