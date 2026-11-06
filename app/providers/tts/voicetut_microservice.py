"""
VoiceTut Microservice Provider (Dedicated GPU Microservice Bridge)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bridges Nebulla Backend to the standalone VoiceTuT Studio server (running on port 8001)
via HTTP REST API. Features health checks, automatic sample upload, and character routing.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Dict, Optional

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
        """Check if the VoiceTuT Studio microservice is reachable and online."""
        try:
            client = self._get_client()
            resp = await client.get(f"{self._url}/api/status", timeout=3.0)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("status") == "online"
            return False
        except Exception:
            return False

    async def _upload_reference_audio(self, audio_path: str) -> Optional[str]:
        """Uploads a local reference WAV to the microservice and returns the remote audio URL."""
        if audio_path in _UPLOADED_AUDIO_URLS:
            return _UPLOADED_AUDIO_URLS[audio_path]

        p = Path(audio_path)
        if not p.exists() or p.stat().st_size < 1000:
            return None

        client = self._get_client()
        try:
            with open(p, "rb") as f:
                files = {"file": (p.name, f, "audio/wav")}
                resp = await client.post(f"{self._url}/api/upload", files=files, timeout=20.0)
                if resp.status_code == 200:
                    data = resp.json()
                    remote_url = data.get("audio_url")
                    if remote_url:
                        _UPLOADED_AUDIO_URLS[audio_path] = remote_url
                        logger.info(f"Uploaded voice sample {p.name} to VoiceTut microservice -> {remote_url}")
                        return remote_url
        except Exception as e:
            logger.debug(f"Failed to upload reference audio {p.name} to VoiceTut microservice: {e}")
        return None

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

        steps = num_step or getattr(settings, "VOICETUT_NUM_STEPS", 32)
        # Cap steps at 36 for fast response on laptop GPU
        steps = min(steps, 36)
        cfg = guidance_scale or getattr(settings, "VOICETUT_GUIDANCE_SCALE", 2.2)
        spd = speed or getattr(settings, "VOICETUT_SPEED", 1.0)

        # Upload local reference audio if available
        remote_ref_url = None
        if target_ref_audio and os.path.exists(target_ref_audio):
            remote_ref_url = await self._upload_reference_audio(target_ref_audio)

        payload = {
            "text": clean_text,
            "ref_text": actual_ref_text or "",
            "language": language,
            "num_step": steps,
            "guidance_scale": cfg,
            "speed": spd,
            "normalize": True,
        }

        if remote_ref_url:
            payload["ref_audio_url"] = remote_ref_url
        else:
            # Fallback to the registered Egyptian character "mazen"
            payload["character_id"] = "mazen"

        resp = await client.post(f"{self._url}/api/clone", json=payload, timeout=60.0)
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
        audio_resp = await client.get(full_audio_url, timeout=30.0)
        if audio_resp.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch synthesized audio from {full_audio_url} (HTTP {audio_resp.status_code})"
            )

        audio_content = audio_resp.content
        if len(audio_content) <= 1000:
            raise RuntimeError(
                f"VoiceTuT Studio microservice returned corrupt/empty audio ({len(audio_content)} bytes)"
            )

        logger.info(f"VoiceTut microservice synthesized {len(audio_content)} bytes (RTF: {data.get('rtf')}x, steps: {steps})")
        return audio_content
