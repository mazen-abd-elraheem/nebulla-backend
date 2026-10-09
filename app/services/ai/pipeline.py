"""
AI Pipeline — orchestrates STT → LLM → TTS with full streaming.

Latency targets (doc §6.3):
  VAD + STT:     0.2 – 0.6 s
  LLM first tok: 0.3 – 0.8 s
  TTS first sent:0.5 – 1.7 s
  Total target:  1.5 – 3 s

Strategy:
  1. Stream STT tokens as they arrive
  2. Pass transcript to LLM in streaming mode
  3. TTS starts on the FIRST sentence (not the full response)
  4. Signal planner extracts gesture markers in parallel
"""

import asyncio
import time
from typing import AsyncIterator

from app.core.config import settings
from app.core.logger import get_logger
from app.providers.stt.base import BaseSTTProvider
from app.providers.tts.base import BaseTTSProvider
from app.providers.llm.base import BaseLLMProvider
from app.services.memory.rag_service import RAGService
from app.services.motion.signal_planner import SignalPlanner
from app.websocket.manager import manager

logger = get_logger(__name__)


class AIPipeline:
    """
    End-to-end voice conversation pipeline.
    Injected with swappable STT/LLM/TTS providers via factory.
    """

    def __init__(self):
        self._stt = _load_stt_provider()
        self._llm = _load_llm_provider()
        self._tts = _load_tts_provider()
        self._rag = RAGService()
        self._planner = SignalPlanner()
        self._audio_buffer: bytearray = bytearray()

    async def process_audio_chunk(self, chunk: bytes) -> None:
        """
        Accumulate audio from the phone, detect end-of-speech (VAD),
        then run the full pipeline.
        """
        self._audio_buffer.extend(chunk)

        # VAD: check for silence (simple energy-based check)
        if _is_end_of_utterance(self._audio_buffer):
            audio = bytes(self._audio_buffer)
            self._audio_buffer.clear()
            asyncio.create_task(self._run_pipeline(audio))

    async def _run_pipeline(self, audio: bytes) -> None:
        t_start = time.perf_counter()

        # ── 1. STT ────────────────────────────────────────────────────────
        transcript = await self._stt.transcribe(audio)
        t_stt = time.perf_counter()
        stt_ms = (t_stt - t_start) * 1000
        logger.info(f"STT ({stt_ms:.0f}ms): {transcript!r}")

        if not transcript.strip():
            return

        # Acknowledge receipt immediately (doc §6.3 "head nod trick")
        await manager.send_to_phone({"t": "eyes", "mood": "thinking"})

        # ── 2. Memory Retrieval (RAG) ─────────────────────────────────────
        memories = await self._rag.retrieve(transcript)

        # ── 3. LLM (streaming) ───────────────────────────────────────────
        t_llm_start = time.perf_counter()
        full_response = ""
        sentence_buffer = ""
        first_sentence_sent = False

        async for token in self._llm.generate_stream(transcript, memories):
            full_response += token
            sentence_buffer += token

            # Stream text to desktop live display
            await manager.broadcast_to_desks({
                "t": "text_stream",
                "token": token,
                "is_final": False,
            })

            # TTS starts on first complete sentence (low latency trick)
            if not first_sentence_sent and _is_sentence_end(sentence_buffer):
                t_tts_start = time.perf_counter()
                audio_out = await self._tts.synthesize(sentence_buffer.strip())
                t_tts_end = time.perf_counter()
                tts_ms = (t_tts_end - t_tts_start) * 1000
                logger.info(f"TTS first sentence ({tts_ms:.0f}ms)")
                await manager.send_to_phone(audio_out)
                sentence_buffer = ""
                first_sentence_sent = True

        t_llm = time.perf_counter()
        llm_ms = (t_llm - t_llm_start) * 1000

        # ── 4. Send remaining TTS audio ───────────────────────────────────
        if sentence_buffer.strip():
            audio_out = await self._tts.synthesize(sentence_buffer.strip())
            await manager.send_to_phone(audio_out)

        # ── 5. Extract gesture / emotion markers from response ─────────────
        commands = await self._planner.extract_from_response(full_response)
        for cmd in commands:
            await manager.send_to_esp(cmd)

        # ── 6. Update emotion on phone display ────────────────────────────
        emotion = _extract_emotion(full_response)
        await manager.send_to_phone({"t": "eyes", "mood": emotion})

        # ── 7. Final text token + total latency broadcast ─────────────────
        total_ms = (time.perf_counter() - t_start) * 1000
        await manager.broadcast_to_desks({
            "t": "text_stream",
            "token": "",
            "is_final": True,
            "response": full_response,
            "latency": {
                "stt_ms": round(stt_ms),
                "llm_ms": round(llm_ms),
                "total_ms": round(total_ms),
            },
        })
        logger.info(f"Pipeline complete in {total_ms:.0f}ms")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_end_of_utterance(buffer: bytearray, min_bytes: int = 8000) -> bool:
    """
    Simplified VAD: considers silence if buffer is large enough.
    Replace with proper WebRTC VAD in production.
    """
    return len(buffer) >= min_bytes


def _is_sentence_end(text: str) -> bool:
    return any(text.rstrip().endswith(p) for p in (".", "!", "?", "؟", "،", "\n"))


def _extract_emotion(text: str) -> str:
    """Extract emotion marker from LLM response."""
    text_lower = text.lower()
    if any(w in text_lower for w in ["happy", "فرحان", "😊"]):
        return "happy"
    if any(w in text_lower for w in ["sad", "حزين", "😢"]):
        return "sad"
    if any(w in text_lower for w in ["surprised", "متفاجئ", "😲"]):
        return "surprised"
    return "neutral"


# ── Provider Factories ───────────────────────────────────────────────────────

def _load_stt_provider() -> "BaseSTTProvider":
    from app.providers.stt.factory import get_stt_provider
    return get_stt_provider(settings.STT_PROVIDER)


def _load_tts_provider() -> "BaseTTSProvider":
    from app.providers.tts.factory import get_tts_provider
    return get_tts_provider(settings.TTS_PROVIDER)


def _load_llm_provider() -> "BaseLLMProvider":
    from app.providers.llm.factory import get_llm_provider
    return get_llm_provider(settings.LLM_PROVIDER)
