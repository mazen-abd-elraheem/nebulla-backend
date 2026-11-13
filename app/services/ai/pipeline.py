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
from concurrent.futures import ThreadPoolExecutor
import re
import time
import uuid
from typing import AsyncIterator, List, Dict, Optional, Tuple, Any

from sqlalchemy import select

from app.core.config import settings
from app.core.logger import get_logger
from app.db.session import AsyncSessionLocal
from app.models.personality import Personality
from app.models.conversation import Conversation, Message
from app.providers.stt.base import BaseSTTProvider
from app.providers.tts.base import BaseTTSProvider
from app.providers.llm.base import BaseLLMProvider
from app.services.ai.context_builder import build_grounding_context, is_greeting_or_persona_inquiry
from app.services.memory.rag_service import RAGService
from app.services.memory.fact_verifier import FactVerifier
from app.services.motion.signal_planner import SignalPlanner
from app.services.voice_clone.voice_clone_service import VoiceCloneService
from app.services.phone_action import ActionOutcome, get_phone_action_service
from app.services.voice_verification.speaker_service import (
    VerificationResult,
    get_speaker_service,
)
from app.utils.masri_normalizer import (
    clean_llm_output_for_speech,
    extract_thoughts_and_actions,
    normalize_masri_orthography,
)
from app.websocket.manager import manager

logger = get_logger(__name__)

# Regex for gesture / emotion / action tags supporting both Latin and Arabic letters
_TAG_RE = re.compile(r"\[(?:action:|gesture:|cmd:)?([\w\u0600-\u06FF]+)(?::[^\]]+)?\]", re.IGNORECASE)


class StreamingThinkFilter:
    """
    Real-time streaming filter for internal reasoning tags (<think> ... </think>).
    Guarantees zero-leakage of token-boundary split tags (e.g. '<' then 'think>')
    into spoken text, TTS queue, or desktop user interface.
    Yields list of (is_thought: bool, token: str).
    """

    def __init__(self):
        self.in_think = False
        self.buffer = ""

    def process(self, token: str) -> List[Tuple[bool, str]]:
        out: List[Tuple[bool, str]] = []
        self.buffer += token

        while self.buffer:
            if not self.in_think:
                idx = self.buffer.find("<think>")
                if idx != -1:
                    normal_part = self.buffer[:idx]
                    if normal_part:
                        out.append((False, normal_part))
                    self.in_think = True
                    self.buffer = self.buffer[idx + 7:]
                    continue

                prefix_match = False
                for p_len in range(min(len(self.buffer), 6), 0, -1):
                    cand = self.buffer[-p_len:]
                    if "<think>".startswith(cand):
                        prefix_match = True
                        if len(self.buffer) > p_len:
                            out.append((False, self.buffer[:-p_len]))
                        self.buffer = cand
                        break
                if prefix_match:
                    break
                else:
                    out.append((False, self.buffer))
                    self.buffer = ""
            else:
                idx = self.buffer.find("</think>")
                if idx != -1:
                    thought_part = self.buffer[:idx]
                    if thought_part:
                        out.append((True, thought_part))
                    self.in_think = False
                    self.buffer = self.buffer[idx + 8:]
                    continue

                prefix_match = False
                for p_len in range(min(len(self.buffer), 7), 0, -1):
                    cand = self.buffer[-p_len:]
                    if "</think>".startswith(cand):
                        prefix_match = True
                        if len(self.buffer) > p_len:
                            out.append((True, self.buffer[:-p_len]))
                        self.buffer = cand
                        break
                if prefix_match:
                    break
                else:
                    out.append((True, self.buffer))
                    self.buffer = ""
        return out

    def flush(self) -> List[Tuple[bool, str]]:
        out: List[Tuple[bool, str]] = []
        if self.buffer:
            out.append((self.in_think, self.buffer))
            self.buffer = ""
        return out


def clean_text_for_tts(text: str) -> str:
    """Preprocess text with Egyptian Masri dialect normalizer before sending to TTS."""
    return clean_llm_output_for_speech(text)


def _extract_emotion(text: str) -> str:
    """Extract emotion marker from LLM response (supports [tags] and keywords)."""
    text_lower = text.lower()
    tags = _TAG_RE.findall(text)
    for tag in tags:
        t_clean = tag.strip("[]").lower()
        if t_clean in ("happy", "فرحان", "smile", "joy", "سعيد"):
            return "happy"
        if t_clean in ("sad", "حزين"):
            return "sad"
        if t_clean in ("surprised", "متفاجئ", "shocked"):
            return "surprised"
        if t_clean in ("wave", "لوح", "سلام", "باي"):
            return "wave"
        if t_clean in ("like", "اعجاب", "تمام", "عاش", "ممتاز"):
            return "like"
        if t_clean in ("love", "حب", "قلب"):
            return "love"
        if t_clean in ("neutral", "طبيعي"):
            return "neutral"

    if any(w in text_lower for w in ["happy", "فرحان", "😊"]):
        return "happy"
    if any(w in text_lower for w in ["sad", "حزين", "😢"]):
        return "sad"
    if any(w in text_lower for w in ["surprised", "متفاجئ", "😲"]):
        return "surprised"
    if any(w in text_lower for w in ["wave", "👋", "سلام", "باي"]):
        return "wave"
    if any(w in text_lower for w in ["like", "👍", "عاش"]):
        return "like"
    return "neutral"


def _is_micro_chunk_ready(text: str, is_first_chunk: bool = False) -> bool:
    """
    Evaluates whether buffered LLM tokens form a natural, prosodically complete micro-chunk.
    - First chunk: triggers on 4+ words + punctuation (، . ! ؟ ,) OR 7+ words (for <300ms TTFA).
    - Later chunks: triggers on 6+ words + punctuation OR 12+ words.
    """
    if text.count("[") > text.count("]"):
        return False
    stripped = text.strip()
    stripped_no_tags = _TAG_RE.sub("", stripped).strip()
    if not stripped_no_tags:
        return False
    words = stripped_no_tags.split()
    min_words = 4 if is_first_chunk else 6
    max_words = 8 if is_first_chunk else 14
    has_punct = any(stripped_no_tags.endswith(p) for p in (".", "!", "?", "؟", "،", ",", ":", "؛", "\n"))
    return (len(words) >= min_words and has_punct) or (len(words) >= max_words)


class EgyptianFastPathCache:
    """
    In-memory millisecond fast-path cache for common Egyptian Arabic greetings,
    social cues, and robot identity queries.
    Bypasses RAG and LLM inference entirely to deliver <10ms response latency.
    """

    _GREETINGS = [
        (
            re.compile(r"(صباح\s+(الخير|النور|الورد|الفل|الجمال))", re.IGNORECASE),
            "صباح الفل والورد عليك! منور يا فندم، جاهز أساعدك في أي حاجة محتاجها دلوقتي. [happy] [gesture:wave]",
        ),
        (
            re.compile(r"(مساء\s+(الخير|النور|الورد|الفل|الجمال))", re.IGNORECASE),
            "مساء النور والسرور يا غالي! أهلاً بيك، أقدر أساعدك في إيه النهاردة؟ [happy] [gesture:wave]",
        ),
        (
            re.compile(r"(أهلاً|اهلا|أهلا|مرحباً|مرحبا|هاي|هالو|hello|hi)", re.IGNORECASE),
            "أهلاً وسهلاً بيك! أنا نيبولا توأمك الرقمي، منورني النهاردة وجاهز أساعدك في أي وقت. [happy] [gesture:wave]",
        ),
        (
            re.compile(r"(إزيك|ازيك|عامل\s+إيه|عامل\s+ايه|أخبارك\s+إيه|اخبارك\s+ايه|أخبارك|اخبارك|إيه\s+الأخبار|ايه\s+الاخبار|كله\s+تمام)", re.IGNORECASE),
            "الحمد لله كله تمام وزي الفل، إنت عامل إيه يا فندم؟ يا رب تكون بأحسن حال. [happy] [action:nod]",
        ),
        (
            re.compile(r"(سلام\s+عليكم|السلام\s+عليكم|سلامو\s+عليكو|سلام)", re.IGNORECASE),
            "وعليكم السلام ورحمة الله وبركاته! أهلاً بيك، نورت نيبولا يا فندم. [happy] [gesture:wave]",
        ),
        (
            re.compile(r"(شكراً|شكرا|تسلم|تسلمي|ألف\s+شكر|الف\s+شكر|مشكور|thanks|thank\s+you)", re.IGNORECASE),
            "العفو يا فندم، الشكر لله! أنا في خدمتك دايماً في أي وقت. [like] [action:nod]",
        ),
    ]

    _IDENTITY_PATTERNS = [
        re.compile(r"(إنت\s+مين|انت\s+مين|مين\s+إنت|مين\s+انت|مين\s+حضرتك|اسمك\s+إيه|اسمك\s+ايه|عرف\s+نفسك|عرفنا\s+بنفسك)", re.IGNORECASE),
    ]

    _CREATOR_PATTERNS = [
        re.compile(r"مين\s+(صممك|عملك|برمجك|صنعك|طورك|صانعك|اخترعك)", re.IGNORECASE),
    ]

    _CAPABILITY_PATTERNS = [
        re.compile(r"(بتعمل\s+إيه|بتعمل\s+ايه|تقدر\s+تعمل\s+إيه|تقدر\s+تعمل\s+ايه|وظيفتك\s+إيه|وظيفتك\s+ايه|بتساعدني\s+في\s+إيه|بتساعدني\s+في\s+ايه)", re.IGNORECASE),
    ]

    @classmethod
    def match(cls, text: str, personality_id: Optional[int] = None, personality_name: Optional[str] = None) -> Optional[Tuple[str, str]]:
        """
        Fast-path pattern matching in <1ms.
        Returns Tuple[response_text, emotion] if matched, else None.
        """
        if not text:
            return None
        msg = text.strip()

        # Check standard Egyptian greetings
        for pat, reply in cls._GREETINGS:
            if pat.search(msg):
                emotion = _extract_emotion(reply)
                return reply, emotion

        # Determine if persona is Menna or Mazen
        p_name = (personality_name or "").lower()
        is_menna = personality_id == 2 or "منه" in p_name or "منّة" in p_name or "menna" in p_name

        # Check identity inquiries
        for pat in cls._IDENTITY_PATTERNS:
            if pat.search(msg):
                if is_menna:
                    reply = "أنا نيبولا (Nebula)، التوأم الرقمي الذكي والمساعد الشخصي للمهندسة منه محمد. [action:nod] [happy]"
                else:
                    reply = "أنا نيبولا (Nebula)، الروبوت الذكي والتوأم الرقمي الفيزيائي للمهندس مازن عبد الرحيم. [action:nod] [happy]"
                emotion = _extract_emotion(reply)
                return reply, emotion

        # Check creator inquiries
        for pat in cls._CREATOR_PATTERNS:
            if pat.search(msg):
                if is_menna:
                    reply = "صممتني وبرمجتني وطورتني المهندسة منه محمد، مطورة نظام نيبولا للذكاء الاصطناعي. [action:nod] [like]"
                else:
                    reply = "صممني وبرمجني وطورني المهندس مازن عبد الرحيم، رئيس ومطور مشروع نيبولا للتوأم الرقمي. [action:nod] [like]"
                emotion = _extract_emotion(reply)
                return reply, emotion

        # Check capability inquiries
        for pat in cls._CAPABILITY_PATTERNS:
            if pat.search(msg):
                reply = "أنا توأمك الرقمي الفيزيائي، بتحكم في مفاصل وحركات الروبوت، وبشوف الوشوش بنظام UniFace، وبسمعك وبساعدك في تنظيم مهامك ومواعيدك وذاكرتك بالكامل. [action:nod] [like]"
                emotion = _extract_emotion(reply)
                return reply, emotion

        return None


class AIPipeline:
    """
    End-to-end voice and text conversation pipeline with RAG memory grounding.
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
        self._active_task: Optional[asyncio.Task] = None
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="pipeline_worker")
        # Chapter 14: phone actions + voice verification
        self._actions = get_phone_action_service()
        self._verifier = get_speaker_service()
        self._actions.set_speaker(self.speak)

    def _dispatch_actuator_async(self, tag_str: str) -> None:
        """Non-blocking background dispatch of physical robot motions to ESP32 (0ms overhead)."""
        async def _worker():
            try:
                act_cmds = await self._planner.extract_from_response(tag_str)
                for cmd in act_cmds:
                    await manager.send_to_esp(cmd)
            except Exception as e:
                logger.debug(f"Actuator background dispatch notice: {e}")
        asyncio.create_task(_worker())

    async def _synthesize_and_dispatch_audio(
        self,
        text: str,
        personality_id: int | None,
        broadcast_to_clients: bool = True,
    ) -> Optional[bytes]:
        """
        Synthesizes text in the cloned voice for the given personality.
        - If the user/personality has a registered voice sample: synthesizes and sends to phone.
        - If NOT registered: sends a clear notification to clients without using any fallback model.
        """
        voice_svc = VoiceCloneService.get_instance()
        has_sample = voice_svc.has_voice_sample(personality_id)
        sample_path = voice_svc.get_sample_path(personality_id) if has_sample else None

        if has_sample and sample_path:
            cleaned = clean_text_for_tts(text)
            if cleaned:
                try:
                    audio_out = await voice_svc.synthesize(
                        text=cleaned,
                        personality_id=personality_id,
                        reference_wav=sample_path,
                    )
                    if audio_out and len(audio_out) > 500:
                        if broadcast_to_clients:
                            await manager.send_to_phone(audio_out)
                        return audio_out
                except Exception as ex:
                    logger.error(f"Voice synthesis error in pipeline: {ex}")
        else:
            notice_payload = {
                "t": "voice_clone_notice",
                "status": "sample_required",
                "message": "يرجى تسجيل عينة صوتك لتفعيل الرد الصوتي",
                "has_voice_sample": False,
                "personality_id": personality_id,
            }
            if broadcast_to_clients:
                await manager.send_to_phone(notice_payload)
                await manager.broadcast_to_desks(notice_payload)
        return None

    def reload_providers(self) -> None:
        """Reload STT, LLM, and TTS providers dynamically when settings change."""
        self._stt = _load_stt_provider()
        self._llm = _load_llm_provider()
        self._tts = _load_tts_provider()
        if hasattr(self._llm, "reset_client"):
            self._llm.reset_client()
        logger.info(
            f"AI Pipeline providers reloaded: LLM={settings.LLM_PROVIDER}, "
            f"STT={settings.STT_PROVIDER}, TTS={settings.TTS_PROVIDER}"
        )

    @property
    def rag(self) -> RAGService:
        return self._rag

    @property
    def llm(self) -> BaseLLMProvider:
        return self._llm

    @property
    def tts(self) -> BaseTTSProvider:
        return self._tts

    @property
    def stt(self) -> BaseSTTProvider:
        return self._stt

    async def process_audio_chunk(self, chunk: bytes) -> None:
        """
        Accumulate audio from the phone, detect end-of-speech (VAD),
        then run the full pipeline. Handles barge-in cancellation if user speaks again.
        """
        # Privacy mute (benefits_section.docx §14.5): while a phone call is ringing/active the
        # mic belongs to the call. Drop the audio — never buffer, transcribe or verify it.
        if settings.PHONE_ACTIONS_ENABLED and self._actions.in_call():
            self._audio_buffer.clear()
            return

        # Cap incoming chunk and total buffer to prevent unbounded memory growth (DoS)
        MAX_AUDIO_BUFFER_BYTES = 320_000  # ~10s of 16kHz 16-bit mono audio
        if len(self._audio_buffer) + len(chunk) > MAX_AUDIO_BUFFER_BYTES:
            logger.warning("Audio buffer exceeded 10s maximum; flushing buffer")
            audio = bytes(self._audio_buffer)
            self._audio_buffer.clear()
            if self._active_task and not self._active_task.done():
                self._active_task.cancel()
            self._active_task = asyncio.create_task(self._run_pipeline(audio))
            return

        self._audio_buffer.extend(chunk)

        # VAD: check for silence (simple energy-based check)
        if _is_end_of_utterance(self._audio_buffer):
            audio = bytes(self._audio_buffer)
            self._audio_buffer.clear()
            if self._active_task and not self._active_task.done():
                logger.info("Cancelling previous turn due to new user speech (barge-in)")
                self._active_task.cancel()
            self._active_task = asyncio.create_task(self._run_pipeline(audio))

    async def speak(self, text: str, mood: Optional[str] = None) -> None:
        """Speak `text` on the phone with the active personality's voice (used by phone actions)."""
        pid, _ = await self._get_active_personality()
        if mood:
            await manager.send_to_phone({"t": "eyes", "mood": mood})
        audio_out = await self._generate_tts(clean_text_for_tts(text), pid)
        await manager.send_to_phone(audio_out)

    async def _transcribe_and_verify(
        self, audio: bytes
    ) -> Tuple[str, Optional[VerificationResult]]:
        """Run STT and speaker verification concurrently (no added latency). Verification fails closed."""
        if not (settings.PHONE_ACTIONS_ENABLED and settings.SPEAKER_VERIFICATION_ENABLED):
            return await self._stt.transcribe(audio), None
        transcript, verification = await asyncio.gather(
            self._stt.transcribe(audio),
            self._verifier.verify(audio),
            return_exceptions=True,
        )
        if isinstance(transcript, BaseException):
            raise transcript
        if isinstance(verification, BaseException):
            logger.warning(f"Speaker verification error (treated as unverified): {verification}")
            verification = None
        return transcript, verification

    async def _run_pipeline(self, audio: bytes) -> None:
        t_start = time.perf_counter()

        # ── 1. STT (+ speaker verification in parallel) ───────────────────
        transcript, verification = await self._transcribe_and_verify(audio)
        t_stt = time.perf_counter()
        stt_ms = (t_stt - t_start) * 1000
        logger.info(f"STT ({stt_ms:.0f}ms): {len(transcript)} chars")

        if not transcript.strip():
            return

        # ── 1c. Fast-Path In-Memory Cache (<5ms response for greetings/identity) ──
        fast_result = EgyptianFastPathCache.match(transcript)
        if fast_result is not None:
            fast_reply, fast_emotion = fast_result
            t_fast = (time.perf_counter() - t_start) * 1000
            logger.info(f"⚡ Fast-Path match in {t_fast:.1f}ms: '{transcript}' -> '{fast_reply}'")

            # Update emotion and broadcast text instantly
            await manager.send_to_phone({"t": "eyes", "mood": fast_emotion})
            await manager.broadcast_to_desks({
                "t": "text_stream",
                "token": fast_reply,
                "is_final": True,
                "response": fast_reply,
                "latency": {
                    "stt_ms": round(stt_ms),
                    "llm_ms": 0,
                    "tts_ms": 0,
                    "total_ms": round(t_fast),
                },
            })

            # Dispatch physical gestures asynchronously (zero latency impact)
            self._dispatch_actuator_async(fast_reply)

            # Synthesize & speak in cloned voice
            cleaned_fast = clean_text_for_tts(fast_reply)
            if cleaned_fast:
                try:
                    active_pid, _ = await self._get_active_personality()
                    audio_out = await self._generate_tts(cleaned_fast, active_pid)
                    await manager.send_to_phone(audio_out)
                except Exception as ex:
                    logger.error(f"TTS error during fast-path playback: {ex}")

            # Persist turn asynchronously
            asyncio.create_task(
                self._save_conversation_turn(
                    personality_id=1,
                    user_transcript=transcript,
                    robot_response=fast_reply,
                    stt_ms=stt_ms,
                    llm_ms=0.0,
                    tts_ms=0.0,
                    total_ms=t_fast,
                    emotion=fast_emotion,
                )
            )
            return

        # ── 1b. Phone actions («كلّم ماما», open maps, reminders …) ───────
        # Deterministic planner + security Guard; the LLM is never involved in deciding
        # whether a phone action runs. Action turns are NOT persisted to conversation
        # history (they can contain message bodies / challenge phrases).
        if settings.PHONE_ACTIONS_ENABLED:
            outcome: ActionOutcome = await self._actions.handle_utterance(transcript, verification)
            if outcome.handled:
                if outcome.speech:
                    try:
                        await self.speak(outcome.speech, outcome.mood)
                    except Exception as ex:
                        logger.error(f"TTS error while speaking action response: {ex}")
                    await manager.broadcast_to_desks({
                        "t": "action_event",
                        "speech": outcome.speech,
                    })
                return

        # Acknowledge receipt immediately (doc §6.3 "head nod trick")
        await manager.send_to_phone({"t": "eyes", "mood": "thinking"})

        # ── 2. Personality, Vision & Context Grounding ────────────────────
        active_pid: Optional[int] = None
        active_prompt: Optional[str] = None
        memories: List[str] = []
        grounding = None
        speaker_id_name = None
        if verification and (getattr(verification, "passed_l1", False) or getattr(verification, "passed_l2", False)):
            speaker_id_name = getattr(verification, "speaker_name", None)

        try:
            async with AsyncSessionLocal() as session:
                active_prompt, memories, grounding, active_pid = await build_grounding_context(
                    db=session,
                    personality_id=None,
                    message=transcript,
                    verified_speaker=speaker_id_name,
                )
        except Exception as e:
            logger.warning(f"Could not build full grounding context, falling back: {e}")
            active_pid, active_prompt = await self._get_active_personality()
            memories = await self._rag.retrieve(transcript, personality_id=active_pid)

        # Broadcast RAG & Visual telemetry to desktop screens
        if grounding and getattr(grounding, "faces", None):
            photo_url = grounding.faces.get("photo_url")
            rag_person_name = grounding.faces.get("active_person")
            await manager.broadcast_to_desks({
                "t": "rag_telemetry",
                "query": transcript,
                "detected_person": rag_person_name,
                "person_photo_url": photo_url,
                "memories_count": len(memories),
                "memories": memories,
            })
            if photo_url and (grounding.faces.get("is_photo_inquiry") or grounding.faces.get("currently_detected")):
                await manager.broadcast_to_desks({
                    "t": "screen_action",
                    "action": "show_person_photo",
                    "name": rag_person_name,
                    "url": photo_url,
                })

        history = await self._get_recent_history(limit=6)

        # ── 3. Streaming LLM + Decoupled TTS Pipeline ─────────────────────
        tts_queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        tts_latencies: List[float] = []

        # Check for cloned voice sample bound to active personality
        voice_svc = VoiceCloneService.get_instance()
        cloned_wav_path = voice_svc.get_sample_path(active_pid) if active_pid else None

        async def _tts_worker():
            while True:
                sentence = await tts_queue.get()
                if sentence is None:
                    tts_queue.task_done()
                    break
                try:
                    t_tts_start = time.perf_counter()
                    if cloned_wav_path:
                        audio_out = await voice_svc.synthesize(
                            text=sentence,
                            personality_id=active_pid,
                            reference_wav=cloned_wav_path,
                        )
                    else:
                        audio_out = await self._tts.synthesize(sentence)
                    t_tts_end = time.perf_counter()
                    tts_latencies.append((t_tts_end - t_tts_start) * 1000)
                    await manager.send_to_phone(audio_out)
                except Exception as ex:
                    logger.error(f"TTS synthesis error: {ex}")
                finally:
                    tts_queue.task_done()

        tts_worker_task = asyncio.create_task(_tts_worker())

        # Strict Zero-Hallucination Guardrail (sub-10ms short-circuit, zero fallback model)
        is_ar = bool(re.search(r"[؀-ۿ]", transcript))
        refusal_reply = (
            "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
            if is_ar
            else "I do not have this information recorded in my memory. [wave]"
        )
        has_memories = bool(memories)
        is_greeting_persona = is_greeting_or_persona_inquiry(transcript)

        if not has_memories and not is_greeting_persona:
            full_response = refusal_reply
            emotion = "wave"
            total_ms = (time.perf_counter() - t_start) * 1000
            await manager.send_to_phone({"t": "eyes", "mood": emotion})

            # Send refusal speech directly through decoupled TTS worker
            tts_text = clean_text_for_tts(refusal_reply)
            if tts_text:
                await tts_queue.put(tts_text)
            await tts_queue.put(None)
            await tts_worker_task
            total_tts_ms = sum(tts_latencies)

            await manager.broadcast_to_desks({
                "t": "text_stream",
                "token": "",
                "is_final": True,
                "response": full_response,
                "latency": {
                    "stt_ms": round(stt_ms),
                    "llm_ms": 0,
                    "tts_ms": round(total_tts_ms),
                    "total_ms": round(total_ms),
                },
            })

            commands = await self._planner.extract_from_response(full_response)
            for cmd in commands:
                await manager.send_to_esp(cmd)

            asyncio.create_task(
                self._save_conversation_turn(
                    personality_id=active_pid,
                    user_transcript=transcript,
                    robot_response=full_response,
                    stt_ms=stt_ms,
                    llm_ms=0.0,
                    tts_ms=total_tts_ms,
                    total_ms=total_ms,
                    emotion=emotion,
                )
            )
            logger.info(f"Pipeline short-circuit refusal complete in {total_ms:.0f}ms")
            return

        t_llm_start = time.perf_counter()
        full_response = ""
        sentence_buffer = ""
        think_filter = StreamingThinkFilter()
        first_emotion_set = False
        dispatched_actions: set[str] = set()
        is_first_chunk = True

        try:
            async for raw_token in self._llm.generate_stream(
                transcript,
                context=memories,
                system_prompt=active_prompt,
                history=history,
            ):
                for is_thought, token in think_filter.process(raw_token):
                    if is_thought:
                        await manager.broadcast_to_desks({
                            "t": "thought_stream",
                            "token": token,
                        })
                    else:
                        full_response += token
                        sentence_buffer += token

                        # Stream clean spoken text to desktop display
                        await manager.broadcast_to_desks({
                            "t": "text_stream",
                            "token": token,
                            "is_final": False,
                        })

                        # Real-time emotion update to phone display as soon as detected
                        if not first_emotion_set:
                            detected_emotion = _extract_emotion(sentence_buffer)
                            if detected_emotion != "neutral":
                                await manager.send_to_phone({"t": "eyes", "mood": detected_emotion})
                                first_emotion_set = True

                        # Check for action tags in real-time and execute on robot actuators
                        for tag_match in _TAG_RE.finditer(sentence_buffer):
                            tag_str = tag_match.group(0)
                            if tag_str not in dispatched_actions:
                                dispatched_actions.add(tag_str)
                                act_cmds = await self._planner.extract_from_response(tag_str)
                                for cmd in act_cmds:
                                    await manager.send_to_esp(cmd)

                        # As sentences complete, enqueue to TTS with deterministic Fact Verification
                        if _is_sentence_end(sentence_buffer):
                            raw_tts_text = clean_text_for_tts(sentence_buffer)
                            sentence_buffer = ""
                            if raw_tts_text:
                                verified_tts = FactVerifier.verify_and_sanitize(
                                    query=transcript,
                                    response=raw_tts_text,
                                    retrieved_memories=memories,
                                    is_greeting=is_greeting_persona,
                                )
                                tts_clean = clean_text_for_tts(verified_tts)
                                if tts_clean:
                                    await tts_queue.put(tts_clean)

            # Flush any remaining tokens in think filter
            for is_thought, token in think_filter.flush():
                if is_thought:
                    await manager.broadcast_to_desks({
                        "t": "thought_stream",
                        "token": token,
                    })
                    continue

                full_response += token
                sentence_buffer += token

                # Stream clean spoken text to desktop display
                await manager.broadcast_to_desks({
                    "t": "text_stream",
                    "token": token,
                    "is_final": False,
                })

                # Check for action tags in real-time and execute asynchronously (zero latency impact)
                for tag_match in _TAG_RE.finditer(sentence_buffer):
                    tag_str = tag_match.group(0)
                    if tag_str not in dispatched_actions:
                        dispatched_actions.add(tag_str)
                        self._dispatch_actuator_async(tag_str)

                # Micro-chunking: as soon as natural clause or punctuation is ready, enqueue to TTS (<300ms TTFA)
                if _is_micro_chunk_ready(sentence_buffer, is_first_chunk=is_first_chunk):
                    raw_tts = clean_text_for_tts(sentence_buffer)
                    sentence_buffer = ""
                    if raw_tts:
                        is_first_chunk = False
                        verified_tts = FactVerifier.verify_and_sanitize(
                            query=transcript,
                            response=raw_tts,
                            retrieved_memories=memories,
                            is_greeting=is_greeting_persona,
                        )
                        tts_clean = clean_text_for_tts(verified_tts)
                        if tts_clean:
                            await tts_queue.put(tts_clean)

        except Exception as e:
            logger.error(f"Error during LLM stream: {e}")
            await manager.send_to_phone({"t": "eyes", "mood": "confused"})

        t_llm = time.perf_counter()
        llm_ms = (t_llm - t_llm_start) * 1000

        # Send any remaining micro-chunk to TTS queue with fact verification (NO duplicate synthesis)
        remaining_text = clean_text_for_tts(sentence_buffer)
        if remaining_text:
            verified_remaining = FactVerifier.verify_and_sanitize(
                query=transcript,
                response=remaining_text,
                retrieved_memories=memories,
                is_greeting=is_greeting_persona,
            )
            tts_clean_rem = clean_text_for_tts(verified_remaining)
            if tts_clean_rem:
                await tts_queue.put(tts_clean_rem)

        # Wait for TTS worker to finish synthesizing all queued audio
        await tts_queue.put(None)
        await tts_worker_task
        total_tts_ms = sum(tts_latencies)

        # Strict Fact Verification on full response before persistence & final broadcast
        full_response = FactVerifier.verify_and_sanitize(
            query=transcript,
            response=full_response,
            retrieved_memories=memories,
            is_greeting=is_greeting_persona,
        )

        # ── 4. Non-blocking physical motion dispatch for any remaining gestures ─────────
        self._dispatch_actuator_async(full_response)

        # Update final emotion on phone display
        emotion = _extract_emotion(full_response)
        await manager.send_to_phone({"t": "eyes", "mood": emotion})

        # ── 6. Final text token + total latency broadcast ─────────────────
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

        # ── 7. Asynchronously persist conversation to database ────────────
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

        if personality_id is not None:
            p = await self._get_personality_by_id(personality_id)
            pid = p.id if p else None
            sys_prompt = p.system_prompt if p else None
        else:
            pid, sys_prompt = await self._get_active_personality()

        # 0. Smart Fast-Path In-Memory Cache (<5ms response for greetings/identity)
        fast_result = EgyptianFastPathCache.match(text, personality_id=pid)
        if fast_result is not None:
            fast_reply, fast_emotion = fast_result
            total_ms = (time.perf_counter() - t_start) * 1000
            logger.info(f"⚡ Fast-Path process_text match in {total_ms:.1f}ms: '{text}' -> '{fast_reply}'")
            if broadcast_to_clients:
                await manager.broadcast_to_desks({
                    "t": "text_stream",
                    "token": fast_reply,
                    "is_final": True,
                    "response": fast_reply,
                    "latency": {"llm_ms": 0, "total_ms": round(total_ms)},
                })
                await manager.send_to_phone({"t": "eyes", "mood": fast_emotion})
            self._dispatch_actuator_async(fast_reply)
            audio_bytes = await self._synthesize_and_dispatch_audio(fast_reply, pid, broadcast_to_clients)
            asyncio.create_task(
                self._record_turn(
                    session_id=session_id,
                    user_text=text,
                    assistant_text=fast_reply,
                    emotion=fast_emotion,
                    llm_ms=0.0,
                    total_ms=total_ms,
                    personality_id=pid,
                )
            )
            return {
                "session_id": session_id,
                "response": fast_reply,
                "retrieved_memories": [],
                "personality_id": pid,
                "audio_bytes": audio_bytes,
            }

        # 1. Full Grounding Context & RAG retrieval
        grounding = None
        try:
            async with AsyncSessionLocal() as db:
                sys_prompt, memories, grounding, pid = await build_grounding_context(
                    db=db,
                    personality_id=pid,
                    message=text,
                )
        except Exception as e:
            logger.warning(f"Could not build grounding context in process_text: {e}")
            memories = await self._rag.retrieve(text, personality_id=pid)

        # Broadcast RAG & Visual telemetry to desktop screens
        if broadcast_to_clients and grounding and getattr(grounding, "faces", None):
            photo_url = grounding.faces.get("photo_url")
            rag_person_name = grounding.faces.get("active_person")
            await manager.broadcast_to_desks({
                "t": "rag_telemetry",
                "query": text,
                "detected_person": rag_person_name,
                "person_photo_url": photo_url,
                "memories_count": len(memories),
                "memories": memories,
            })
            if photo_url and (grounding.faces.get("is_photo_inquiry") or grounding.faces.get("currently_detected")):
                await manager.broadcast_to_desks({
                    "t": "screen_action",
                    "action": "show_person_photo",
                    "name": rag_person_name,
                    "url": photo_url,
                })

        # Strict Zero-Hallucination Guardrail
        is_ar = bool(re.search(r"[؀-ۿ]", text))
        refusal_reply = "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]" if is_ar else "I do not have this information recorded in my memory. [wave]"
        has_memories = bool(memories)
        is_greeting_persona = is_greeting_or_persona_inquiry(text)

        if not has_memories and not is_greeting_persona:
            full_response = refusal_reply
            emotion = "wave"
            total_ms = (time.perf_counter() - t_start) * 1000
            if broadcast_to_clients:
                await manager.broadcast_to_desks({
                    "t": "text_stream",
                    "token": full_response,
                    "is_final": True,
                    "response": full_response,
                    "latency": {"llm_ms": 0, "total_ms": round(total_ms)},
                })
                await manager.send_to_phone({"t": "eyes", "mood": emotion})
            self._dispatch_actuator_async(full_response)
            audio_bytes = await self._synthesize_and_dispatch_audio(full_response, pid, broadcast_to_clients)
            asyncio.create_task(
                self._record_turn(
                    session_id=session_id,
                    user_text=text,
                    assistant_text=full_response,
                    emotion=emotion,
                    llm_ms=0.0,
                    total_ms=total_ms,
                    personality_id=pid,
                )
            )
            return {
                "session_id": session_id,
                "response": full_response,
                "retrieved_memories": [],
                "personality_id": pid,
                "audio_bytes": audio_bytes,
            }

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

        # Strict Fact Verification against retrieved memories (No Fallback Model)
        full_response = self._rag.verify_response(text, full_response, memories)
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

        # Physical motion dispatch
        self._dispatch_actuator_async(full_response)

        # Voice Synthesis & Delivery via VoiceCloneService (No Fallback Model)
        audio_bytes = await self._synthesize_and_dispatch_audio(full_response, pid, broadcast_to_clients)

        # Save turn to DB
        asyncio.create_task(
            self._record_turn(
                session_id=session_id,
                user_text=text,
                assistant_text=full_response,
                emotion=emotion,
                llm_ms=llm_ms,
                total_ms=total_ms,
                personality_id=pid,
            )
        )

        return {
            "session_id": session_id,
            "response": full_response,
            "retrieved_memories": memories,
            "personality_id": pid,
            "emotion": emotion,
            "audio_bytes": audio_bytes,
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
        Yields dicts with {"type": "context", ...}, {"type": "token", "content": "..."}, then {"type": "done", ...}.
        """
        session_id = session_id or f"stream-{uuid.uuid4().hex[:8]}"

        if personality_id is not None:
            p = await self._get_personality_by_id(personality_id)
            pid = p.id if p else None
            sys_prompt = p.system_prompt if p else None
        else:
            pid, sys_prompt = await self._get_active_personality()

        # 1. Retrieve RAG memories
        memories = await self._rag.retrieve(text, personality_id=pid)
        yield {
            "type": "context",
            "memories": memories,
            "personality_id": pid,
        }

        # Strict Zero-Hallucination Guardrail (sub-10ms short-circuit, zero fallback model)
        is_ar = bool(re.search(r"[؀-ۿ]", text))
        refusal_reply = "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]" if is_ar else "I do not have this information recorded in my memory. [wave]"
        has_memories = bool(memories)
        is_greeting_persona = is_greeting_or_persona_inquiry(text)

        if not has_memories and not is_greeting_persona:
            full_response = refusal_reply
            emotion = "wave"
            yield {
                "type": "token",
                "content": full_response,
            }
            asyncio.create_task(
                self._record_turn(
                    session_id=session_id,
                    user_text=text,
                    assistant_text=full_response,
                    emotion=emotion,
                    llm_ms=0.0,
                    total_ms=0.0,
                    personality_id=pid,
                )
            )
            yield {
                "type": "done",
                "session_id": session_id,
                "response": full_response,
                "emotion": emotion,
                "llm_ms": 0.0,
            }
            return

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
        full_response = self._rag.verify_response(text, full_response, memories, is_greeting=is_greeting_persona)
        emotion = _extract_emotion(full_response)

        asyncio.create_task(
            self._record_turn(
                session_id=session_id,
                user_text=text,
                assistant_text=full_response,
                emotion=emotion,
                llm_ms=llm_ms,
                total_ms=llm_ms,
                personality_id=pid,
            )
        )

        yield {
            "type": "done",
            "session_id": session_id,
            "response": full_response,
            "emotion": emotion,
            "llm_ms": round(llm_ms, 2),
        }

    async def _get_personality_by_id(self, pid: int) -> Optional[Personality]:
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
        personality_id: int | None = None,
    ) -> None:
        try:
            async with AsyncSessionLocal() as session:
                r = await session.execute(
                    select(Conversation).where(Conversation.session_id == session_id)
                )
                conv = r.scalars().first()
                if not conv:
                    conv = Conversation(personality_id=personality_id, session_id=session_id)
                    session.add(conv)
                    await session.flush()

                u_msg = Message(
                    conversation_id=conv.id,
                    role="user",
                    content=user_text,
                    stt_latency_ms=round(stt_ms, 2) if stt_ms is not None else None,
                )
                a_msg = Message(
                    conversation_id=conv.id,
                    role="assistant",
                    content=assistant_text,
                    emotion=emotion,
                    llm_latency_ms=round(llm_ms, 2) if llm_ms is not None else None,
                    tts_latency_ms=round(tts_ms, 2) if tts_ms is not None else None,
                    total_latency_ms=round(total_ms, 2) if total_ms is not None else None,
                )
                session.add_all([u_msg, a_msg])
                await session.commit()
        except Exception as e:
            logger.warning(f"Could not persist conversation turn to DB: {e}")

    async def _get_latest_device_telemetry(self) -> dict[str, Any] | None:
        try:
            from app.models.device import Device
            async with AsyncSessionLocal() as session:
                r = await session.execute(
                    select(Device).where(Device.is_connected == True).order_by(Device.last_seen.desc()).limit(1)  # noqa: E712
                )
                dev = r.scalars().first()
                if dev:
                    state: dict[str, Any] = {}
                    if dev.device_type:
                        state["device_type"] = dev.device_type
                    if dev.battery_voltage is not None:
                        state["battery_voltage"] = dev.battery_voltage
                    if dev.distance_cm is not None:
                        state["distance_cm"] = dev.distance_cm
                    return state if state else None
        except Exception as e:
            logger.debug(f"Could not load device telemetry: {e}")
        return None

    async def _generate_tts(self, text: str, personality_id: Optional[int]) -> bytes:
        """Synthesize text strictly using the cloned voice of the personality."""
        from app.services.voice_clone.voice_clone_service import VoiceCloneService
        return await VoiceCloneService.get_instance().synthesize(
            text=text,
            personality_id=personality_id,
        )

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
            logger.warning(f"Failed to persist conversation turn to DB: {e}")

    async def process_chat_message(self, text: str) -> None:
        """Process incoming text message from websocket phone/desktop with millisecond latency."""
        await self.process_text(text, broadcast_to_clients=True)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _is_end_of_utterance(buffer: bytearray, min_bytes: int = 8000) -> bool:
    """
    Simplified VAD: considers silence if buffer is large enough.
    Replace with proper WebRTC VAD in production.
    """
    return len(buffer) >= min_bytes


def _is_sentence_end(text: str) -> bool:
    # Ensure any opening gesture bracket is closed before splitting sentence
    if text.count("[") > text.count("]"):
        return False
    stripped = text.strip()
    stripped_no_tags = _TAG_RE.sub("", stripped).strip()
    if not stripped_no_tags:
        return False
    return any(stripped_no_tags.endswith(p) for p in (".", "!", "?", "؟", "،", "\n"))




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
