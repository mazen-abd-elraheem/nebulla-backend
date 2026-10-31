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
    JWT_SECRET_KEY: str = "change-me-jwt-secret-in-production"  # dedicated JWT signing secret
    MAX_COMMANDS_PER_SECOND: int = 20  # rate-limit for ESP32 commands

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./nebula.db"

    # ── WebSocket ──────────────────────────────────────────────────────────
    WS_HEARTBEAT_INTERVAL: int = 30  # seconds

    # ── AI Providers (swappable without code changes, doc §6) ──────────────
    # STT: "qwencleo" | "whisper" | "nemotron"
    STT_PROVIDER: Literal["qwencleo", "whisper", "nemotron", "groq", "openai"] = "qwencleo"

    # TTS: "voicetut" | "voicetut_service" | "ar_eg_free" | "xtts"
    TTS_PROVIDER: Literal["voicetut", "voicetut_service", "ar_eg_free", "xtts"] = "voicetut"

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

    # ── STT Config ─────────────────────────────────────────────────────────
    QWENCLEO_MODEL_PATH: str = "models/qwencleo-asr"
    QWENCLEO_DEVICE: str = "cuda"  # "cuda" | "cpu"
    QWENCLEO_LANGUAGE: str = "Arabic"
    WHISPER_MODEL: str = "base"    # "tiny" | "base" | "small" | "medium" | "turbo" | "large-v3"
    WHISPER_DEVICE: str = "cuda"   # "cuda" | "cpu"
    WHISPER_LANGUAGE: str = "ar"
    GROQ_API_KEY: str = ""

    # ── TTS Config ─────────────────────────────────────────────────────────
    VOICETUT_MODEL_PATH: str = "models/voicetut-tts"
    VOICETUT_DEVICE: str = "cuda"  # "cuda" | "cpu" (RTX 4050 GPU)
    VOICETUT_SERVICE_URL: str = "http://127.0.0.1:8001"  # Standalone studio microservice endpoint
    VOICETUT_SPEAKER: str = "mazen"
    VOICETUT_STEPS: int = 32
    # OmniVoice base (VoiceTut is fine-tuned on ~380h Egyptian podcast)
    OMNIVOICE_BASE_PATH: str = "models/omnivoice"
    # Diffusion denoising steps (4: fast preview, 10: balanced streaming, 36: max studio fidelity)
    VOICETUT_NUM_STEPS: int = 36
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

    # ── Logging ────────────────────────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "logs/nebula.log"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
