"""
AI Pipeline — orchestrates STT → RAG → LLM → TTS with full streaming.

Latency targets (doc §6.3):
  VAD + STT:     0.2 – 0.6 s
  LLM first tok: 0.3 – 0.8 s
  TTS first sent:0.5 – 1.7 s
  Total target:  1.5 – 3 s

Strategy:
  1. Stream STT tokens as they arrive
  2. Retrieve relevant memories via RAG (grounding context)
  3. Pass transcript + RAG memories + active personality prompt to LLM in streaming mode
  4. TTS starts on the FIRST sentence (not the full response)
  5. Signal planner extracts gesture markers in parallel
  6. Support both voice audio pipeline and direct text chat pipeline
"""

import asyncio
import time
from typing import AsyncIterator
import uuid

from sqlalchemy import select

from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import AsyncSessionLocal
from app.models.conversation import Conversation, Message
from app.models.personality import Personality
from app.providers.stt.base import BaseSTTProvider
from app.providers.tts.base import BaseTTSProvider
from app.providers.llm.base import BaseLLMProvider
from app.services.memory.rag_service import RAGService
from app.services.motion.signal_planner import SignalPlanner
from app.websocket.manager import manager

logger = get_logger(__name__)


class AIPipeline:
    """
    End-to-end voice and text conversation pipeline with RAG memory grounding.
    Injected with swappable STT/LLM/TTS providers via factory.
    """

    def __init__(self):
        self._stt = _load_stt_provider()
        self._llm = _load_llm_provider()
        self._tts = _load_tts_provider()
        self._rag = RAGService()
        self._planner = SignalPlanner()
        self._audio_buffer: bytearray = bytearray()

    @property
    def rag(self) -> RAGService:
        return self._rag

    @property
    def llm(self) -> BaseLLMProvider:
        return self._llm

    # ── Voice Audio Ingestion ──────────────────────────────────────────────────

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
        active_p = await self._get_active_personality()
        pid = active_p.id if active_p else None
        sys_prompt = active_p.system_prompt if active_p else None

        memories = await self._rag.retrieve(transcript, personality_id=pid)
        logger.info(f"RAG retrieved {len(memories)} memories for personality={pid}")

        # ── 3. LLM (streaming) with RAG context ───────────────────────────
        t_llm_start = time.perf_counter()
        full_response = ""
        sentence_buffer = ""
        first_sentence_sent = False

        async for token in self._llm.generate_stream(
            prompt=transcript,
            context=memories,
            system_prompt=sys_prompt,
        ):
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

        # ── 8. Persist conversation turn to DB ─────────────────────────────
        asyncio.create_task(
            self._record_turn(
                session_id="voice-session",
                user_text=transcript,
                assistant_text=full_response,
                emotion=emotion,
                stt_ms=stt_ms,
                llm_ms=llm_ms,
                total_ms=total_ms,
            )
        )

    # ── Text Ingestion (Direct RAG + LLM Chat) ────────────────────────────────

    async def process_text(
        self,
        text: str,
        personality_id: int | None = None,
        session_id: str | None = None,
        broadcast_to_clients: bool = True,
    ) -> dict:
        """
        Process a text query directly through RAG + LLM.
        Useful for REST API, desktop control room text chat, or testing.
        """
        t_start = time.perf_counter()
        session_id = session_id or f"text-{uuid.uuid4().hex[:8]}"

        # Load personality if specified or active
        if personality_id is not None:
            p = await self._get_personality_by_id(personality_id)
        else:
            p = await self._get_active_personality()

        pid = p.id if p else None
        sys_prompt = p.system_prompt if p else None

        # 1. RAG retrieval
        memories = await self._rag.retrieve(text, personality_id=pid)

        # 2. LLM response generation
        t_llm_start = time.perf_counter()
        full_response = ""
        async for token in self._llm.generate_stream(
            prompt=text,
            context=memories,
            system_prompt=sys_prompt,
        ):
            full_response += token
            if broadcast_to_clients:
                await manager.broadcast_to_desks({
                    "t": "text_stream",
                    "token": token,
                    "is_final": False,
                })

        t_llm = time.perf_counter()
        llm_ms = (t_llm - t_llm_start) * 1000
        total_ms = (time.perf_counter() - t_start) * 1000
        emotion = _extract_emotion(full_response)

        if broadcast_to_clients:
            await manager.broadcast_to_desks({
                "t": "text_stream",
                "token": "",
                "is_final": True,
                "response": full_response,
                "latency": {"llm_ms": round(llm_ms), "total_ms": round(total_ms)},
            })
            await manager.send_to_phone({"t": "eyes", "mood": emotion})

        # Save turn to DB
        asyncio.create_task(
            self._record_turn(
                session_id=session_id,
                user_text=text,
                assistant_text=full_response,
                emotion=emotion,
                llm_ms=llm_ms,
                total_ms=total_ms,
            )
        )

        return {
            "session_id": session_id,
            "response": full_response,
            "retrieved_memories": memories,
            "personality_id": pid,
            "emotion": emotion,
            "latency": {
                "llm_ms": round(llm_ms, 2),
                "total_ms": round(total_ms, 2),
            },
        }

    async def process_text_stream(
        self,
        text: str,
        personality_id: int | None = None,
        session_id: str | None = None,
    ) -> AsyncIterator[dict]:
        """
        Stream tokens directly to caller as an AsyncIterator.
        Yields dicts with {"type": "token", "content": "..."} then {"type": "done", ...}.
        """
        session_id = session_id or f"stream-{uuid.uuid4().hex[:8]}"

        if personality_id is not None:
            p = await self._get_personality_by_id(personality_id)
        else:
            p = await self._get_active_personality()

        pid = p.id if p else None
        sys_prompt = p.system_prompt if p else None

        # 1. Retrieve RAG memories
        memories = await self._rag.retrieve(text, personality_id=pid)
        yield {
            "type": "context",
            "memories": memories,
            "personality_id": pid,
        }

        # 2. Stream LLM tokens
        full_response = ""
        t_llm_start = time.perf_counter()

        async for token in self._llm.generate_stream(
            prompt=text,
            context=memories,
            system_prompt=sys_prompt,
        ):
            full_response += token
            yield {
                "type": "token",
                "content": token,
            }

        llm_ms = (time.perf_counter() - t_llm_start) * 1000
        emotion = _extract_emotion(full_response)

        asyncio.create_task(
            self._record_turn(
                session_id=session_id,
                user_text=text,
                assistant_text=full_response,
                emotion=emotion,
                llm_ms=llm_ms,
                total_ms=llm_ms,
            )
        )

        yield {
            "type": "done",
            "session_id": session_id,
            "response": full_response,
            "emotion": emotion,
            "llm_ms": round(llm_ms, 2),
        }

    # ── Database Helpers ──────────────────────────────────────────────────────

    async def _get_active_personality(self) -> Personality | None:
        try:
            async with AsyncSessionLocal() as session:
                r = await session.execute(
                    select(Personality).where(Personality.is_active == True).limit(1)
                )
                return r.scalars().first()
        except Exception as e:
            logger.warning(f"Failed to query active personality: {e}")
            return None

    async def _get_personality_by_id(self, pid: int) -> Personality | None:
        try:
            async with AsyncSessionLocal() as session:
                return await session.get(Personality, pid)
        except Exception as e:
            logger.warning(f"Failed to query personality {pid}: {e}")
            return None

    async def _record_turn(
        self,
        session_id: str,
        user_text: str,
        assistant_text: str,
        emotion: str | None = None,
        stt_ms: float | None = None,
        llm_ms: float | None = None,
        tts_ms: float | None = None,
        total_ms: float | None = None,
    ) -> None:
        try:
            async with AsyncSessionLocal() as session:
                # Find or create conversation session
                r = await session.execute(
                    select(Conversation).where(Conversation.session_id == session_id)
                )
                conv = r.scalars().first()
                if not conv:
                    conv = Conversation(session_id=session_id)
                    session.add(conv)
                    await session.flush()

                u_msg = Message(
                    conversation_id=conv.id,
                    role="user",
                    content=user_text,
                )
                a_msg = Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=assistant_text,
                    emotion=emotion,
                    stt_latency_ms=stt_ms,
                    llm_latency_ms=llm_ms,
                    tts_latency_ms=tts_ms,
                    total_latency_ms=total_ms,
                )
                session.add(u_msg)
                session.add(a_msg)
                await session.commit()
        except Exception as e:
            logger.warning(f"Could not persist conversation turn to DB: {e}")


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
    if any(w in text_lower for w in ["happy", "فرحان", "😊", "مبسوط"]):
        return "happy"
    if any(w in text_lower for w in ["sad", "حزين", "😢", "زعلان"]):
        return "sad"
    if any(w in text_lower for w in ["surprised", "متفاجئ", "😲", "واو"]):
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
