"""
Nebula Backend — Digital Twin Robot
FastAPI application entry point.

Architecture: Phone/Desk/ESP32 all connect to THIS backend.
No device talks to another device directly (design decision from doc §4).
"""

import json
import re
from contextlib import asynccontextmanager
from pathlib import Path
from starlette.types import ASGIApp, Receive, Scope, Send

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.core.config import settings
from app.core.logger import get_logger
from app.api.v1.router import api_router
from app.websocket.hub import router as ws_router
from app.db.session import init_db

logger = get_logger(__name__)


async def _warmup_vision():
    """Pre-load UniFace face detection and recognition model in RAM on startup."""
    try:
        from app.websocket.handlers import _get_face_service
        svc = _get_face_service()
        await svc._ensure_model()
        logger.info("[OK] UniFace FaceAnalyzer is warm and ready in RAM.")
    except Exception as e:
        logger.debug(f"Vision warm-up notice: {e}")


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


async def _warmup_stt():
    """Pre-warm configured STT model in VRAM to eliminate cold-start transcription latency."""
    try:
        from app.providers.stt.factory import get_stt_provider
        provider = get_stt_provider(settings.STT_PROVIDER)
        if hasattr(provider, '_ensure_loaded'):
            await provider._ensure_loaded()
        elif hasattr(provider, '_ensure_model_loaded'):
            await provider._ensure_model_loaded()
        logger.info(f"✅ STT model '{settings.STT_PROVIDER}' is warm and ready in VRAM.")
    except Exception as e:
        logger.debug(f"STT warm-up notice: {e}")


async def _warmup_rag():
    """Pre-warm RAG SentenceTransformer in RAM to eliminate cold-start retrieval latency."""
    try:
        from app.services.memory.rag_service import RAGService
        rag = RAGService()
        await rag._ensure_embedder()
        logger.info("✅ RAG SentenceTransformer model is warm and ready in RAM.")
    except Exception as e:
        logger.debug(f"RAG warm-up notice: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    import asyncio
    logger.info("🚀 Nebula backend starting up…")
    await init_db()
    asyncio.create_task(_warmup_vision())
    asyncio.create_task(_warmup_ollama())
    asyncio.create_task(_warmup_rag())
    asyncio.create_task(_warmup_stt())

    # Chapter 14: reminders (medicine / tasks) with family escalation
    scheduler = None
    if settings.PHONE_ACTIONS_ENABLED:
        from app.services.phone_action import get_phone_action_service
        from app.services.phone_action.reminders import ReminderScheduler
        from app.websocket.handlers import get_ai_pipeline

        async def _speak(text: str, mood=None) -> None:
            await get_ai_pipeline().speak(text, mood)

        svc = get_phone_action_service()
        svc.set_speaker(_speak)
        scheduler = ReminderScheduler(svc)
        await scheduler.start()
    yield
    if scheduler is not None:
        await scheduler.stop()
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


def repair_malformed_json(raw_text: str) -> str:
    s = raw_text.strip()
    if not s:
        return s

    try:
        json.loads(s)
        return s
    except Exception:
        pass

    fixed = s
    # Fix trailing commas before } or ]
    fixed = re.sub(r',\s*([}\]])', r'\1', fixed)

    # Convert Python-style set of strings: { "a", "b", "c" } -> [ "a", "b", "c" ]
    if fixed.startswith('{') and fixed.endswith('}') and ':' not in fixed:
        fixed = '[' + fixed[1:-1] + ']'
        try:
            json.loads(fixed)
            return fixed
        except Exception:
            pass

    # Fix unbracketed list of strings inside { "content": "str1", "str2" }
    if fixed.startswith('{') and fixed.endswith('}'):
        inner = fixed[1:-1].strip()
        lines = [ln.strip() for ln in inner.splitlines() if ln.strip()]
        new_lines = []
        in_content_list = False
        content_items = []
        has_content_key = False

        for line in lines:
            line_clean = line.rstrip(',')
            key_match = re.match(r'^"([^"]+)"\s*:\s*(.*)$', line_clean)
            if key_match:
                key = key_match.group(1)
                val = key_match.group(2).strip()
                if key in ("content", "text", "memory", "memories"):
                    has_content_key = True
                    in_content_list = True
                    if val and val != '[':
                        content_items.append(val.rstrip(','))
                else:
                    if in_content_list:
                        in_content_list = False
                    new_lines.append(f'"{key}": {val}')
            elif in_content_list and line_clean.startswith('"') and line_clean.endswith('"'):
                content_items.append(line_clean)
            elif not has_content_key and line_clean.startswith('"') and line_clean.endswith('"'):
                content_items.append(line_clean)
            else:
                new_lines.append(line_clean)

        if content_items:
            formatted_items = '[\n    ' + ',\n    '.join(content_items) + '\n  ]'
            new_lines.append(f'"content": {formatted_items}')
            rebuilt = '{\n  ' + ',\n  '.join(new_lines) + '\n}'
            try:
                json.loads(rebuilt)
                return rebuilt
            except Exception:
                pass

    return raw_text


class JSONRepairMiddleware:
    """Auto-repairs common JSON syntax slips (like missing list brackets around content)."""
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope.get("method") in ("POST", "PUT", "PATCH"):
            body_bytes = b""
            more_body = True
            while more_body:
                message = await receive()
                body_bytes += message.get("body", b"")
                more_body = message.get("more_body", False)

            if body_bytes:
                try:
                    text = body_bytes.decode("utf-8")
                    repaired = repair_malformed_json(text)
                    if repaired != text:
                        logger.info(f"Auto-repaired malformed JSON in request to {scope.get('path')}")
                        body_bytes = repaired.encode("utf-8")
                except Exception:
                    pass

            body_sent = False
            async def custom_receive():
                nonlocal body_sent
                if not body_sent:
                    body_sent = True
                    return {"type": "http.request", "body": body_bytes, "more_body": False}
                return {"type": "http.request", "body": b"", "more_body": False}

            await self.app(scope, custom_receive, send)
            return

        await self.app(scope, receive, send)

app.add_middleware(JSONRepairMiddleware)

# ---------------------------------------------------------------------------
# Validation & Malformed JSON Exception Handler
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    for err in errors:
        if err.get("type") == "json_invalid":
            body_bytes = await request.body()
            body_str = body_bytes.decode("utf-8", errors="replace")
            loc = err.get("loc", [])
            pos = loc[1] if len(loc) > 1 and isinstance(loc[1], int) else None

            snippet = ""
            if pos is not None and 0 <= pos <= len(body_str):
                start = max(0, pos - 30)
                end = min(len(body_str), pos + 30)
                snippet = body_str[start:end]
                logger.error(
                    f"❌ Malformed JSON syntax in request to {request.url.path} near character {pos}:\n"
                    f"   Snippet: '{snippet}'\n"
                    f"   Detail: {err.get('ctx', {}).get('error', '')}"
                )

            return JSONResponse(
                status_code=422,
                content={
                    "detail": "خطأ في صياغة الـ JSON (JSON syntax error). تأكد من علامات التنصيص المزدوجة \"، ووضع نقطتين : بعد اسم كل حقل، والفواصل بين الحقول.",
                    "error_type": "json_invalid",
                    "position": pos,
                    "near": snippet,
                    "syntax_error": err.get("ctx", {}).get("error", "Malformed JSON"),
                    "raw_errors": errors,
                },
            )
    serialized_errors = []
    for err in errors:
        err_copy = dict(err)
        if "ctx" in err_copy and isinstance(err_copy["ctx"], dict):
            ctx_copy = dict(err_copy["ctx"])
            if "error" in ctx_copy and isinstance(ctx_copy["error"], Exception):
                ctx_copy["error"] = str(ctx_copy["error"])
            err_copy["ctx"] = ctx_copy
        serialized_errors.append(err_copy)

    return JSONResponse(status_code=422, content={"detail": serialized_errors})


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(api_router, prefix="/api/v1")   # REST endpoints
app.include_router(ws_router)                       # WebSocket hub (ws/phone, ws/desk, ws/esp)

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
