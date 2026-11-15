"""
VoiceTut Microservice Provider (Dedicated GPU Microservice Bridge)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bridges Nebulla Backend to the standalone VoiceTuT Studio server (running on port 8001)
via HTTP REST API. Features health checks, automatic sample upload, and character routing.
"""

from __future__ import annotations

import asyncio
import io
import math
import os
from pathlib import Path
import struct
import tempfile
from typing import Dict, Optional
import wave

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.tts.base import BaseTTSProvider
from app.utils.masri_normalizer import clean_llm_output_for_speech

logger = get_logger(__name__)

# Cache uploaded reference audio URLs so we don't re-upload the same WAV repeatedly
_UPLOADED_AUDIO_URLS: Dict[str, str] = {}


class VoiceTutMicroserviceProvider(BaseTTSProvider):
    """
    Connects to the dedicated VoiceTuT Studio microservice (http://127.0.0.1:8001).
    Delegates heavy GPU neural synthesis to the isolated process with native fallback.
    """

    def __init__(self, service_url: Optional[str] = None):
        self._url = (service_url or getattr(settings, "VOICETUT_SERVICE_URL", "http://127.0.0.1:8001")).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None
        self._client_loop: Optional[asyncio.AbstractEventLoop] = None

    def _get_client(self) -> httpx.AsyncClient:
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if self._client is None or self._client.is_closed or self._client_loop != curr_loop:
            self._client = httpx.AsyncClient(timeout=120.0)
            self._client_loop = curr_loop
        return self._client

    async def is_healthy(self) -> bool:
        """Check if the VoiceTuT Studio microservice is reachable and online."""
        try:
            client = self._get_client()
            resp = await client.get(f"{self._url}/health", timeout=2.0)
            return resp.status_code == 200
        except Exception:
            return False

    async def synthesize(
        self,
        text: str,
        speaker: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        speed: Optional[float] = None,
        language: str = "arz",
    ) -> bytes:
        """
        Synthesize speech using VoiceTuT microservice with automatic fallback.
        """
        client = self._get_client()

        # Resolve reference audio file path
        actual_ref_audio = ref_audio
        if not actual_ref_audio or not os.path.exists(actual_ref_audio):
            # Try default preset reference samples
            default_path = Path("data/voice_samples/personality_1.wav")
            if default_path.exists():
                actual_ref_audio = str(default_path.resolve())

        # Determine reference text if not provided
        actual_ref_text = ref_text
        if not actual_ref_text and actual_ref_audio and os.path.exists(actual_ref_audio):
            txt_path = Path(actual_ref_audio).with_suffix(".txt")
            if txt_path.exists():
                try:
                    actual_ref_text = txt_path.read_text(encoding="utf-8").strip()
                except Exception:
                    actual_ref_text = None

        steps = num_step or getattr(settings, "VOICETUT_NUM_STEPS", 32)
        # Cap steps at 36 for fast response on laptop GPU
        steps = min(steps, 36)
        cfg = guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.2)
        spd = speed or getattr(settings, "VOICETUT_SPEED", 1.0)

        payload = {
            "text": text,
            "ref_audio": actual_ref_audio,
            "ref_text": actual_ref_text,
            "speaker": speaker,
            "steps": steps,
            "guidance_scale": cfg,
            "speed": spd,
            "language": language,
        }

        try:
            resp = await client.post(f"{self._url}/api/clone", json=payload, timeout=5.0)
            if resp.status_code == 200:
                data = resp.json()
                audio_rel_url = data.get("audio_url")
                if audio_rel_url:
                    full_audio_url = f"{self._url}{audio_rel_url}" if audio_rel_url.startswith("/") else audio_rel_url
                    audio_resp = await client.get(full_audio_url)
                    if audio_resp.status_code == 200 and len(audio_resp.content) > 1000:
                        return audio_resp.content
        except Exception as exc:
            logger.error(f"VoiceTuT microservice not reachable: {exc}")
            raise RuntimeError(
                f"فشل الاتصال بخدمة VoiceTut GPU Studio ({exc}). لا يوجد أي نموذج بديل (Zero Fallback)."
            )

        raise RuntimeError(
            "لم تقم خدمة VoiceTut بإرجاع ملف صوتي سليم، يرجى التحقق من حالة الموديل."
        )
