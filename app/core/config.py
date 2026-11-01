"""
Application settings — loaded from environment variables / .env file.
Swappable STT/TTS/LLM providers are configured here (doc §6, swappable providers).
"""

from functools import lru_cache
from typing import List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Project ────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "Nebula Backend"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Security ───────────────────────────────────────────────────────────
    # Local-network only (doc §6 security)
    CORS_ORIGINS: List[str] = ["*"]  # tighten in production
    PAIRING_SECRET: str = "change-me-in-production"  # pairing code auth
    API_KEY: str = "change-me-in-production"  # pre-shared API key
    JWT_SECRET_KEY: str = "change-me-jwt-secret-in-production"  # dedicated JWT signing secret
    MAX_COMMANDS_PER_SECOND: int = 20  # rate-limit for ESP32 commands

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./nebula.db"

    # ── WebSocket ──────────────────────────────────────────────────────────
    WS_HEARTBEAT_INTERVAL: int = 30  # seconds

    # ── AI Providers (swappable without code changes, doc §6) ──────────────
    # STT: "qwencleo" | "whisper" | "nemotron"
    STT_PROVIDER: Literal["qwencleo", "whisper", "nemotron", "groq", "openai"] = "qwencleo"

    # TTS: strictly VoiceTut-TTS ("voicetut_service" or "voicetut")
    TTS_PROVIDER: Literal["voicetut_service", "voicetut"] = "voicetut_service"

    # LLM: "local" | "openai" | "anthropic" | "huggingface" | "nile"
    LLM_PROVIDER: Literal["local", "openai", "anthropic", "huggingface", "nile"] = "local"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "http://localhost:11434"   # local Ollama default
    LLM_MODEL: str = "nebula-masri"
    HF_MODEL_NAME: str = "MBZUAI-Paris/Nile-Chat-3x4B-A6B"
    LLM_STREAM: bool = True
    LLM_TIMEOUT: float = 120.0
    LLM_MAX_TOKENS: int = 45
    LLM_TEMPERATURE: float = 0.0
    LLM_TOP_P: float = 0.85
    LLM_REPEAT_PENALTY: float = 1.15

    # ── STT Config (QwenCleo-ASR) ──────────────────────────────────────────
    QWENCLEO_MODEL_PATH: str = "models/qwencleo-asr"
    QWENCLEO_DEVICE: str = "cuda"  # "cuda" | "cpu"
    QWENCLEO_LANGUAGE: str = "Arabic"
    WHISPER_MODEL: str = "turbo"   # "tiny" | "base" | "small" | "medium" | "turbo" | "large-v3"
    WHISPER_DEVICE: str = "cuda"   # "cuda" | "cpu"
    WHISPER_LANGUAGE: str = "ar"
    GROQ_API_KEY: str = ""

    # ── TTS Config (VoiceTut-TTS Studio) ───────────────────────────────────
    VOICETUT_MODEL_PATH: str = "models/voicetut-tts"
    VOICETUT_DEVICE: str = "cuda"  # "cuda" | "cpu" (RTX 4050 GPU)
    VOICETUT_SERVICE_URL: str = "http://127.0.0.1:8001"  # Standalone studio microservice endpoint
    VOICETUT_SPEAKER: str = "mazen"
    # Diffusion denoising steps (48 for max studio fidelity & crisp consonant transitions)
    VOICETUT_NUM_STEPS: int = 48
    VOICETUT_GUIDANCE_SCALE: float = 2.2
    VOICETUT_SPEED: float = 1.0
    VOICETUT_LANGUAGE: str = "arz"
    DEFAULT_VOICE_SAMPLE: str = "data/voice_samples/personality_1.wav"
    DEFAULT_VOICE_TRANSCRIPT: str = "data/voice_samples/personality_1.txt"
    TTS_MAX_NEW_TOKENS: int = 200

    # ── Vision Config ──────────────────────────────────────────────────────
    UNIFACE_MODEL: Literal["scrfd", "retinaface", "yolo_face"] = "scrfd"
    UNIFACE_MODEL_NAME: str = "scrfd_2.5g_kps"
    UNIFACE_RECOGNIZER: str = "mobileface"
    UNIFACE_CONF_THRESH: float = 0.6
    UNIFACE_DEVICE: str = "cpu"   # "cpu" | "cuda" (keep off GPU if STT/TTS busy)
    CAMERA_FPS: int = 10          # frames per second sent from phone camera
    CAMERA_WIDTH: int = 320
    CAMERA_HEIGHT: int = 240

    # ── Memory / RAG ───────────────────────────────────────────────────────
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    EMBEDDING_DEVICE: str = "cpu"
    MEMORY_TOP_K: int = 5           # how many memories to retrieve per query

    # ── Motion Guard ───────────────────────────────────────────────────────
    # Safety limits matching ESP32 firmware constants (doc §7.8)
    SERVO_MIN_ANGLE: int = 0
    SERVO_MAX_ANGLE: int = 180
    SERVO_MAX_SPEED_MS: int = 2000   # milliseconds for full travel
    MOTOR_MAX_SPEED: int = 255       # PWM 0-255

    # ── Phone Actions & Voice Verification (benefits_section.docx, ch.14) ──
    PHONE_ACTIONS_ENABLED: bool = True
    # Speaker verification (voiceprint). Fails CLOSED: if the model is
    # unavailable or nobody is enrolled, only Level-0 (guest) actions run.
    SPEAKER_VERIFICATION_ENABLED: bool = True
    SPEAKER_MODEL_SOURCE: str = "speechbrain/spkrec-ecapa-voxceleb"
    SPEAKER_MODEL_DIR: str = "models/speaker-ecapa"
    SPEAKER_DEVICE: str = "cpu"
    # Cosine-similarity thresholds. These defaults are starting points only —
    # calibrate on real phone-mic recordings (doc §14.3: FAR≈0 at Level 2).
    SPEAKER_THRESHOLD_L1: float = 0.45
    SPEAKER_THRESHOLD_L2: float = 0.55
    # Very short utterances (e.g. "أيوه") cannot be scored reliably; the
    # confirmation step only vetoes when a *scored* match is clearly wrong.
    SPEAKER_CONFIRM_MIN_SIMILARITY: float = 0.25
    SPEAKER_MIN_AUDIO_SECONDS: float = 1.0
    SPEAKER_ENROLL_MIN_SAMPLES: int = 5
    SPEAKER_ENROLL_MAX_SAMPLES: int = 20
    SPEAKER_SAMPLE_RATE: int = 16000
    # Anti-replay / anti-clone random challenge (Level 2)
    CHALLENGE_TTL_SECONDS: int = 60
    CHALLENGE_MAX_ATTEMPTS: int = 2
    CHALLENGE_TEXT_MATCH_RATIO: float = 0.82
    # Verbal-confirmation window («أكلّم ماما؟» → «أيوه»)
    CONFIRMATION_TTL_SECONDS: int = 30
    # Brute-force protection: N failed identity checks → lockout
    ACTION_MAX_FAILED_CHECKS: int = 3
    ACTION_LOCKOUT_SECONDS: int = 300
    # Level-3 external (control-room) confirmation window
    EXTERNAL_CONFIRM_TTL_SECONDS: int = 120
    DEFAULT_CALL_SPEAKERPHONE: bool = True
    # Dispatched-but-unacknowledged phone commands expire after this long
    ACTION_RESULT_TTL_SECONDS: int = 60
    # Active-call privacy mute: failsafe so a lost "call_ended" never mutes forever
    CALL_MAX_SUSPEND_SECONDS: int = 3600
    # Medicine / task reminders
    REMINDER_CHECK_INTERVAL_SECONDS: int = 30
    REMINDER_ESCALATION_MINUTES: int = 5
    ACTION_LOG_RETENTION_DAYS: int = 90

    # ── Logging ────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/nebula.log"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
