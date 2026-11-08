# Handoff Report: AI Context Builder & Strict RAG Memory Grounding in Egyptian Arabic (`arz`)

**Agent**: Explorer 2 (AI Context & RAG Explorer)  
**Parent Orchestrator**: `f2243747-929d-4819-801b-dbe3972e0c1b`  
**Date**: 2026-11-02  
**Working Directory**: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\`  
**Report Artifact**: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\survey_report.md`

---

## 1. Observation

1. **Current Code in `app/services/ai/context_builder.py`**:
   - Lines 255–406 define prompt assembly with disjointed logic.
   - Lines 327–366 define an English block that is immediately followed by duplicate Arabic snippets and then overwritten completely at line 369 with `grounded_system_prompt = f"""You are "{robot_name}"...`.
   - Lines 329 and 368 import from a non-production script: `from scripts.generate_rag_dataset import to_english_memory`.
   - When memories are retrieved (`if memories:` at line 257), the prompt sets a brief prompt without negative grounding rules (no instruction on how to handle queries asking for details absent from memory) and omits the system diagnostic status block (`معلومات النظام والسياق النشط:`).
   - Only when memories are empty and non-greeting (`else: else:` at lines 289–316) is the system context block containing `"الشخصية النشطة"` and `"التشخيص وحالة الأجهزة"` emitted.
2. **Integration Test Assertions**:
   - `tests/integration/test_chat_endpoint.py`, lines 150–157:
     ```python
     call_kwargs = mock_gen.call_args[1]
     sys_prompt = call_kwargs.get("system_prompt", "")
     assert "مازن عبد الرحيم" in sys_prompt
     assert "alex" in sys_prompt
     assert "samples/voice1.wav" in sys_prompt
     assert "الشخصية النشطة" in sys_prompt
     assert "التشخيص وحالة الأجهزة" in sys_prompt
     ```
   - If `"الشخصية النشطة"` or `"التشخيص وحالة الأجهزة"` is missing from the system prompt when memories are retrieved, or if persona/dialect/voice sample fields change format unexpectedly, this test breaks.
3. **RAG Pipeline & Providers**:
   - `app/services/ai/pipeline.py` (lines 212 & 418) calls `build_grounding_context(db=..., personality_id=..., message=...)`.
   - `app/api/v1/endpoints/conversations.py` (lines 149 & 368) calls `build_grounding_context(...)`.
   - `app/providers/llm/local_ollama.py` (line 56) and `app/providers/llm/huggingface_provider.py` (line 98) search for `"الذاكرة"` or `"ذكريات"` in `effective_system_prompt` to prevent duplicating context.
   - `app/services/memory/fact_verifier.py` (line 26) uses `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"` as the canonical refusal phrase.
4. **Test Suite Status**:
   - `tests/unit/test_rag_llm.py` tests `app/providers/llm/prompt_builder.py`, but does not test `context_builder.py`.
   - Zero test files exist for `context_builder.py` (`tests/unit/test_context_builder.py` is absent).

---

## 2. Logic Chain

1. **Premise 1**: Requirement R1 requires project-wide language unification to Egyptian Arabic (`arz`), and R3 requires enhancing `context_builder.py` with an Egyptian Arabic system prompt strictly grounding the local LLM to RAG memories and forbidding hallucinated/assumed memories outside retrieved RAG.
2. **Premise 2**: Observation 1 shows that `context_builder.py` currently contains dead English code branches, broken duplicate Arabic snippets, and an runtime import from `scripts/generate_rag_dataset.py`.
3. **Premise 3**: Observation 1 also shows that when memories are retrieved, the prompt lacks negative constraints: if a user asks a query combining a known memory with an unknown detail (e.g., asking for an unrecorded phone number), the LLM is not instructed to refuse the unrecorded part.
4. **Premise 4**: Observation 2 proves that `tests/integration/test_chat_endpoint.py` strictly relies on `"الشخصية النشطة"` and `"التشخيص وحالة الأجهزة"` appearing in `system_prompt`.
5. **Deduction**: Therefore, `build_grounding_context` must be refactored into clean, unified Egyptian Arabic (`arz`) where:
   - All English fallback templates and script imports are removed.
   - Both the memory-grounded branch (`if memories:`) and the empty-memory branch enforce the exact refusal instruction: `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`.
   - Negative grounding directives explicitly forbid inventing phone numbers, passwords, or personal details not in memory.
   - The system status block (`معلومات النظام والسياق النشط:`) is included unconditionally across all branches to guarantee complete backwards compatibility with `tests/integration/test_chat_endpoint.py`.
   - A dedicated unit test suite `tests/unit/test_context_builder.py` must be added to provide direct verification.

---

## 3. Caveats

1. **Hardware / Model Execution**: In the test environment, Ollama or local LLM weights may not be running or GPU-accelerated. Tests should utilize mock LLM providers (e.g. `provider="mock"`) or unit test `build_grounding_context` directly without invoking live network models.
2. **Scope Boundary**: This survey covers AI context builder, RAG grounding, and prompt design (R3). User registration, login endpoints, and JWT authentication (R2) are handled by Explorer 1.

---

## 4. Conclusion

The design for enhancing `app/services/ai/context_builder.py` is fully specified in `survey_report.md`:
1. Refactor `build_grounding_context` to unify all prompt generation in Egyptian Arabic (`arz`).
2. Add explicit anti-hallucination, negative grounding directives, and TTS-safe guidelines (one/two concise sentences, mandatory emotion tag `[happy]`/`[wave]`/`[like]`).
3. Retain the canonical refusal string: `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`.
4. Ensure the system status block (`معلومات النظام والسياق النشط:`) is consistently included in all prompt variations.
5. Create `tests/unit/test_context_builder.py` covering all 6 test cases detailed in Section 6.2 of `survey_report.md`.

---

## 5. Verification Method

1. **File Inspection**:
   - Inspect `app/services/ai/context_builder.py` lines 255–416 to verify all prompt branches are written in Egyptian Arabic (`arz`), script imports are eliminated, and negative constraints are in place.
2. **Automated Unit Tests**:
   - Run `pytest tests/unit/test_context_builder.py -v` (once implemented) to verify:
     - Memory grounding formatting
     - Empty memory refusal formatting
     - Greeting and persona handling
     - Hardware & vision telemetry formatting
     - Strict refusal on unrecorded queries
3. **Existing Integration Tests**:
   - Run `pytest tests/integration/test_chat_endpoint.py -v` to ensure zero regression on existing chat endpoint and system prompt assertions.
4. **Invalidation Conditions**:
   - If `test_chat_endpoint.py` fails due to missing `"الشخصية النشطة"` or `"التشخيص وحالة الأجهزة"`.
   - If any English prompt strings remain in `context_builder.py`.
