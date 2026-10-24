"""
VoiceTut Microservice Provider (Method 2: Dedicated GPU Microservice Bridge)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bridges Nebulla Backend to the standalone VoiceTuT Studio server (running on port 8001)
via HTTP REST API. Features health checks, character routing, and automatic fallback.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Optional

import httpx

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.tts.base import BaseTTSProvider
from app.utils.masri_normalizer import clean_llm_output_for_speech

logger = get_logger(__name__)


class VoiceTutMicroserviceProvider(BaseTTSProvider):
    """
    Connects to the dedicated VoiceTuT Studio microservice (http://127.0.0.1:8001).
    Delegates heavy GPU neural synthesis to the isolated process.
    """

    def __init__(self, service_url: Optional[str] = None):
        self._url = (service_url or getattr(settings, "VOICETUT_SERVICE_URL", "http://127.0.0.1:8001")).rstrip("/")
        self._client: Optional[httpx.AsyncClient] = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=45.0)
        return self._client

    async def is_healthy(self) -> bool:
        """Check if the VoiceTuT Studio microservice is reachable."""
        try:
            client = self._get_client()
            resp = await client.get(f"{self._url}/api/characters")
            return resp.status_code == 200
        except Exception:
            return False

    async def synthesize(
        self,
        text: str,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        character_id: Optional[str] = "mazen",
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        speed: Optional[float] = None,
        language: str = "arz",
    ) -> bytes:
        """
        Synthesize speech through the VoiceTuT Studio microservice.
        Falls back to local VoiceTut or ArEgFree if microservice is offline.
        """
        clean_text = clean_llm_output_for_speech(text) or text.strip()
        client = self._get_client()

        target_ref_audio = ref_audio
        if not target_ref_audio:
            def_path = Path(settings.DEFAULT_VOICE_SAMPLE)
            if def_path.exists():
                target_ref_audio = str(def_path.resolve())

        actual_ref_text = ref_text
        if not actual_ref_text and target_ref_audio:
            txt_path = Path(target_ref_audio).with_suffix(".txt")
            if txt_path.exists():
                try:
                    actual_ref_text = txt_path.read_text(encoding="utf-8").strip()
                except Exception:
                    pass

        payload = {
            "text": clean_text,
            "ref_text": actual_ref_text or "",
            "character_id": character_id or "mazen",
            "language": language,
            "num_step": num_step or getattr(settings, "VOICETUT_NUM_STEPS", 36),
            "guidance_scale": guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.2),
            "speed": speed or getattr(settings, "VOICETUT_SPEED", 1.0),
            "normalize": True,
        }

        try:
            resp = await client.post(f"{self._url}/api/clone", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                audio_rel_url = data.get("audio_url")
                if audio_rel_url:
                    full_audio_url = f"{self._url}{audio_rel_url}" if audio_rel_url.startswith("/") else audio_rel_url
                    audio_resp = await client.get(full_audio_url)
                    if audio_resp.status_code == 200 and len(audio_resp.content) > 1000:
                        logger.info(f"Microservice synthesized {len(audio_resp.content)} bytes (RTF: {data.get('rtf')}x)")
                        return audio_resp.content
        except Exception as exc:
            logger.warning(f"VoiceTuT Studio microservice request failed: {exc} — attempting local synthesis")

        # Fallback to local native engine
        from app.providers.tts.voicetut import VoiceTutProvider
        return await VoiceTutProvider().synthesize(
            clean_text,
            ref_audio=target_ref_audio,
            ref_text=actual_ref_text,
            num_step=num_step,
            guidance_scale=guidance_scale,
            speed=speed,
            language=language,
        )
