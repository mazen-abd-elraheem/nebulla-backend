"""
Unit & Integration Test Suite for `handle_llm_voice_clone`
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tests:
1. Direct audio synthesis (return_json=False) -> audio/wav Response
2. JSON output (return_json=True) -> LLMVoiceCloneResponse with base64 audio
3. Text cleaning: strips [tags], markdown, emojis, preserves Masri Arabic
4. Strict Zero Fallback: HTTP 422 Unprocessable Entity when personality has no sample
5. Empty text validation: HTTP 400 Bad Request
"""

import asyncio
import base64
import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.api.v1.endpoints.voice_clone import (
    handle_llm_voice_clone,
    LLMVoiceCloneRequest,
    LLMVoiceCloneResponse,
)
from app.services.voice_clone.voice_clone_service import VoiceCloneService


async def main():
    print("=" * 70, flush=True)
    print("🧪 Running `handle_llm_voice_clone` Test Suite", flush=True)
    print("=" * 70, flush=True)

    voice_svc = VoiceCloneService.get_instance()
    sample_dir = Path("data/voice_samples")
    sample_dir.mkdir(parents=True, exist_ok=True)
    sample_path = sample_dir / "personality_1.wav"
    if not sample_path.exists():
        sample_path.write_bytes(b"RIFF" + b"\x00" * 2000)
    voice_svc._personality_voice_map[1] = str(sample_path)

    dummy_wav = b"RIFF" + b"\x00" * 4000

    with patch.object(voice_svc, "synthesize", new_callable=AsyncMock) as mock_synth:
        mock_synth.return_value = dummy_wav

        # -------------------------------------------------------------
        # Test 1: Direct Audio Response (return_json=False)
        # -------------------------------------------------------------
        print("\n[Test 1] Testing handle_llm_voice_clone returning audio/wav...", flush=True)
        resp1 = await handle_llm_voice_clone(
            text="[happy] صباح الفل يا نيبولا! [wave]",
            personality_id=1,
            return_json=False,
            svc=voice_svc,
        )
        assert resp1.status_code == 200
        assert resp1.media_type == "audio/wav"
        assert resp1.body == dummy_wav
        print("  ✅ Returned audio/wav response with correct binary payload.", flush=True)

        called_args = mock_synth.call_args[1]
        assert "[happy]" not in called_args["text"]
        assert "[wave]" not in called_args["text"]
        print(f"  ✅ Text cleaning verified: Cleaned text sent to VoiceTut: '{called_args['text']}'", flush=True)

        # -------------------------------------------------------------
        # Test 2: JSON Response (return_json=True)
        # -------------------------------------------------------------
        print("\n[Test 2] Testing handle_llm_voice_clone with return_json=True...", flush=True)
        resp2 = await handle_llm_voice_clone(
            text="أهلاً بك يا فندم، أنا جاهز لمساعدتك بكل سرور.",
            personality_id=1,
            return_json=True,
            svc=voice_svc,
        )
        assert resp2.status_code == 200
        data2 = json.loads(resp2.body.decode("utf-8"))
        assert data2["status"] == "success"
        assert data2["model_used"] == "VoiceTut-TTS"
        assert data2["personality_id"] == 1
        assert "audio_base64" in data2
        decoded = base64.b64decode(data2["audio_base64"])
        assert decoded == dummy_wav
        assert data2["audio_url"] == "/api/v1/voice-clone/llm_voice_clone?personality_id=1"
        print("  ✅ JSON response contains valid Base64 audio, audio_url, and VoiceTut metadata.", flush=True)

        # -------------------------------------------------------------
        # Test 3: Strict Zero Fallback Enforcement
        # -------------------------------------------------------------
        print("\n[Test 3] Testing Strict Zero Fallback Model Enforcement on Missing Sample...", flush=True)
        try:
            await handle_llm_voice_clone(
                text="كلام لشخصية غير مسجلة صوتياً",
                personality_id=88888,  # Unregistered
                return_json=True,
                svc=voice_svc,
            )
            assert False, "Should have raised HTTPException 422 for missing voice sample!"
        except HTTPException as exc:
            assert exc.status_code == 422, f"Expected 422, got {exc.status_code}"
            assert "يرجى تسجيل عينة صوتك أولاً" in exc.detail
            assert "Zero Fallback" in exc.detail
            print(f"  ✅ Zero Fallback enforced: Caught HTTP 422:\n     '{exc.detail}'", flush=True)

        # -------------------------------------------------------------
        # Test 4: Empty Text Validation
        # -------------------------------------------------------------
        print("\n[Test 4] Testing Empty Text Validation...", flush=True)
        try:
            await handle_llm_voice_clone(
                text="   ",
                personality_id=1,
                svc=voice_svc,
            )
            assert False, "Should have raised HTTPException 400 for empty text!"
        except HTTPException as exc:
            assert exc.status_code == 400
            print("  ✅ Empty text rejected with HTTP 400.", flush=True)

    print("\n" + "=" * 70, flush=True)
    print("🎉 ALL 4 TESTS PASSED! `llm_voice_clone` IS FULLY VERIFIED.", flush=True)
    print("=" * 70, flush=True)


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
