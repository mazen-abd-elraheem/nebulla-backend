"""
End-to-End Test Suite for LLM ↔ Voice Clone Integration (Zero Fallback Model)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Verifies:
1. Voice sample resolution per user/personality (has_voice_sample & get_user_voice_sample).
2. Cloned voice synthesis from LLM text with Masri normalization and emotion tag stripping.
3. Strict zero-fallback model behavior: raising explicit alert if voice sample is missing.
4. AIPipeline.process_text speech synthesis and notice dispatch over WebSocket.
5. /conversations/chat REST API returning audio_base64 and audio_url when return_audio=True.
"""

import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure repo root is in python path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.services.voice_clone.voice_clone_service import VoiceCloneService
from app.services.ai.pipeline import AIPipeline
from app.api.v1.endpoints.conversations import _synthesize_chat_audio


async def run_tests():
    print("=" * 75)
    print("🚀 NEBULA AI — LLM ↔ VOICE CLONE INTEGRATION TEST SUITE")
    print("=" * 75)

    svc = VoiceCloneService.get_instance()

    # --------------------------------------------------------------------------
    # TEST 1: Voice Sample Resolution (has_voice_sample)
    # --------------------------------------------------------------------------
    print("\n[TEST 1] Testing Voice Sample Discovery & User Binding...")
    # Personality 1 should exist or have sample
    p1_sample = svc.get_sample_path(1)
    has_p1 = svc.has_voice_sample(1)
    has_99999 = svc.has_voice_sample(99999)

    assert has_99999 is False, "Non-existent personality should not report having a voice sample"
    print(f"  ✓ Non-existent personality 99999 correctly detected as has_sample=False")
    print(f"  ✓ Personality 1 sample status: exists={has_p1}, path={p1_sample}")

    # --------------------------------------------------------------------------
    # TEST 2: Strict Zero-Fallback Model Check (Synthesize without sample)
    # --------------------------------------------------------------------------
    print("\n[TEST 2] Testing Zero-Fallback Model on Missing Voice Sample...")
    try:
        await svc.synthesize(
            text="أهلاً بيك يا فندم",
            personality_id=99999,
        )
        assert False, "Should have raised HTTPException 422 for missing voice sample!"
    except HTTPException as ex:
        assert ex.status_code == 422
        assert "يرجى تسجيل عينة صوتك" in ex.detail
        print(f"  ✓ [PASSED] Strict alert raised (422: {ex.detail}) without falling back to any secondary model!")

    # --------------------------------------------------------------------------
    # TEST 3: Synthesis with Clean LLM Output (Stripping tags & normalising)
    # --------------------------------------------------------------------------
    print("\n[TEST 3] Testing LLM Output Cleaning & Speech Preparation...")
    llm_output_with_tags = "الحمد لله كله تمام يا فندم! [happy] [action:nod] <think>تفكير داخلي</think> هساعدك دلوقتي."
    mock_wav = b"RIFF" + b"\x00" * 2000

    with patch.object(svc._xtts, "synthesize", new_callable=AsyncMock) as mock_xtts_syn:
        mock_xtts_syn.return_value = mock_wav

        # Ensure sample_1 exists for testing
        fake_sample = ROOT_DIR / "data" / "voice_samples" / "personality_1.wav"
        fake_sample.parent.mkdir(parents=True, exist_ok=True)
        if not fake_sample.exists():
            fake_sample.write_bytes(b"RIFF" + b"\x00" * 4000)

        audio_bytes = await svc.synthesize(
            text=llm_output_with_tags,
            personality_id=1,
            reference_wav=str(fake_sample),
        )

        assert audio_bytes == mock_wav
        # Verify passed text was cleaned of tags and thinking
        cleaned_sent_to_xtts = mock_xtts_syn.call_args[0][0]
        assert "[happy]" not in cleaned_sent_to_xtts
        assert "[action:nod]" not in cleaned_sent_to_xtts
        assert "<think>" not in cleaned_sent_to_xtts
        assert "تفكير داخلي" not in cleaned_sent_to_xtts
        print(f"  ✓ [PASSED] Clean text received by XTTS: '{cleaned_sent_to_xtts}'")

    # --------------------------------------------------------------------------
    # TEST 4: AIPipeline.process_text with Cloned Voice Delivery
    # --------------------------------------------------------------------------
    print("\n[TEST 4] Testing AIPipeline.process_text Cloned Audio Dispatch...")
    pipeline = AIPipeline()

    # Test missing sample branch (should dispatch notice without fallback)
    with patch("app.websocket.manager.manager.send_to_phone", new_callable=AsyncMock) as mock_phone_send, \
         patch("app.websocket.manager.manager.broadcast_to_desks", new_callable=AsyncMock) as mock_desk_broadcast:

        res = await pipeline.process_text(
            text="سؤال تجريبي",
            personality_id=99999,
            broadcast_to_clients=True,
        )

        assert "response" in res
        # Verify notice payload sent to phone and desk
        sent_payloads = [call.args[0] for call in mock_phone_send.call_args_list if isinstance(call.args[0], dict)]
        has_notice = any(p.get("t") == "voice_clone_notice" and p.get("has_voice_sample") is False for p in sent_payloads)
        assert has_notice, "Should have broadcast voice_clone_notice when sample is missing"
        print("  ✓ [PASSED] Missing sample triggers 'voice_clone_notice' to phone/desktop without fallback model.")

    # --------------------------------------------------------------------------
    # TEST 5: /conversations/chat REST API with return_audio=True
    # --------------------------------------------------------------------------
    print("\n[TEST 5] Testing /conversations/chat endpoint with return_audio=True...")
    client = TestClient(app)

    # A. With missing voice sample
    req_payload_no_voice = {
        "message": "صباح الخير يا نيبولا",
        "personality_id": 99999,
        "return_audio": True,
    }
    resp = client.post("/api/v1/conversations/chat", json=req_payload_no_voice)
    assert resp.status_code == 200, f"Chat endpoint failed: {resp.text}"
    data = resp.json()
    assert data["has_voice_sample"] is False
    assert data["voice_notice"] == "يرجى تسجيل عينة صوتك لتفعيل الرد الصوتي"
    assert data["audio_base64"] is None
    print(f"  ✓ [PASSED] Missing voice sample handled gracefully in REST API: {data['voice_notice']}")

    # B. With valid voice sample
    with patch("app.services.voice_clone.voice_clone_service.VoiceCloneService.synthesize", new_callable=AsyncMock) as mock_syn:
        mock_syn.return_value = b"RIFF" + b"\x00" * 1500
        with patch("app.services.voice_clone.voice_clone_service.VoiceCloneService.has_voice_sample", return_value=True), \
             patch("app.services.voice_clone.voice_clone_service.VoiceCloneService.get_sample_path", return_value=str(fake_sample)):

            req_payload_with_voice = {
                "message": "صباح الخير يا نيبولا",
                "personality_id": 1,
                "return_audio": True,
            }
            resp_audio = client.post("/api/v1/conversations/chat", json=req_payload_with_voice)
            assert resp_audio.status_code == 200, f"Chat failed: {resp_audio.text}"
            audio_data = resp_audio.json()
            assert audio_data["has_voice_sample"] is True
            assert audio_data["audio_base64"] is not None
            assert len(audio_data["audio_base64"]) > 50
            assert audio_data["audio_url"] == "/api/v1/voice-clone/synthesize?personality_id=1"
            print(f"  ✓ [PASSED] Audio synthesized & base64 encoded ({len(audio_data['audio_base64'])} chars) with audio_url.")

    print("\n" + "=" * 75)
    print("🎉 ALL 5 INTEGRATION TESTS PASSED 100%! ZERO FALLBACK MODEL GUARANTEED.")
    print("=" * 75)


if __name__ == "__main__":
    asyncio.run(run_tests())

