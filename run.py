"""
Nebula Backend — Production & Development Server Launcher
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Launches the FastAPI backend with domain-isolated Multithreading,
high-concurrency WebSocket hubs, and pre-warmed AI models.

Usage:
    python run.py
    python run.py --port 8000 --host 0.0.0.0 --reload
"""

from __future__ import annotations

import argparse
import os
import sys

# Ensure project root is in sys.path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import uvicorn
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger("nebula.launcher")


def main() -> None:
    parser = argparse.ArgumentParser(description="Nebula Robot Backend Launcher")
    parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Bind port (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload on code change")
    parser.add_argument("--workers", type=int, default=1, help="Number of server processes (default: 1)")
    args = parser.parse_args()

    cpu_cores = os.cpu_count() or 4
    logger.info("=" * 70)
    logger.info(f" 🤖 Starting Nebula Backend — Digital Twin Robot (v{settings.VERSION})")
    logger.info("=" * 70)
    logger.info(f"[*] Detected CPU Cores  : {cpu_cores}")
    logger.info(f"[*] Vision Thread Pool  : {getattr(settings, 'VISION_MAX_THREADS', 4)} workers")
    logger.info(f"[*] Audio Thread Pool   : {getattr(settings, 'AUDIO_MAX_THREADS', 4)} workers")
    logger.info(f"[*] RAG Thread Pool     : {getattr(settings, 'RAG_MAX_THREADS', 2)} workers")
    logger.info(f"[*] I/O Thread Pool     : {getattr(settings, 'IO_MAX_THREADS', 4)} workers")
    logger.info(f"[*] Serving URL         : http://{args.host}:{args.port}")
    logger.info(f"[*] Swagger Docs        : http://{args.host}:{args.port}/docs")
    logger.info(f"[*] Threads Monitor     : http://{args.host}:{args.port}/threads")
    logger.info("=" * 70)

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=args.workers,
        log_level="info",
        access_log=False,
        timeout_keep_alive=65,
    )


if __name__ == "__main__":
    main()

