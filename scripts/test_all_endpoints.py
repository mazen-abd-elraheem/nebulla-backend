"""
Comprehensive Test Suite for ALL Nebula Backend Endpoints.
Tests every REST route with realistic data and authenticates using pairing code / JWT.
"""

import asyncio
import io
import json
import os
import sys
import time
import wave
import numpy as np
from PIL import Image
from httpx import AsyncClient, ASGITransport

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from app.core.config import settings
from app.db.session import init_db


def make_test_wav_bytes(duration_s: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Generate a valid PCM 16-bit mono WAV in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        # 440 Hz gentle sine tone
        t = np.linspace(0, duration_s, int(sample_rate * duration_s), endpoint=False)
        audio = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)
        wf.writeframes(audio.tobytes())
    return buf.getvalue()


def make_test_jpeg_bytes() -> bytes:
    """Generate a valid test JPEG image."""
    img = Image.new("RGB", (128, 128), color=(220, 160, 120))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


async def run_all_endpoint_tests():
    print("=" * 70)
    print("🚀 بدء الفحص الشامل لجميع الـ Endpoints في Nebula Backend")
    print("=" * 70)

    await init_db()
    transport = ASGITransport(app=app)

    passed = 0
    failed = 0
    results = []

    def log_result(name: str, ok: bool, details: str = ""):
        nonlocal passed, failed
        if ok:
            passed += 1
            print(f"✅ PASS | {name}")
            if details:
                print(f"       تفاصيل: {details}")
        else:
            failed += 1
            print(f"❌ FAIL | {name}")
            if details:
                print(f"       خطأ: {details}")
        results.append((name, ok, details))

    async with AsyncClient(transport=transport, base_url="http://testserver", timeout=60.0) as client:
        # ──────────────────────────────────────────────────────────────────
        # 1. Health & Core
        # ──────────────────────────────────────────────────────────────────
        try:
            r = await client.get("/health")
            log_result("1. GET /health", r.status_code == 200, f"Status: {r.json()}")
        except Exception as e:
            log_result("1. GET /health", False, str(e))

        try:
            r = await client.get("/docs")
            log_result("2. GET /docs (Swagger UI)", r.status_code == 200, f"HTML size: {len(r.content)} bytes")
        except Exception as e:
            log_result("2. GET /docs", False, str(e))

        try:
            r = await client.get("/chat")
            log_result("3. GET /chat (Web Playground UI)", r.status_code == 200, f"HTML size: {len(r.content)} bytes")
        except Exception as e:
            log_result("3. GET /chat", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 2. Auth (Pairing code -> JWT -> /me)
        # ──────────────────────────────────────────────────────────────────
        token = ""
        auth_headers = {}
        try:
            r = await client.post(
                "/api/v1/auth/token",
                json={"pairing_code": settings.PAIRING_SECRET, "device_name": "control_room_desktop"},
            )
            ok = r.status_code == 200 and "access_token" in r.json()
            if ok:
                token = r.json()["access_token"]
                auth_headers = {"Authorization": f"Bearer {token}"}
            log_result("4. POST /api/v1/auth/token", ok, f"Token generated (first 20 chars: {token[:20]}...)")
        except Exception as e:
            log_result("4. POST /api/v1/auth/token", False, str(e))

        try:
            r = await client.get("/api/v1/auth/me", headers=auth_headers)
            ok = r.status_code == 200 and r.json().get("identity") == "control_room_desktop"
            log_result("5. GET /api/v1/auth/me", ok, f"Current identity: {r.json()}")
        except Exception as e:
            log_result("5. GET /api/v1/auth/me", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 3. Devices
        # ──────────────────────────────────────────────────────────────────
        try:
            r = await client.get("/api/v1/devices/status", headers=auth_headers)
            log_result("6. GET /api/v1/devices/status", r.status_code == 200, f"Channels: {r.json().get('channels')}")
        except Exception as e:
            log_result("6. GET /api/v1/devices/status", False, str(e))

        try:
            r = await client.get("/api/v1/devices/", headers=auth_headers)
            log_result("7. GET /api/v1/devices/", r.status_code == 200, f"Count: {len(r.json().get('devices', []))}")
        except Exception as e:
            log_result("7. GET /api/v1/devices/", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 4. Personalities (CRUD + Activate)
        # ──────────────────────────────────────────────────────────────────
        pid = None
        try:
            r = await client.get("/api/v1/personalities/")
            log_result("8. GET /api/v1/personalities/", r.status_code == 200, f"Existing: {len(r.json().get('personalities', []))}")
        except Exception as e:
            log_result("8. GET /api/v1/personalities/", False, str(e))

        try:
            r = await client.post(
                "/api/v1/personalities/",
                json={
                    "name": "نيبولا المصري الودود",
                    "description": "شخصية الروبوت المصري المتحدث بالعامية",
                    "system_prompt": "أنت الروبوت نيبولا، اتكلم مصري ودود وخفيف الظل.",
                    "dialect": "cairo",
                    "language_mix": "ar",
                },
                headers=auth_headers,
            )
            ok = r.status_code == 201
            if ok:
                pid = r.json()["id"]
            log_result("9. POST /api/v1/personalities/ (Create)", ok, f"Created personality ID: {pid}")
        except Exception as e:
            log_result("9. POST /api/v1/personalities/", False, str(e))

        if pid:
            try:
                r = await client.get(f"/api/v1/personalities/{pid}")
                log_result("10. GET /api/v1/personalities/{pid}", r.status_code == 200, f"Name: {r.json().get('name')}")
            except Exception as e:
                log_result("10. GET /api/v1/personalities/{pid}", False, str(e))

            try:
                r = await client.patch(
                    f"/api/v1/personalities/{pid}",
                    json={"description": "تم التحديث - شخصية الذكاء الاصطناعي المصري"},
                    headers=auth_headers,
                )
                log_result("11. PATCH /api/v1/personalities/{pid}", r.status_code == 200, f"Updated: {r.json().get('description')}")
            except Exception as e:
                log_result("11. PATCH /api/v1/personalities/{pid}", False, str(e))

            try:
                r = await client.post(f"/api/v1/personalities/{pid}/activate", headers=auth_headers)
                log_result("12. POST /api/v1/personalities/{pid}/activate", r.status_code == 200, f"Active ID: {r.json().get('active_personality_id')}")
            except Exception as e:
                log_result("12. POST /api/v1/personalities/{pid}/activate", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 5. Memories & Semantic RAG Search
        # ──────────────────────────────────────────────────────────────────
        mid = None
        try:
            r = await client.post(
                "/api/v1/memories/",
                json={
                    "content": "الروبوت نيبولا مزود بمحركات سيرفو MG996R وبطارية ليثيوم 12 فولت ومستشعر مسافات فوق صوتي.",
                    "personality_id": pid or 1,
                    "importance": 5,
                },
            )
            ok = r.status_code == 201
            if ok:
                mid = r.json()["id"]
            log_result("13. POST /api/v1/memories/ (Add Memory)", ok, f"Memory ID: {mid}")
        except Exception as e:
            log_result("13. POST /api/v1/memories/", False, str(e))

        try:
            r = await client.get(f"/api/v1/memories/?personality_id={pid or 1}")
            log_result("14. GET /api/v1/memories/", r.status_code == 200, f"Count: {len(r.json().get('memories', []))}")
        except Exception as e:
            log_result("14. GET /api/v1/memories/", False, str(e))

        try:
            r = await client.get("/api/v1/memories/search?q=بطارية ومحركات الروبوت&detailed=true")
            ok = r.status_code == 200 and len(r.json().get("results", [])) > 0
            res_content = r.json().get("results", [{}])[0].get("content", "") if ok else ""
            log_result("15. GET /api/v1/memories/search (Hybrid RAG)", ok, f"Found: {res_content[:60]}...")
        except Exception as e:
            log_result("15. GET /api/v1/memories/search", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 6. Conversations & Grounded LLM Chat (REST & SSE Stream)
        # ──────────────────────────────────────────────────────────────────
        conv_session = f"test-session-{int(time.time())}"
        try:
            r = await client.post(
                "/api/v1/conversations/chat",
                json={
                    "message": "إيه مواصفات البطارية والمحركات في نيبولا؟",
                    "personality_id": pid or 1,
                    "session_id": conv_session,
                    "stream": False,
                },
            )
            ok = r.status_code == 200
            reply = r.json().get("reply", "") if ok else ""
            log_result("16. POST /api/v1/conversations/chat (REST)", ok, f"Reply: {reply[:65]}... | Model: {r.json().get('llm_model')}")
        except Exception as e:
            log_result("16. POST /api/v1/conversations/chat", False, str(e))

        try:
            r = await client.post(
                "/api/v1/conversations/chat/stream",
                json={
                    "message": "عرف نفسك باختصار",
                    "personality_id": pid or 1,
                    "session_id": conv_session,
                },
            )
            ok = r.status_code == 200 and "text/event-stream" in r.headers.get("content-type", "")
            events_count = len(r.text.split("data: ")) - 1
            log_result("17. POST /api/v1/conversations/chat/stream (SSE)", ok, f"Received {events_count} SSE chunks")
        except Exception as e:
            log_result("17. POST /api/v1/conversations/chat/stream", False, str(e))

        try:
            r = await client.get("/api/v1/conversations/?limit=5")
            ok = r.status_code == 200 and len(r.json().get("conversations", [])) > 0
            conv_id = r.json()["conversations"][0]["id"] if ok else 1
            log_result("18. GET /api/v1/conversations/", ok, f"Sessions found: {len(r.json().get('conversations', []))}")
        except Exception as e:
            log_result("18. GET /api/v1/conversations/", False, str(e))
            conv_id = 1

        try:
            r = await client.get(f"/api/v1/conversations/{conv_id}/messages")
            ok = r.status_code == 200
            msgs_count = len(r.json().get("messages", []))
            log_result(f"19. GET /api/v1/conversations/{conv_id}/messages", ok, f"Total messages with latency metrics: {msgs_count}")
        except Exception as e:
            log_result(f"19. GET /api/v1/conversations/{conv_id}/messages", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 7. Motion Signals & Calibration
        # ──────────────────────────────────────────────────────────────────
        sig_id = None
        try:
            r = await client.get("/api/v1/signals/", headers=auth_headers)
            log_result("20. GET /api/v1/signals/", r.status_code == 200, f"Signals count: {len(r.json().get('signals', []))}")
        except Exception as e:
            log_result("20. GET /api/v1/signals/", False, str(e))

        try:
            r = await client.post(
                "/api/v1/signals/",
                json={
                    "name": "test_dance_gesture",
                    "description": "حركة اختبارية للتحية والرقص",
                    "joint_commands_json": json.dumps([
                        {"t": "joint", "id": 4, "deg": 80, "ms": 300},
                        {"t": "joint", "id": 4, "deg": 100, "ms": 300},
                        {"t": "joint", "id": 4, "deg": 90, "ms": 300},
                    ]),
                    "emotion_tag": "happy",
                },
                headers=auth_headers,
            )
            ok = r.status_code == 201
            if ok:
                sig_id = r.json()["id"]
            log_result("21. POST /api/v1/signals/ (Create)", ok, f"Signal ID: {sig_id}")
        except Exception as e:
            log_result("21. POST /api/v1/signals/", False, str(e))

        try:
            r = await client.post("/api/v1/signals/wave/fire", headers=auth_headers)
            ok = r.status_code == 200 and r.json().get("fired") == "wave"
            log_result("22. POST /api/v1/signals/wave/fire", ok, f"Fired: {r.json()}")
        except Exception as e:
            log_result("22. POST /api/v1/signals/wave/fire", False, str(e))

        try:
            r = await client.get("/api/v1/calibration/", headers=auth_headers)
            log_result("23. GET /api/v1/calibration/", r.status_code == 200, f"Calibrations count: {len(r.json().get('calibrations', []))}")
        except Exception as e:
            log_result("23. GET /api/v1/calibration/", False, str(e))

        try:
            r = await client.put(
                "/api/v1/calibration/3",
                json={"label": "head_pitch_servo", "min_angle": 30.0, "max_angle": 150.0, "home_angle": 90.0},
                headers=auth_headers,
            )
            ok = r.status_code == 200 and r.json().get("servo_id") == 3
            log_result("24. PUT /api/v1/calibration/3", ok, f"Calibrated: {r.json().get('label')}")
        except Exception as e:
            log_result("24. PUT /api/v1/calibration/3", False, str(e))

        try:
            r = await client.post("/api/v1/calibration/reset", headers=auth_headers)
            log_result("25. POST /api/v1/calibration/reset", r.status_code == 200, f"Response: {r.json().get('message')}")
        except Exception as e:
            log_result("25. POST /api/v1/calibration/reset", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 8. Audio (VoiceTut TTS, Speakers & Transcribe STT)
        # ──────────────────────────────────────────────────────────────────
        try:
            r = await client.get("/api/v1/audio/speakers")
            ok = r.status_code == 200 and "speakers" in r.json()
            log_result("26. GET /api/v1/audio/speakers", ok, f"Egyptian speakers: {r.json().get('speakers')}")
        except Exception as e:
            log_result("26. GET /api/v1/audio/speakers", False, str(e))

        try:
            r = await client.post(
                "/api/v1/audio/voicetut",
                data={"text": "أهلاً وسهلاً بك في نيبولا، أنا سعيد جداً بمساعدتك!", "speaker": "mohammed"},
            )
            ok = r.status_code == 200 and len(r.content) > 1000 and r.headers.get("content-type") == "audio/wav"
            log_result("27. POST /api/v1/audio/voicetut (TTS Synthesis)", ok, f"WAV Audio: {len(r.content):,} bytes")
        except Exception as e:
            log_result("27. POST /api/v1/audio/voicetut", False, str(e))

        try:
            test_wav = make_test_wav_bytes(duration_s=2.0)
            files = {"file": ("speech_sample.wav", test_wav, "audio/wav")}
            r = await client.post("/api/v1/audio/transcribe", files=files)
            ok = r.status_code == 200 and r.json().get("success") is True
            log_result("28. POST /api/v1/audio/transcribe (STT)", ok, f"Result: {r.json()}")
        except Exception as e:
            log_result("28. POST /api/v1/audio/transcribe", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 9. Voice Clone Endpoints
        # ──────────────────────────────────────────────────────────────────
        try:
            sample_wav = make_test_wav_bytes(duration_s=2.5)
            files = {"file": ("my_egyptian_voice.wav", sample_wav, "audio/wav")}
            data = {"transcript": "أهلاً يا نيبولا ده تسجيلي الصوتي علشان تستنسخه", "personality_id": str(pid or 1)}
            r = await client.post("/api/v1/voice-clone/upload", files=files, data=data)
            ok = r.status_code == 201
            log_result("29. POST /api/v1/voice-clone/upload", ok, f"Saved to: {r.json().get('path')}")
        except Exception as e:
            log_result("29. POST /api/v1/voice-clone/upload", False, str(e))

        try:
            r = await client.get("/api/v1/voice-clone/samples")
            ok = r.status_code == 200 and "samples" in r.json()
            log_result("30. GET /api/v1/voice-clone/samples", ok, f"Profiles: {len(r.json().get('samples', []))}")
        except Exception as e:
            log_result("30. GET /api/v1/voice-clone/samples", False, str(e))

        try:
            r = await client.post(
                "/api/v1/voice-clone/synthesize",
                json={
                    "text": "صباح الخير يا فندم، أنا الروبوت نيبولا وبكلمك بصوتك المصري المستنسخ تماماً.",
                    "personality_id": pid or 1,
                    "language": "ar",
                },
            )
            ok = r.status_code == 200 and len(r.content) > 1000
            log_result("31. POST /api/v1/voice-clone/synthesize (WAV output)", ok, f"Cloned Audio size: {len(r.content):,} bytes")
        except Exception as e:
            log_result("31. POST /api/v1/voice-clone/synthesize", False, str(e))

        try:
            r = await client.post(f"/api/v1/voice-clone/test?personality_id={pid or 1}")
            ok = r.status_code == 200 and len(r.content) > 1000
            log_result("32. POST /api/v1/voice-clone/test", ok, f"Quick Voice test WAV: {len(r.content):,} bytes")
        except Exception as e:
            log_result("32. POST /api/v1/voice-clone/test", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 10. Vision / UniFace & Faces
        # ──────────────────────────────────────────────────────────────────
        try:
            r = await client.get("/api/v1/faces", headers=auth_headers)
            log_result("33. GET /api/v1/faces", r.status_code == 200, f"Registered faces count: {len(r.json().get('faces', []))}")
        except Exception as e:
            log_result("33. GET /api/v1/faces", False, str(e))

        try:
            r = await client.get("/api/v1/faces/current", headers=auth_headers)
            ok = r.status_code == 200 and "detected" in r.json()
            log_result("34. GET /api/v1/faces/current (Live Tracking)", ok, f"Current: {r.json()}")
        except Exception as e:
            log_result("34. GET /api/v1/faces/current", False, str(e))

        try:
            from unittest.mock import patch
            jpeg_bytes = make_test_jpeg_bytes()
            files = {"file": ("engineer_face.jpg", jpeg_bytes, "image/jpeg")}
            data = {"name": "مهندس_نيبولا"}
            # Use real or mocked embedding for registration
            with patch("app.services.vision.face_service.FaceService.extract_embedding_sync", return_value=[0.05] * 128):
                r = await client.post("/api/v1/faces/register", data=data, files=files, headers=auth_headers)
            ok = r.status_code == 200
            log_result("35. POST /api/v1/faces/register (UniFace Embeddings)", ok, f"Registered: {r.json()}")
        except Exception as e:
            log_result("35. POST /api/v1/faces/register", False, str(e))

        try:
            r = await client.delete("/api/v1/faces/مهندس_نيبولا", headers=auth_headers)
            log_result("36. DELETE /api/v1/faces/{name}", r.status_code == 200, f"Deleted: {r.json().get('message')}")
        except Exception as e:
            log_result("36. DELETE /api/v1/faces/{name}", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 11. Settings & Provider Hot-swap
        # ──────────────────────────────────────────────────────────────────
        try:
            r = await client.get("/api/v1/settings/", headers=auth_headers)
            ok = r.status_code == 200 and "llm_model" in r.json()
            log_result("37. GET /api/v1/settings/", ok, f"Settings: LLM={r.json().get('llm_model')}, TTS={r.json().get('tts_provider')}")
        except Exception as e:
            log_result("37. GET /api/v1/settings/", False, str(e))

        try:
            r = await client.patch(
                "/api/v1/settings/providers",
                json={"llm_model": "nebula-masri"},
                headers=auth_headers,
            )
            log_result("38. PATCH /api/v1/settings/providers", r.status_code == 200, f"Hot-swap response: {r.json()}")
        except Exception as e:
            log_result("38. PATCH /api/v1/settings/providers", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 12. Diagnostics & Emergency Stop
        # ──────────────────────────────────────────────────────────────────
        try:
            r = await client.get("/api/v1/diagnostics/status", headers=auth_headers)
            ok = r.status_code == 200 and r.json().get("backend") == "ok"
            log_result("39. GET /api/v1/diagnostics/status", ok, f"Backend status: {r.json()}")
        except Exception as e:
            log_result("39. GET /api/v1/diagnostics/status", False, str(e))

        try:
            r = await client.post("/api/v1/diagnostics/emergency-stop", headers=auth_headers)
            ok = r.status_code == 200
            log_result("40. POST /api/v1/diagnostics/emergency-stop", ok, f"Safety stop triggered: {r.json()}")
        except Exception as e:
            log_result("40. POST /api/v1/diagnostics/emergency-stop", False, str(e))

        # ──────────────────────────────────────────────────────────────────
        # 13. Cleanup Test Artifacts
        # ──────────────────────────────────────────────────────────────────
        if mid:
            try:
                r = await client.delete(f"/api/v1/memories/{mid}")
                log_result("41. DELETE /api/v1/memories/{mid}", r.status_code == 204, f"Cleaned memory {mid}")
            except Exception as e:
                log_result("41. DELETE /api/v1/memories/{mid}", False, str(e))

        if sig_id:
            try:
                r = await client.delete(f"/api/v1/signals/{sig_id}", headers=auth_headers)
                log_result("42. DELETE /api/v1/signals/{sid}", r.status_code == 204, f"Cleaned signal {sig_id}")
            except Exception as e:
                log_result("42. DELETE /api/v1/signals/{sid}", False, str(e))

        if pid:
            try:
                r = await client.delete(f"/api/v1/personalities/{pid}", headers=auth_headers)
                log_result("43. DELETE /api/v1/personalities/{pid}", r.status_code == 204, f"Cleaned personality {pid}")
            except Exception as e:
                log_result("43. DELETE /api/v1/personalities/{pid}", False, str(e))

    print("=" * 70)
    total = passed + failed
    pct = (passed / total * 100) if total else 0
    print(f"📊 نتيجة فحص جميع الـ Endpoints: نجح {passed} من أصل {total} ({pct:.1f}%)")
    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(run_all_endpoint_tests())
    sys.exit(0 if success else 1)
