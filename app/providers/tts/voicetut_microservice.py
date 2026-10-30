"""
VoiceTut Microservice Provider (Method 2: Dedicated GPU Microservice Bridge)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bridges Nebulla Backend to the standalone VoiceTuT Studio server (running on port 8001)
via HTTP REST API. Features health checks and character routing.
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
        speaker: Optional[str] = None,
        ref_audio: Optional[str] = None,
        ref_text: Optional[str] = None,
        character_id: Optional[str] = None,
        num_step: Optional[int] = None,
        guidance_scale: Optional[float] = None,
        speed: Optional[float] = None,
        language: str = "arz",
    ) -> bytes:
        """
        Synthesize speech through the dedicated VoiceTuT Studio microservice.
        Strict single-engine policy: raises descriptive RuntimeError on connection or synthesis failure.
        """
        clean_text = clean_llm_output_for_speech(text) or text.strip()
        client = self._get_client()

        target_ref_audio = ref_audio
        if not target_ref_audio:
            spk = speaker or character_id
            if spk and not str(spk).isdigit() and str(spk).lower() != "mazen":
                spk_wav = Path(f"data/voice_samples/{spk}.wav")
                if spk_wav.exists():
                    target_ref_audio = str(spk_wav.resolve())

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

        if not actual_ref_text and hasattr(settings, "DEFAULT_VOICE_TRANSCRIPT"):
            def_txt = Path(settings.DEFAULT_VOICE_TRANSCRIPT)
            if def_txt.exists():
                try:
                    actual_ref_text = def_txt.read_text(encoding="utf-8").strip()
                except Exception:
                    pass

        steps = num_step or getattr(settings, "VOICETUT_NUM_STEPS", 48)
        cfg = guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.2)
        spd = speed or getattr(settings, "VOICETUT_SPEED", 1.0)
        target_char = character_id or speaker or "mazen"

        payload = {
            "text": clean_text,
            "ref_text": actual_ref_text or "",
            "character_id": target_char,
            "language": language,
            "num_step": steps,
            "guidance_scale": cfg,
            "speed": spd,
            "normalize": True,
        }

        try:
            resp = await client.post(f"{self._url}/api/clone", json=payload)
            if resp.status_code != 200:
                err_detail = resp.text
                logger.error(f"VoiceTuT Studio microservice returned HTTP {resp.status_code}: {err_detail}")
                raise RuntimeError(
                    f"VoiceTuT Studio microservice error (HTTP {resp.status_code}): {err_detail}"
                )

            data = resp.json()
            audio_rel_url = data.get("audio_url")
            if not audio_rel_url:
                raise RuntimeError(
                    f"VoiceTuT Studio microservice returned no audio_url. Response: {data}"
                )

            full_audio_url = f"{self._url}{audio_rel_url}" if audio_rel_url.startswith("/") else audio_rel_url
            audio_resp = await client.get(full_audio_url)
            if audio_resp.status_code != 200:
                raise RuntimeError(
                    f"Failed to fetch synthesized audio from {full_audio_url} (HTTP {audio_resp.status_code})"
                )

            audio_content = audio_resp.content
            if len(audio_content) <= 1000:
                raise RuntimeError(
                    f"VoiceTuT Studio microservice returned corrupt/empty audio ({len(audio_content)} bytes)"
                )

            logger.info(f"Microservice synthesized {len(audio_content)} bytes (RTF: {data.get('rtf')}x, steps: {steps})")
            return audio_content
        except RuntimeError:
            raise
        except Exception as exc:
            err_msg = f"VoiceTuT Studio microservice request failed: {exc}"
            logger.error(err_msg, exc_info=True)
            raise RuntimeError(err_msg) from exc

