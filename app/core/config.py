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
    )

    # ── Project ────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "Nebula Backend"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ── Security ───────────────────────────────────────────────────────────
    # Local-network only (doc §6 security)
    CORS_ORIGINS: List[str] = ["*"]  # tighten in production
    PAIRING_SECRET: str = "change-me-in-production"  # pairing code auth
    MAX_COMMANDS_PER_SECOND: int = 20  # rate-limit for ESP32 commands

    # ── Database ───────────────────────────────────────────────────────────
    DATABASE_URL: str = "sqlite+aiosqlite:///./nebula.db"

    # ── WebSocket ──────────────────────────────────────────────────────────
    WS_HEARTBEAT_INTERVAL: int = 30  # seconds

    # ── AI Providers (swappable without code changes, doc §6) ──────────────
    # STT: "qwencleo" | "whisper" | "nemotron"
    STT_PROVIDER: Literal["qwencleo", "whisper", "nemotron"] = "qwencleo"

    # TTS: "voicetut" | "ar_eg_free"
    TTS_PROVIDER: Literal["voicetut", "ar_eg_free"] = "voicetut"

    # LLM: "local" | "openai" | "anthropic"
    LLM_PROVIDER: Literal["local", "openai", "anthropic"] = "local"
    LLM_API_KEY: str = ""
    LLM_BASE_URL: str = "http://localhost:11434"   # local Ollama default
    LLM_MODEL: str = "llama3"
    LLM_STREAM: bool = True

    # ── STT Config ─────────────────────────────────────────────────────────
    QWENCLEO_MODEL_PATH: str = "models/qwencleo-asr"
    QWENCLEO_DEVICE: str = "cuda"  # "cuda" | "cpu"

    # ── TTS Config ─────────────────────────────────────────────────────────
    VOICETUT_MODEL_PATH: str = "models/voicetut-tts"
    VOICETUT_DEVICE: str = "cuda"
    # OmniVoice base (VoiceTut is fine-tuned on ~380h Egyptian podcast)
    OMNIVOICE_BASE_PATH: str = "models/omnivoice"
    # Max generation steps — keep first sentence short for low latency (doc §6.3)
    TTS_MAX_NEW_TOKENS: int = 200

    # ── Vision Config ──────────────────────────────────────────────────────
    UNIFACE_MODEL: Literal["scrfd", "retinaface", "yolo_face"] = "scrfd"
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
