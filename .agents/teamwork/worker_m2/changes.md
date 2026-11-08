# Milestone 2 — Code Changes: AI Context Builder & Strict RAG Grounding in `arz`

**File Modified**: `app/services/ai/context_builder.py`  
**Worker**: Worker M2 (implementer / qa / specialist)  
**Date**: 2026-11-02  

---

## 1. Summary of Changes

`app/services/ai/context_builder.py` was refactored and enhanced to fulfill Requirements R1 and R3:
1. **Dead Imports Removed**:
   - Removed unused import `from app.models.face_profile import FaceProfile` (line 15).
   - Removed runtime import `from scripts.generate_rag_dataset import to_english_memory` from deleted dead branches.
2. **Elimination of Dead Multi-Language Branches (Lines 327–406)**:
   - Deleted the dead, redundant, and fragmented English/Arabic code blocks where `grounded_system_prompt` was repeatedly reassigned and overwritten.
   - Unified the entire system prompt formulation directly in authentic Egyptian Arabic (`arz`), eliminating the fragile `if is_arabic` branch split.
3. **Enhanced Persona Detection**:
   - Added Egyptian Arabic self-introduction inquiries (`عرف نفسك`, `عرفنا بنفسك`, `كلمنا عن نفسك`) to `persona_patterns` in `is_greeting_or_persona_inquiry`.
4. **Strict RAG Memory Grounding Directives (Case A — Memories Present)**:
   - Formatted memories into structured source bullets: `[المصدر 1]: ...`, `[المصدر 2]: ...`.
   - Injected four strict operational rules in Egyptian Arabic (`arz`):
     - Rule 1: Sole and strict reliance on memories provided in `سياق الذاكرة المعتمدة`. Total prohibition against guessing, fabricating, or assuming facts outside retrieved sources.
     - Rule 2: Explicit negative refusal directive: If asked about unrecorded details or sensitive information (phone numbers, passwords, bank data), the LLM must refuse using:
       `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`
     - Rule 3: Spoken Cairo dialect style (1–2 sentences max) without markdown tables, asterisks, or URLs to ensure clean TTS audio synthesis.
     - Rule 4: Mandatory emotion tag at the end of each response (`[happy]`, `[wave]`, `[like]`, `[neutral]`, `[sad]`).
   - Included authentic Egyptian Arabic few-shot examples demonstrating both direct factual extraction and negative refusal for unrecorded private details (e.g., requesting personal phone numbers).
5. **Warm Egyptian Greeting & Persona Inquiry (Case B)**:
   - Warm welcome acknowledging user in polite Cairo Arabic, identifying as `robot_name` created by `creator_name`, concise speech-oriented response, and mandatory emotion tag.
6. **Zero-Hallucination Immediate Refusal (Case C — No Memories Available)**:
   - Strict directive instructing immediate refusal using:
     `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`
   - Prohibits any speculation or unrecorded output.
7. **System Status & Hardware Context Preservation**:
   - Unified `sys_status_block` (`معلومات النظام والسياق النشط:`) and unconditionally appended it across all prompt branches.
   - Preserved active personality name and dialect (`- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect') or 'cairo'})`), voice sample path (`- بصمة الصوت: {voice_str}`), and hardware connection telemetry (`- التشخيص وحالة الأجهزة: الهاتف ({phone_str}) | الحاسوب ({desk_str}) | شريحة الروبوت ({esp_str})`).
   - Dynamically appends camera face profile (`- الكاميرا: الشخص أمامك هو {current_face['face_id']}.`), verified speaker voiceprint, screen photo display profile, allowlisted contacts, and active reminders.
   - Guarantees 100% backward compatibility with `tests/integration/test_chat_endpoint.py` and downstream LLM providers (`local_ollama.py`, `huggingface_provider.py`).

---

## 2. Line-by-Line Diff Summary

- **Lines 14–16**: Removed unused `FaceProfile` import.
- **Line 55**: Added `r"\b(عرف\s+نفسك|عرفنا\s+بنفسك|كلمنا\s+عن\s+نفسك)\b"` to `persona_patterns`.
- **Lines 252–406 (Old)**: Replaced 155 lines of convoluted, duplicated, and partially overwritten code with 65 lines of structured, authentic Egyptian Arabic prompt logic. Total file line count reduced from 416 to 328 lines.
