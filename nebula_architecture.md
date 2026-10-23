# Nebula Backend — Architecture Overview

## System Topology (doc §4)

```
📱 Flutter Phone    ←── ws/phone ──→  ┌─────────────────────────┐
🖥️ Flutter Desktop  ←── ws/desk  ──→  │     Nebula Backend      │
🔌 ESP32 Firmware   ←── ws/esp   ──→  │  FastAPI on local PC    │
                                      └─────────────────────────┘
                                              │
                          ┌───────────────────┼───────────────────┐
                       AI Pipeline       Services           REST API
                       STT→LLM→TTS      Vision             /auth
                       XTTS v2          Motion Guard       /personalities
                       RAG Memory       Signal Planner     /memories
                                                           /voice-clone
                                                           /diagnostics
```

## All 79 Python Files

| Path | Purpose |
|------|---------|
| `app/main.py` | FastAPI entry point, lifespan, CORS, router registration |
| **`app/auth/`** | **🔐 Authentication** |
| `app/auth/jwt.py` | JWT helpers + FastAPI `get_current_user` dependency |
| `app/auth/models.py` | APIKey ORM model |
| `app/auth/router.py` | `POST /auth/token`, `GET /auth/me` |
| **`app/core/`** | **⚙️ Core** |
| `app/core/config.py` | All settings via `.env` (swappable providers) |
| `app/core/logger.py` | Rotating file + console logger |
| `app/core/security.py` | Pairing code verify + per-device rate limiter |
| **`app/db/`** | **🗃️ Database** |
| `app/db/session.py` | Async SQLAlchemy engine + `get_db()` dependency |
| **`app/models/`** | **📋 ORM Models** |
| `app/models/device.py` | Phone / Desktop / ESP32 device records |
| `app/models/personality.py` | Robot personality profiles |
| `app/models/memory.py` | Long-term memories (RAG store with embeddings) |
| `app/models/conversation.py` | Sessions + messages with latency fields |
| `app/models/signal.py` | Named gesture sequences → joint commands |
| `app/models/calibration.py` | Per-servo min/max/home angles |
| `app/models/tracking.py` | Telemetry time-series |
| `app/models/log.py` | System event log |
| **`app/websocket/`** | **🔌 WebSocket Hub** |
| `app/websocket/hub.py` | Routes: `/ws/phone` `/ws/desk` `/ws/esp` |
| `app/websocket/manager.py` | `ConnectionManager` singleton — all fan-out logic |
| `app/websocket/handlers.py` | Per-channel message processing loops |
| `app/websocket/messages.py` | Typed Pydantic schemas for all WS messages |
| **`app/services/ai/`** | **🤖 AI Pipeline** |
| `app/services/ai/pipeline.py` | STT→LLM→TTS with first-sentence streaming |
| **`app/services/vision/`** | **👁️ Vision** |
| `app/services/vision/face_service.py` | UniFace integration, EMA gaze smoothing |
| **`app/services/motion/`** | **🦾 Motion** |
| `app/services/motion/motion_guard.py` | Servo angle clamping + speed validation |
| `app/services/motion/signal_planner.py` | `[tag]` → joint commands resolver |
| **`app/services/memory/`** | **🧠 Memory** |
| `app/services/memory/rag_service.py` | Cosine similarity retrieval + memory add |
| **`app/services/voice_clone/`** | **🎙️ Voice Clone** |
| `app/services/voice_clone/voice_clone_service.py` | WAV upload + XTTS synthesis management |
| **`app/providers/stt/`** | **STT Providers** |
| `app/providers/stt/factory.py` | `get_stt_provider(name)` factory |
| `app/providers/stt/qwencleo.py` | QwenCleo-ASR — Egyptian Arabic primary |
| `app/providers/stt/whisper.py` | Whisper large-v3 fallback |
| `app/providers/stt/nemotron.py` | Nemotron stub |
| **`app/providers/tts/`** | **TTS Providers** |
| `app/providers/tts/factory.py` | `get_tts_provider(name)` factory |
| `app/providers/tts/voicetut.py` | VoiceTut (OmniVoice fine-tune on Egyptian podcasts) |
| `app/providers/tts/ar_eg_free.py` | gTTS free fallback (no GPU needed) |
| `app/providers/tts/xtts/provider.py` | ⭐ **XTTS v2 zero-shot voice clone** |
| **`app/providers/llm/`** | **LLM Providers** |
| `app/providers/llm/factory.py` | `get_llm_provider(name)` factory |
| `app/providers/llm/local_ollama.py` | Local Ollama streaming with Egyptian prompt |
| `app/providers/llm/openai_provider.py` | OpenAI + Anthropic |
| **`app/api/v1/endpoints/`** | **REST Endpoints** |
| `endpoints/devices.py` | `GET /status`, list, delete devices |
| `endpoints/personalities.py` | Full CRUD + `POST /{id}/activate` |
| `endpoints/memories.py` | CRUD + `GET /search?q=...` semantic search |
| `endpoints/conversations.py` | Read-only conversation + message history |
| `endpoints/signals.py` | CRUD + `POST /{name}/fire` immediate dispatch |
| `endpoints/calibration.py` | `PUT /{servo_id}`, `POST /reset` home all servos |
| `endpoints/voice_clone.py` | `POST /upload`, `POST /synthesize`, `POST /test` |
| `endpoints/settings.py` | `GET /`, `PATCH /providers` hot-swap |
| `endpoints/diagnostics.py` | Servo/motor/LED test + emergency stop |

## REST API Endpoint Groups

| Prefix | Key Endpoints |
|--------|--------------|
| `POST /api/v1/auth/token` | Exchange pairing code → JWT |
| `GET /api/v1/devices/status` | Live phone/desk/ESP32 connection state |
| `GET/POST/PATCH/DELETE /api/v1/personalities` | Robot character CRUD + activate |
| `GET/POST/DELETE /api/v1/memories` | Memory CRUD + `GET /search?q=` |
| `GET /api/v1/conversations/{id}/messages` | Live conversation history |
| `POST /api/v1/signals/{name}/fire` | Trigger a named gesture now |
| `PUT /api/v1/calibration/{servo_id}` | Set servo min/max/home |
| `POST /api/v1/voice-clone/upload/{id}` | Upload WAV reference sample |
| `POST /api/v1/voice-clone/synthesize` | Synthesise text in cloned voice |
| `PATCH /api/v1/settings/providers` | Hot-swap STT/TTS/LLM at runtime |
| `POST /api/v1/diagnostics/emergency-stop` | 🚨 Stop everything immediately |

## Auth Flow

```
Device              Backend
  │                    │
  ├─ POST /auth/token ►│  body: { pairing_code, device_name }
  │◄── { access_token }┤
  │                    │
  ├─ GET /api/v1/... ─►│  header: X-API-Key or Bearer <token>
  │◄──── response ─────┤
  │                    │
  ├─ WS /ws/phone?pairing_code=... ►│
  │◄──────── WebSocket open ────────┤
```

## Voice Clone Pipeline (XTTS v2)

```
1. Upload WAV    →  POST /voice-clone/upload/{personality_id}
                    Validates: WAV format, min 3s, max 120s
2. Stored at     →  data/voice_samples/personality_{id}.wav
3. AI response   →  pipeline.py calls VoiceCloneService.synthesize(text, pid)
4. XTTS v2       →  provider.py clones voice from reference WAV
5. WAV bytes     →  streamed back to phone over ws/phone binary channel
```

## WebSocket JSON Protocol (doc §6)

```json
// Phone → Backend  (binary: raw PCM audio)
// Phone → Backend  (binary: JPEG camera frame 320×240)

// Backend → Phone
{ "t": "eyes", "mood": "happy" }
{ "t": "gaze", "x": 0.2, "y": -0.1 }
{ "t": "text_stream", "token": "أهلاً", "is_final": false }
// + binary WAV audio chunks

// Desktop → Backend
{ "t": "cmd", "gesture": "like" }
{ "t": "cmd", "joint_id": 3, "angle": 90, "speed_ms": 300 }

// Backend → ESP32
{ "t": "joint", "id": 3, "deg": 90, "ms": 300 }
{ "t": "motor", "left": 128, "right": 128 }
{ "t": "stop" }
{ "t": "led", "state": "blink_fast" }

// ESP32 → Backend
{ "t": "tele", "bat": 7.6, "dist": 85 }
{ "t": "error", "code": "OVERCURRENT", "message": "..." }
```

## Safety Layers (doc §4 + §10)

| Layer | Where | What it does |
|-------|-------|-------------|
| Pairing Code | WS channels + REST | Rejects unknown devices before accepting connection |
| JWT/API Key | All REST endpoints | Only authenticated clients can call the API |
| Rate Limiter | `core/security.py` | Max 20 commands/sec per device |
| Motion Guard | `services/motion/motion_guard.py` | Clamps angles to calibrated min/max, rejects speed < 50ms |
| ESP32 Watchdog | Firmware (not in this repo) | Robot stops safely on WiFi disconnect |
| Emergency Stop | `diagnostics.py` | `POST /emergency-stop` broadcasts stop to all channels |

## Provider Swap — No Code Changes Required

```env
# .env — change and restart (or hot-swap via PATCH /settings/providers)
STT_PROVIDER=qwencleo    # qwencleo | whisper | nemotron
TTS_PROVIDER=xtts        # xtts | voicetut | ar_eg_free
LLM_PROVIDER=local       # local | openai | anthropic
```

## Latency Budget (doc §6.3, target 1.5–3 s total)

| Stage | Target | Optimisation |
|-------|--------|-------------|
| VAD silence detect | 0.25–0.30 s | WebRTC VAD in pipeline |
| STT (QwenCleo) | 0.20–0.60 s | Streaming on NVIDIA GPU |
| LLM first token | 0.30–0.80 s | Ollama streaming, reply ≤ 2 sentences |
| TTS first sentence | 0.50–1.70 s | XTTS, first sentence ≤ 8 words |
| Network (local WiFi) | ~0.10 s | Router on same LAN |
| **Total** | **1.5–3 s** | Head-nod on VAD end hides latency |

## Quick Start

```bash
cd nebulla-backend
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # edit PAIRING_SECRET at minimum
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# → open http://localhost:8000/docs
```
