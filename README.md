# 🤖 Nebula Backend — Digital Twin Robot

**FastAPI backend for the Nebula Digital Twin Robot project (v3.0)**

Connects the Flutter phone app (robot face), Flutter desktop app (control room), and ESP32 firmware over WebSocket — and runs the full Egyptian Arabic AI pipeline.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Nebula Backend                          │
│                      (FastAPI on PC/Server)                     │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │  WebSocket   │  │  AI Pipeline │  │    REST API v1        │  │
│  │     Hub      │  │              │  │                       │  │
│  │  /ws/phone   │  │  STT         │  │  /auth/token          │  │
│  │  /ws/desk    │  │  └ QwenCleo  │  │  /personalities       │  │
│  │  /ws/esp     │  │  LLM (Ollama)│  │  /memories            │  │
│  └──────┬───────┘  │  TTS         │  │  /conversations       │  │
│         │          │  └ XTTS v2   │  │  /signals             │  │
│         │          │  └ VoiceTut  │  │  /calibration         │  │
│  ┌──────▼──────────▼──────────┐   │  │  /voice-clone         │  │
│  │      Service Layer         │   │  │  /settings            │  │
│  │  ┌────────────────────┐    │   │  │  /diagnostics         │  │
│  │  │ UniFace Vision     │    │   │  └──────────────────────┘  │
│  │  │ Signal Planner     │    │   │                             │
│  │  │ Motion Guard       │    │   │  ┌──────────────────────┐  │
│  │  │ RAG Memory         │    │   │  │   Voice Clone Svc    │  │
│  │  │ VoiceClone Service │    │   │  │  (XTTS v2 + samples) │  │
│  │  └────────────────────┘    │   │  └──────────────────────┘  │
│  └─────────────────────────── ┘   │                             │
│                                   │  ┌──────────────────────┐  │
│  ┌────────────────────────────┐    │  │    SQLite / Postgres  │  │
│  │     Auth Layer             │    │  │  devices, memories,  │  │
│  │  JWT + Pairing Code        │    │  │  conversations,      │  │
│  └────────────────────────────┘    │  │  signals, calibration│  │
└─────────────────────────────────── ┘  └──────────────────────┘  │
                                                                   │
   📱 Flutter Phone          🖥️ Flutter Desktop       🔌 ESP32      │
   (ws/phone)                (ws/desk)               (ws/esp)     │
```

---

## Folder Structure

```
nebulla-backend/
├── app/
│   ├── main.py                     # FastAPI app entry point
│   ├── auth/                       # 🔐 Authentication
│   │   ├── jwt.py                  # JWT helpers + FastAPI dependencies
│   │   ├── models.py               # APIKey ORM model
│   │   └── router.py               # POST /auth/token, GET /auth/me
│   ├── core/
│   │   ├── config.py               # All settings (loaded from .env)
│   │   ├── logger.py               # Rotating file + console logger
│   │   └── security.py             # Pairing code + rate limiter
│   ├── db/
│   │   └── session.py              # Async SQLAlchemy engine + get_db()
│   ├── models/                     # SQLAlchemy ORM models
│   │   ├── device.py               # Phone / Desktop / ESP32 devices
│   │   ├── personality.py          # Robot personality profiles
│   │   ├── memory.py               # Long-term memories (RAG store)
│   │   ├── conversation.py         # Conversation sessions + messages
│   │   ├── signal.py               # Named gesture sequences
│   │   ├── calibration.py          # Per-servo min/max/home angles
│   │   ├── tracking.py             # Telemetry time-series
│   │   └── log.py                  # System event log
│   ├── websocket/                  # 🔌 WebSocket Hub
│   │   ├── hub.py                  # Routes: /ws/phone /ws/desk /ws/esp
│   │   ├── manager.py              # ConnectionManager singleton
│   │   ├── handlers.py             # Message processing per channel
│   │   └── messages.py             # Pydantic message schemas (JSON protocol)
│   ├── services/
│   │   ├── ai/
│   │   │   └── pipeline.py         # STT → LLM → TTS pipeline (streaming)
│   │   ├── vision/
│   │   │   └── face_service.py     # UniFace face detection + gaze
│   │   ├── motion/
│   │   │   ├── motion_guard.py     # Safety validator for ESP32 commands
│   │   │   └── signal_planner.py   # Gesture tag → joint commands
│   │   ├── memory/
│   │   │   └── rag_service.py      # Embedding search + memory add
│   │   └── voice_clone/
│   │       └── voice_clone_service.py  # Sample management + XTTS synthesis
│   ├── providers/                  # 🔄 Swappable AI backends
│   │   ├── stt/
│   │   │   ├── base.py             # BaseSTTProvider ABC
│   │   │   ├── factory.py          # get_stt_provider(name)
│   │   │   ├── qwencleo.py         # Egyptian Arabic ASR (primary)
│   │   │   ├── whisper.py          # Whisper large-v3 (fallback)
│   │   │   └── nemotron.py         # Nemotron stub
│   │   ├── tts/
│   │   │   ├── base.py             # BaseTTSProvider ABC
│   │   │   ├── factory.py          # get_tts_provider(name)
│   │   │   ├── voicetut.py         # VoiceTut (OmniVoice fine-tune)
│   │   │   ├── ar_eg_free.py       # gTTS fallback (no GPU)
│   │   │   └── xtts/
│   │   │       └── provider.py     # XTTS v2 zero-shot voice clone ⭐
│   │   └── llm/
│   │       ├── factory.py          # get_llm_provider(name)
│   │       ├── local_ollama.py     # Local Ollama (Llama 3, Qwen)
│   │       ├── openai_provider.py  # OpenAI API
│   │       └── anthropic_provider.py
│   ├── api/v1/
│   │   ├── router.py               # Aggregates all sub-routers
│   │   └── endpoints/
│   │       ├── devices.py          # GET/DELETE devices + live status
│   │       ├── personalities.py    # CRUD + activate
│   │       ├── memories.py         # CRUD + semantic search
│   │       ├── conversations.py    # Read-only conversation history
│   │       ├── signals.py          # CRUD + /fire endpoint
│   │       ├── calibration.py      # Servo min/max/home + reset-to-home
│   │       ├── voice_clone.py      # Upload WAV + synthesize + test ⭐
│   │       ├── settings.py         # Hot-swap providers at runtime
│   │       └── diagnostics.py      # Hardware test panel
│   └── utils/
├── tests/
│   ├── unit/
│   │   ├── test_motion_guard.py
│   │   └── test_signal_planner.py
│   └── integration/
│       └── test_api.py
├── data/
│   ├── voice_samples/              # Uploaded WAV reference files
│   └── embeddings/                 # (optional) pre-built embedding cache
├── logs/                           # Rotating log files
├── scripts/                        # Utility scripts
├── docs/                           # Architecture docs
├── .env.example                    # ← Copy to .env and fill in
├── requirements.txt
├── Dockerfile
├── Makefile
└── pytest.ini
```

---

## Quick Start

```bash
# 1. Clone and enter
cd nebulla-backend

# 2. Create virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env — at minimum set PAIRING_SECRET

# 5. Run
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000/docs** to see the interactive API documentation.

---

## WebSocket Channels

| Channel     | Client              | Direction          | Data                                |
|-------------|---------------------|--------------------|-------------------------------------|
| `/ws/phone` | Flutter phone app   | Binary ↔ JSON      | Audio PCM, JPEG frames → eye/gaze cmds, TTS audio |
| `/ws/desk`  | Flutter desktop app | JSON ↔ JSON        | Gesture/servo cmds → live status, telemetry |
| `/ws/esp`   | ESP32 firmware      | JSON ↔ JSON        | Telemetry → joint/motor/stop cmds  |

All channels require `?pairing_code=<PAIRING_SECRET>` query parameter.

---

## Key JSON Messages

```json
// Phone → Backend (binary audio on ws/phone)
// Phone → Backend (binary JPEG camera frame)

// Backend → Phone
{"t": "eyes", "mood": "happy"}
{"t": "gaze", "x": 0.2, "y": -0.1}
// + binary WAV audio chunks

// Desktop → Backend
{"t": "cmd", "gesture": "like"}
{"t": "cmd", "joint_id": 3, "angle": 90, "speed_ms": 300}

// Backend → ESP32
{"t": "joint", "id": 3, "deg": 90, "ms": 300}
{"t": "motor", "left": 128, "right": 128}
{"t": "stop"}

// ESP32 → Backend
{"t": "tele", "bat": 7.6, "dist": 85}
```

---

## Voice Clone (XTTS v2)

```bash
# 1. Upload a reference voice sample (WAV, ≥ 3 seconds)
curl -X POST http://localhost:8000/api/v1/voice-clone/upload/1 \
  -H "X-API-Key: nebula-2026-secret" \
  -F "file=@my_voice.wav"

# 2. Synthesise in that voice
curl -X POST http://localhost:8000/api/v1/voice-clone/synthesize \
  -H "X-API-Key: nebula-2026-secret" \
  -H "Content-Type: application/json" \
  -d '{"text": "أهلاً يا صديقي!", "personality_id": 1}' \
  --output output.wav

# 3. Quick test
curl -X POST "http://localhost:8000/api/v1/voice-clone/test?personality_id=1" \
  -H "X-API-Key: nebula-2026-secret" \
  --output test.wav
```

---

## Swapping AI Providers

Change in `.env` — no code changes needed:

```env
STT_PROVIDER=qwencleo   # or: whisper, nemotron
TTS_PROVIDER=xtts       # or: voicetut, ar_eg_free
LLM_PROVIDER=local      # or: openai, anthropic
```

Or hot-swap at runtime via REST:

```bash
curl -X PATCH http://localhost:8000/api/v1/settings/providers \
  -H "X-API-Key: nebula-2026-secret" \
  -d '{"tts_provider": "voicetut"}'
```

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Safety Features

- **Motion Guard** — clamps servo angles to calibrated min/max, rejects too-fast commands
- **Pairing Code** — all WS channels + REST API require the secret
- **Rate Limiter** — max 20 commands/sec per device
- **Emergency Stop** — `POST /api/v1/diagnostics/emergency-stop` stops everything
- **Local Network Only** — no open internet ports required (works offline with local GPU)
- **ESP32 Watchdog** — robot stops safely if WiFi disconnects (handled in firmware)

---

## Team Responsibilities (doc §8)

| Module | Owner |
|--------|-------|
| WebSocket Hub + REST API | M6 (Backend Lead) |
| AI Pipeline (STT/LLM/TTS) | M5 (AI Lead) |
| XTTS Voice Clone | M5 + M7 |
| UniFace Vision | M5 |
| Flutter apps | M7 |
| ESP32 Firmware | M4 |
| Mechanical / 3D Print | M2 + M3 |
| Integration + QA | M1 (Project Lead) |