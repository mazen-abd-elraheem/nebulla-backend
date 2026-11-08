# Dispatch: Worker M2 (Milestone 2 — Context Builder Prompt Enhancement & RAG Grounding in arz)

## Objective
Enhance `c:\Users\L0Q\Desktop\graduation project\app\services\ai\context_builder.py` with comprehensive system prompts written in Egyptian Arabic (`arz`), strictly grounding the local LLM to only use memories provided via RAG and forbidding any hallucinated or assumed memories outside retrieved RAG context (Requirement R3 & R1).

## Scope Boundaries & Exclusive File Ownership
You exclusively own and may edit:
- `c:\Users\L0Q\Desktop\graduation project\app\services\ai\context_builder.py`

Do NOT edit any other file in this milestone.

## Mandatory References
1. Verbatim User Requirements: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\ORIGINAL_REQUEST.md`
2. Project Blueprint: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\PROJECT.md`
3. Explorer 2 Detailed Prompt Design & Survey Report: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\survey_report.md`
4. Language Unification (arz) Guidelines: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_3\survey_report.md`

## Detailed Implementation Requirements
1. **Clean Codebase & Eliminate Dead Branches**:
   - Remove unused/dead imports such as `from scripts.generate_rag_dataset import to_english_memory`.
   - Remove lines 327–406 which contain dead, repeated English prompt definitions and fragmented Arabic pasted into English branches.
2. **Implement Authentic Egyptian Arabic (`arz`) System Prompts**:
   - Unify the entire prompt assembly in authentic Cairo Egyptian Arabic (`arz`).
   - Implement Case A (memories present):
     - Bulleted list of memories: `[المصدر 1]: ...`, `[المصدر 2]: ...`.
     - Strict RAG grounding directives: Depend solely and strictly on memories provided in `سياق الذاكرة المعتمدة`. Forbid inventing, guessing, or assuming any events, memories, or facts outside retrieved sources.
     - Negative grounding directive: If asked about unrecorded details or sensitive data (phone numbers, passwords, financial info) not explicitly mentioned in the memories, refuse strictly using:
       `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`
     - Response style: Spoken Egyptian colloquial Arabic (1-2 sentences max), no markdown tables or asterisks, suitable for TTS.
     - Mandatory emotion tag at the end: `[happy]`, `[wave]`, `[like]`, `[neutral]`, `[sad]`.
     - Few-shot grounding examples in Egyptian Arabic illustrating direct answers and negative refusal.
   - Implement Case B (greeting or persona inquiry):
     - Warm Egyptian greeting acknowledging user, identifying as `robot_name` created by `creator_name`, concise response for TTS with emotion tag.
   - Implement Case C (no memories available):
     - Explicit refusal directive: state that no memory is recorded for this query and instruct immediate refusal with `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`.
3. **Preserve Compatibility Anchor with Tests**:
   - Ensure the system context block (`معلومات النظام والسياق النشط:`) is included in all prompt branches:
     - `- الشخصية النشطة: {robot_name} (اللهجة: {p_info.get('dialect') or 'cairo'})`
     - `- بصمة الصوت: {voice_str}`
     - `- التشخيص وحالة الأجهزة: الهاتف ({phone_str}) | الحاسوب ({desk_str}) | شريحة الروبوت ({esp_str})`
     - Plus optional camera face, verified speaker, screen photo profile, contacts, and reminders lines.
   - This ensures `tests/integration/test_chat_endpoint.py` and downstream LLM providers (`local_ollama.py`, `huggingface_provider.py`) continue to function seamlessly.
4. **User Rule**:
   - Directly edit the file using file editing tools — do NOT use python injection scripts.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Deliverable
Run tests on `tests/integration/test_chat_endpoint.py` to ensure no regression, document changes in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m2\changes.md` and handoff in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m2\handoff.md`.

## 2026-11-02T23:16:26Z
Worker M2 dispatched:
Implement Milestone 2:
1. Edit `c:\Users\L0Q\Desktop\graduation project\app\services\ai\context_builder.py` directly.
2. Clean up dead imports and dead duplicated English/Arabic code blocks (lines 327-406).
3. Unify prompts in authentic Egyptian Arabic (`arz`) with strict RAG grounding directives (sole reliance on retrieved memories, strict negative refusal with `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"` for absent or sensitive details, spoken Cairo dialect, mandatory emotion tags, few-shot grounding examples).
4. Preserve the system status context block (`معلومات النظام والسياق النشط:`) with `"الشخصية النشطة"`, `"التشخيص وحالة الأجهزة"`, etc., in all branches for test compatibility.
5. Verify changes by running `pytest tests/integration/test_chat_endpoint.py`.
Document changes in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m2\changes.md` and handoff in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m2\handoff.md`.
When finished, send a message to your parent orchestrator.
