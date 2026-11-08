# Dispatch: Worker M4 Tests (Milestone 4 — Automated Test Suite & Test Execution)

## Objective
Implement comprehensive automated unit tests for `context_builder.py` in `tests/unit/test_context_builder.py`, verify integration tests for auth in `tests/integration/test_user_auth_endpoints.py`, and run the automated test suite to verify 100% pass across all components (Requirement R1, R2, R3 & Verification Acceptance Criteria).

## Scope Boundaries & Exclusive File Ownership
You exclusively own and may edit:
1. `c:\Users\L0Q\Desktop\graduation project\tests\unit\test_context_builder.py` (new file)
2. `c:\Users\L0Q\Desktop\graduation project\tests\integration\test_user_auth_endpoints.py` (if any additional edge-case tests are needed)

Do NOT modify production source code unless an explicit bug is found in tests.

## Mandatory References
1. Verbatim User Requirements: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\ORIGINAL_REQUEST.md`
2. Project Blueprint: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\PROJECT.md`
3. Explorer 2 Detailed Test Specification: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\survey_report.md` (Section 6)

## Test Specifications to Implement in `tests/unit/test_context_builder.py`
Implement 6 comprehensive async unit tests using pytest:
1. `test_context_builder_grounded_with_memories`: Tests prompt assembly when memories are returned. Asserts `سياق الذاكرة المعتمدة`, `[المصدر 1]`, `Strict RAG Grounding`, absence of English text, presence of system status block (`معلومات النظام والسياق النشط:`).
2. `test_context_builder_empty_memories_refusal`: Tests prompt assembly when no memories exist. Asserts `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`, presence of system status block.
3. `test_context_builder_greeting_and_persona`: Tests prompt assembly for greetings ("صباح الخير", "أنت مين"). Asserts welcoming Egyptian response guidance and presence of robot and creator names.
4. `test_context_builder_vision_and_screen_awareness`: Tests camera face profile and screen photo formatting. Asserts camera face profile line, photo URL line, and screen awareness directives.
5. `test_context_builder_hardware_diagnostics_integration`: Tests phone, desktop, and ESP32 states formatting in system status block.
6. `test_context_builder_negative_grounding_directives`: Tests strict anti-hallucination rules for unrecorded details (explicit prohibition against guessing phone numbers and passwords).

## Execution & Verification
Run the test suites using `pytest`:
- `pytest tests/unit/test_context_builder.py`
- `pytest tests/integration/test_user_auth_endpoints.py`
- `pytest tests/integration/test_chat_endpoint.py`
Document the commands, outputs, and results in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m4_tests\changes.md` and `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m4_tests\handoff.md`.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.


## 2026-11-03T00:25:56Z
[Message] timestamp=2026-11-03T00:25:56Z sender=f2243747-929d-4819-801b-dbe3972e0c1b priority=MESSAGE_PRIORITY_HIGH content=You are Worker M4 Tests (Test Suite Implementation & Verification Worker).
Your working directory is: c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m4_tests\
Read `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\ORIGINAL_REQUEST.md`, `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\PROJECT.md`, and `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m4_tests\DISPATCH.md`.
Read Explorer 2's test design at `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\survey_report.md` (Section 6).

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Implement:
1. Create `tests/unit/test_context_builder.py` covering the 6 specified async test cases (grounded with memories, empty memories refusal, greeting/persona, vision/screen awareness, hardware diagnostics, and negative grounding directives).
2. Run pytest on:
   - `pytest tests/unit/test_context_builder.py`
   - `pytest tests/integration/test_user_auth_endpoints.py`
   - `pytest tests/integration/test_chat_endpoint.py`
3. Document all test results in `changes.md` and `handoff.md`.
When finished, send a message to your parent orchestrator.
