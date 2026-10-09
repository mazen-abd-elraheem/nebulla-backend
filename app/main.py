"""
Nebula Backend — Digital Twin Robot
FastAPI application entry point.

Architecture: Phone/Desk/ESP32 all connect to THIS backend.
No device talks to another device directly (design decision from doc §4).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import get_logger
from app.api.v1.router import api_router
from app.websocket.hub import router as ws_router
from app.db.session import init_db

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    logger.info("🚀 Nebula backend starting up…")
    await init_db()
    yield
    logger.info("👋 Nebula backend shutting down…")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description=(
        "Backend for the Nebula Digital-Twin Robot. "
        "Connects the Flutter phone app (face), the Flutter desktop app (control room), "
        "and the ESP32 firmware via WebSocket channels. "
        "Runs the AI pipeline: STT → LLM → TTS with streaming, "
        "UniFace vision, RAG memory, motion guard, and signal planner."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — local-network only (doc §6, security: local Wi-Fi, no open internet)
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(api_router, prefix="/api/v1")   # REST endpoints
app.include_router(ws_router)                       # WebSocket hub (ws/phone, ws/desk, ws/esp)


@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": settings.VERSION}
