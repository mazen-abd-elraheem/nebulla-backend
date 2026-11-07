# BRIEFING — 2026-11-02T22:21:00Z

## Mission
Investigate and survey AI context building, RAG memory grounding, Egyptian Arabic (`arz`) system prompts, and test coverage to guide R3 implementation.

## 🔒 My Identity
- Archetype: explorer
- Roles: AI Context & RAG Explorer, Investigator, Synthesizer
- Working directory: c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2
- Original parent: f2243747-929d-4819-801b-dbe3972e0c1b
- Milestone: survey

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Strictly focus on AI context builder, RAG memory grounding, arz system prompts, and relevant testing
- User global rule: do not use python injection just directly edit the file, make sure path is right as inside project terminal

## Current Parent
- Conversation ID: f2243747-929d-4819-801b-dbe3972e0c1b
- Updated: 2026-11-02T22:09:07Z

## Investigation State
- **Explored paths**:
  - `app/services/ai/context_builder.py`
  - `app/services/ai/pipeline.py`
  - `app/api/v1/endpoints/conversations.py`
  - `app/services/memory/rag_service.py`
  - `app/services/memory/fact_verifier.py`
  - `app/services/memory/person_retriever.py`
  - `app/providers/llm/local_ollama.py`
  - `app/providers/llm/huggingface_provider.py`
  - `app/providers/llm/prompt_builder.py`
  - `app/providers/llm/base.py`
  - `app/core/config.py`
  - `app/utils/masri_normalizer.py`
  - `tests/unit/test_rag_llm.py`
  - `tests/unit/test_multimodal_rag_extensions.py`
  - `tests/unit/test_llm_pipeline.py`
  - `tests/integration/test_chat_endpoint.py`
  - `tests/integration/test_rag_chat_api.py`
  - `scripts/test_nile_rag.py`
  - `scripts/test_rag_hallucination.py`
  - `scripts/test_grounding_live.py`
- **Key findings**:
  - `context_builder.py` has disjointed prompt formatting, duplicated English/Arabic code blocks, and imports scripts at runtime.
  - When memories are present, the current prompt lacks negative constraints for unmentioned details and omits hardware/device diagnostics.
  - Zero dedicated unit tests exist for `context_builder.py` (`tests/unit/test_context_builder.py` is missing).
  - In `test_chat_endpoint.py`, assertions require specific substrings: `"مازن عبد الرحيم"`, `"alex"`, `"samples/voice1.wav"`, `"الشخصية النشطة"`, `"التشخيص وحالة الأجهزة"`. The new prompt must preserve these.
  - Fast refusal shortcut and `FactVerifier` both use `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"` as the standard refusal phrase in Masri.
- **Unexplored areas**: None for survey scope.

## Key Decisions Made
- Structure detailed enhancement plan for `context_builder.py` focusing on unified Egyptian Arabic (`arz`), strict negative RAG grounding, zero-hallucination directives, and preserving backward compatibility with `test_chat_endpoint.py`.
- Recommend creating `tests/unit/test_context_builder.py` with 6 exhaustive test cases covering all grounding conditions and edge cases.

## Artifact Index
- DISPATCH.md — incoming dispatch instructions
- BRIEFING.md — persistent working memory
- progress.md — liveness heartbeat
- survey_report.md — detailed survey report with exact lines, design, prompt text, and test specifications
- handoff.md — 5-component handoff report
