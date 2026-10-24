"""
Nebula Backend — Digital Twin Robot
FastAPI application entry point.

Architecture: Phone/Desk/ESP32 all connect to THIS backend.
No device talks to another device directly (design decision from doc §4).
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logger import get_logger
from app.api.v1.router import api_router
from app.websocket.hub import router as ws_router
from app.db.session import init_db

logger = get_logger(__name__)


async def _warmup_ollama():
    """Pre-warm the active Ollama model in RAM with 24h keep-alive to avoid cold-start delays."""
    try:
        import httpx
        target_model = settings.LLM_MODEL or "nebula-rag"
        logger.info(f"🔥 Pre-warming local model '{target_model}' in RAM (keep-alive: 24h)...")
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                f"{settings.LLM_BASE_URL}/api/chat",
                json={
                    "model": target_model,
                    "messages": [{"role": "user", "content": "test"}],
                    "keep_alive": "24h",
                    "options": {"num_predict": 1},
                },
            )
        logger.info(f"✅ Local model '{target_model}' is warm and ready in RAM.")
    except Exception as e:
        logger.debug(f"Ollama warm-up notice: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    import asyncio
    logger.info("🚀 Nebula backend starting up…")
    await init_db()
    asyncio.create_task(_warmup_ollama())
    yield
    logger.info("Nebula backend shutting down...")


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
    allow_origins=["*"],
    allow_origin_regex=".*",
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(api_router, prefix="/api/v1")   # REST endpoints
app.include_router(ws_router)                       # WebSocket hub (ws/phone, ws/desk, ws/esp)


from fastapi.responses import HTMLResponse, RedirectResponse

@app.get("/health", tags=["health"])
async def health_check():
    return {"status": "ok", "version": settings.VERSION}


STUDIO_HTML_PATH = Path(__file__).parent / "static" / "faces_studio.html"


@app.get("/faces-ui", response_class=HTMLResponse, tags=["vision-studio"], summary="Interactive Vision Testing Studio")
async def vision_studio():
    """Interactive visual testing interface for video face recognition and match percentage."""
    if STUDIO_HTML_PATH.exists():
        return HTMLResponse(content=STUDIO_HTML_PATH.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h3>Studio UI template not found</h3>", status_code=404)


@app.get("/chat", response_class=HTMLResponse, tags=["chat"])
async def chat_playground():
    """Interactive visual web playground to chat with the LLM in real-time."""
    html_path = Path(__file__).parent / "templates" / "chat_ui.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h3>Chat UI template not found</h3>", status_code=404)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/chat")
