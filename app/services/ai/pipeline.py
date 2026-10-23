"""
AI Pipeline — orchestrates STT → LLM → TTS with full streaming.

Latency targets (doc §6.3):
  VAD + STT:     0.2 – 0.6 s
  LLM first tok: 0.3 – 0.8 s
  TTS first sent:0.5 – 1.7 s
  Total target:  1.5 – 3 s

Strategy:
  1. Stream STT tokens as they arrive
  2. Pass transcript to LLM in streaming mode (with personality, RAG memories, and conversation history)
  3. TTS starts on the FIRST sentence (with gesture tags cleanly stripped)
  4. Signal planner extracts gesture markers in parallel
  5. Asynchronously persist conversation and message latencies to database
"""

import asyncio
import re
import time
import uuid
from typing import AsyncIterator, List, Dict, Optional, Tuple

from sqlalchemy import select

from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import AsyncSessionLocal
from app.models.personality import Personality
from app.models.conversation import Conversation, Message
from app.providers.stt.base import BaseSTTProvider
from app.providers.tts.base import BaseTTSProvider
from app.providers.llm.base import BaseLLMProvider
from app.services.memory.rag_service import RAGService
from app.services.motion.signal_planner import SignalPlanner
from app.websocket.manager import manager

logger = get_logger(__name__)

_TAG_RE = re.compile(r"\[[a-zA-Z_]+\]")


def clean_text_for_tts(text: str) -> str:
    """Remove gesture markers like [happy] or [wave] before sending to TTS."""
    cleaned = _TAG_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


class AIPipeline:
    """
    End-to-end voice conversation pipeline.
    Injected with swappable STT/LLM/TTS providers via factory.
    """

    def __init__(self, session_id: Optional[str] = None):
        self._stt = _load_stt_provider()
        self._llm = _load_llm_provider()
        self._tts = _load_tts_provider()
        self._rag = RAGService()
        self._planner = SignalPlanner()
        self._audio_buffer: bytearray = bytearray()
        self.session_id: str = session_id or str(uuid.uuid4())

    def reload_providers(self) -> None:
        """Reload STT, LLM, and TTS providers dynamically when settings change."""
        self._stt = _load_stt_provider()
        self._llm = _load_llm_provider()
        self._tts = _load_tts_provider()
        logger.info(
            f"AI Pipeline providers reloaded: LLM={settings.LLM_PROVIDER}, "
            f"STT={settings.STT_PROVIDER}, TTS={settings.TTS_PROVIDER}"
        )

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

        # ── 2. Personality & Context Retrieval ───────────────────────────
        active_pid, active_prompt = await self._get_active_personality()
        memories = await self._rag.retrieve(transcript, personality_id=active_pid)
        history = await self._get_recent_history(limit=6)

        # ── 3. LLM (streaming) ───────────────────────────────────────────
        t_llm_start = time.perf_counter()
        full_response = ""
        sentence_buffer = ""
        first_sentence_sent = False
        first_tts_ms: Optional[float] = None

        async for token in self._llm.generate_stream(
            transcript,
            context=memories,
            system_prompt=active_prompt,
            history=history,
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
                tts_text = clean_text_for_tts(sentence_buffer)
                sentence_buffer = ""
                first_sentence_sent = True

                if tts_text:
                    t_tts_start = time.perf_counter()
                    audio_out = await self._generate_tts(tts_text, active_pid)
                    t_tts_end = time.perf_counter()
                    first_tts_ms = (t_tts_end - t_tts_start) * 1000
                    logger.info(f"TTS first sentence ({first_tts_ms:.0f}ms): {tts_text!r}")
                    await manager.send_to_phone(audio_out)

        t_llm = time.perf_counter()
        llm_ms = (t_llm - t_llm_start) * 1000

        # ── 4. Send remaining TTS audio ───────────────────────────────────
        remaining_tts_ms = 0.0
        remaining_text = clean_text_for_tts(sentence_buffer)
        if remaining_text:
            t_rem_start = time.perf_counter()
            audio_out = await self._generate_tts(remaining_text, active_pid)
            remaining_tts_ms = (time.perf_counter() - t_rem_start) * 1000
            await manager.send_to_phone(audio_out)

        total_tts_ms = (first_tts_ms or 0.0) + remaining_tts_ms

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
                "tts_ms": round(total_tts_ms),
                "total_ms": round(total_ms),
            },
        })
        logger.info(f"Pipeline complete in {total_ms:.0f}ms")

        # ── 8. Asynchronously persist conversation to database ────────────
        asyncio.create_task(
            self._save_conversation_turn(
                personality_id=active_pid,
                user_transcript=transcript,
                robot_response=full_response,
                stt_ms=stt_ms,
                llm_ms=llm_ms,
                tts_ms=total_tts_ms,
                total_ms=total_ms,
                emotion=emotion,
            )
        )

    async def _generate_tts(self, text: str, personality_id: Optional[int]) -> bytes:
        """Synthesize text using the cloned voice of the personality, falling back to base TTS."""
        try:
            from app.services.voice_clone.voice_clone_service import VoiceCloneService
            res = await VoiceCloneService.get_instance().synthesize(
                text=text,
                personality_id=personality_id,
            )
            if res and len(res) > 2000:
                return res
        except Exception as e:
            logger.warning(f"Voice clone synthesis failed in AI pipeline: {e}, falling back to base TTS")

        return await self._tts.synthesize(text)

    # ── Database Helpers ──────────────────────────────────────────────────────

    async def _get_active_personality(self) -> Tuple[Optional[int], Optional[str]]:
        """Fetch currently active personality from database if set."""
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(Personality).where(Personality.is_active == True).limit(1)  # noqa: E712
                )
                p = res.scalar_one_or_none()
                if p:
                    prompt = p.system_prompt or ""
                    if p.dialect and p.dialect != "cairo":
                        prompt += f"\nالتزم بلهجة: {p.dialect}."
                    return p.id, prompt.strip() or None
        except Exception as e:
            logger.warning(f"Could not load active personality from DB: {e}")
        return None, None

    async def _get_recent_history(self, limit: int = 6) -> List[Dict[str, str]]:
        """Fetch recent messages for context from current session."""
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(Conversation)
                    .where(Conversation.session_id == self.session_id)
                    .order_by(Conversation.started_at.desc())
                    .limit(1)
                )
                conv = res.scalar_one_or_none()
                if not conv:
                    return []

                msg_res = await session.execute(
                    select(Message)
                    .where(Message.conversation_id == conv.id)
                    .order_by(Message.created_at.desc(), Message.id.desc())
                    .limit(limit)
                )
                msgs = list(reversed(msg_res.scalars().all()))
                return [{"role": m.role, "content": m.content} for m in msgs]
        except Exception as e:
            logger.warning(f"Could not load recent history: {e}")
            return []

    async def _save_conversation_turn(
        self,
        personality_id: Optional[int],
        user_transcript: str,
        robot_response: str,
        stt_ms: float,
        llm_ms: float,
        tts_ms: float,
        total_ms: float,
        emotion: str,
    ) -> None:
        """Save user utterance and robot response into DB."""
        try:
            async with AsyncSessionLocal() as session:
                res = await session.execute(
                    select(Conversation)
                    .where(Conversation.session_id == self.session_id)
                    .order_by(Conversation.started_at.desc())
                    .limit(1)
                )
                conv = res.scalar_one_or_none()
                if not conv:
                    if personality_id is None:
                        res_p = await session.execute(select(Personality.id).limit(1))
                        first_p = res_p.scalar_one_or_none()
                        if first_p:
                            personality_id = first_p
                        else:
                            default_p = Personality(
                                name="default",
                                system_prompt="أنت توأم رقمي مصري.",
                                dialect="cairo",
                                is_active=True,
                            )
                            session.add(default_p)
                            await session.flush()
                            personality_id = default_p.id

                    conv = Conversation(
                        personality_id=personality_id,
                        session_id=self.session_id,
                    )
                    session.add(conv)
                    await session.flush()

                user_msg = Message(
                    conversation_id=conv.id,
                    role="user",
                    content=user_transcript,
                    stt_latency_ms=round(stt_ms, 2),
                )
                robot_msg = Message(
                    conversation_id=conv.id,
                    role="robot",
                    content=robot_response,
                    llm_latency_ms=round(llm_ms, 2),
                    tts_latency_ms=round(tts_ms, 2),
                    total_latency_ms=round(total_ms, 2),
                    emotion=emotion,
                )
                session.add_all([user_msg, robot_msg])
                await session.commit()
        except Exception as e:
            logger.warning(f"Failed to persist conversation turn: {e}")


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
    """Extract emotion marker from LLM response (supports [tags] and keywords)."""
    text_lower = text.lower()
    tags = _TAG_RE.findall(text)
    for tag in tags:
        t_clean = tag.strip("[]").lower()
        if t_clean in ("happy", "فرحان", "smile", "joy"):
            return "happy"
        if t_clean in ("sad", "حزين"):
            return "sad"
        if t_clean in ("surprised", "متفاجئ", "shocked"):
            return "surprised"

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
