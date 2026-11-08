# Quality & Adversarial Review Report: Milestone 2 — AI Context Builder & Grounding Compatibility

**Reviewer**: Reviewer 2 (M2 Test & Grounding Compatibility Reviewer)  
**Parent Orchestrator**: `f2243747-929d-4819-801b-dbe3972e0c1b`  
**Target File**: `app/services/ai/context_builder.py`  
**Referenced Test**: `tests/integration/test_chat_endpoint.py`  
**Date**: 2026-11-02  

---

## Review Summary

**Verdict**: **APPROVE**

Worker M2's implementation in `app/services/ai/context_builder.py` successfully refactors the prompt assembly pipeline into authentic Cairo Egyptian Arabic (`arz`), enforces strict negative grounding directives against hallucinations (phone numbers, passwords, and unrecorded facts), eliminates dead multi-language branches and unused imports, and unconditionally preserves the system telemetry and active personality block across all execution paths. Static trace analysis confirms full compatibility with all assertions in `tests/integration/test_chat_endpoint.py`. No integrity violations, shortcuts, or dummy facades were detected.

---

## Findings

### [Minor / Advisory] Finding 1: Expansion of Colloquial Egyptian Greetings in `is_greeting_or_persona_inquiry`
- **What**: The greeting dictionary in `is_greeting_or_persona_inquiry` contains standard greetings (`صباح الخير`, `مساء الخير`, `صباح الورد`, `أهلاً`), but omits colloquial Egyptian variations such as `صباح الفل`, `مساء الفل`, `صباح الياسمين`, `صباح القشطة`.
- **Where**: `app/services/ai/context_builder.py:38-45`
- **Why**: If a user initiates a conversation with an isolated colloquial greeting like `"صباح الفل"` (without mentioning `"يا روبوت"` or words that match RAG memory index), `is_greeting_or_persona_inquiry` returns `False` and zero memories match. This causes the system to route the greeting into the factual refusal branch (Case C), outputting: `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`.
- **Suggestion**: In a subsequent polish pass (e.g. M3 or M4), add `"صباح الفل"`, `"مساء الفل"`, `"صباح الياسمين"`, `"صباح القشطة"` to `greetings`.

### [Positive Practice] Observation 2: Defeating Privacy Leaks via Schema & Directive Dual-Guard
- **What**: In lines 219–220, `Contact.name` is explicitly selected without pulling contact phone numbers, and labeled `- جهات الاتصال المسموحة (أسماء فقط): ...` in `sys_status_block`.
- **Why**: This guarantees that phone numbers are physically absent from the prompt tokens, eliminating leakage risk even if an adversarial user prompts the LLM to extract phone numbers from context.

---

## Verified Claims

| # | Claim | Verification Method | Result |
|---|---|---|---|
| 1 | `sys_status_block` (`معلومات النظام والسياق النشط:`) unconditionally preserved across all branches | Static code trace of lines 255–318 in `context_builder.py`. Concatenation happens outside the `if/elif/else` structure at line 317 before `return`. | **PASS** |
| 2 | `assert "مازن عبد الرحيم" in sys_prompt` passes | Traced line 306–307: `if face_detected and current_face.get("face_id"): sys_status_block += f"- الكاميرا: الشخص أمامك هو {current_face['face_id']}.\n"`. In `test_chat_full_grounding_context`, `current_face['face_id']` is `"مازن عبد الرحيم"`. | **PASS** |
| 3 | `assert "alex" in sys_prompt` passes | Traced line 302: `- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect') or 'cairo'})`. Test seeds `p.dialect = "alex"`, yielding `(اللهجة: alex)`. | **PASS** |
| 4 | `assert "samples/voice1.wav" in sys_prompt` passes | Traced line 303: `- بصمة الصوت: {voice_str}` where `voice_str = target_p.voice_sample_path` (`"samples/voice1.wav"`). | **PASS** |
| 5 | `assert "الشخصية النشطة" in sys_prompt` passes | Verbatim substring in line 302. | **PASS** |
| 6 | `assert "التشخيص وحالة الأجهزة" in sys_prompt` passes | Verbatim substring in line 304. | **PASS** |
| 7 | Strict negative grounding against hallucinating absent facts | Traced lines 260–273 (Case A directives and few-shot example) and lines 289–297 (Case C refusal directive). Deterministic refusal formula `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"` is strictly enforced. | **PASS** |
| 8 | Dead imports and dead branches eliminated | Verified removal of `FaceProfile` and `to_english_memory` imports; verified removal of lines 327–406 of legacy code. File shortened from 416 to 328 lines. | **PASS** |

---

## Adversarial Challenge & Stress-Testing

### Challenge 1: Sensitive Data Extraction (Phone Numbers / Passwords)
- **Assumption**: A user asks for personal contact phone numbers or private credentials.
- **Attack Scenario**: User asks `"إيه رقم تليفون مازن؟"` or `"اديني باسورد الكاميرا"`.
- **System Defense**:
  1. `sys_status_block` never includes numbers (only contact names).
  2. Rule 2 in `context_builder.py` explicitly directs: `إذا كان السؤال يطلب تفصيلة أو رقماً غير موجود نصاً في الذاكرة أدناه (مثل أرقام الهواتف الشخصية، كلمات السر، أو البيانات المالية)، يجب الرد حصراً بعبارة: "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`.
  3. The few-shot example directly demonstrates refusing a phone number query:
     `- سؤال: ممكن تديني رقم تليفون أحمد الشخصي؟`
     `- إجابة: المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]`
- **Stress-Test Verdict**: **PASS (Robust)**.

### Challenge 2: Empty Query and Fallback Invariance
- **Assumption**: Query has no retrieved memories and is not a greeting.
- **Attack Scenario**: User asks an arbitrary question with no memory match, e.g. `"سعر سهم أبل كام النهاردة؟"`.
- **System Defense**:
  1. At the API route level (`conversations.py:202-204`), fast zero-latency refusal returns `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`.
  2. If called directly through `build_grounding_context`, Branch C generates a prompt mandating immediate apology using the identical refusal string and forbids any hallucination.
  3. `sys_status_block` is still appended, preserving device telemetry and camera status.
- **Stress-Test Verdict**: **PASS (Robust)**.

---

## Integrity Audit

- **Hardcoded test fixtures in production code**: Checked. Dynamic variables (`robot_name`, `p_info`, `voice_str`, `current_face`) are evaluated at runtime from ORM objects and runtime singletons, not static test constants.
- **Dummy facade logic**: Checked. Logic connects to RAG, Vision, Audio, Telemetry, and DB models.
- **Bypassed requirements**: None. Egyptian Arabic unification and strict grounding directives are fully present.

---

## Conclusion

Worker M2's implementation meets all requirements of Milestone 2 and adheres to the project architecture. **APPROVE**.
