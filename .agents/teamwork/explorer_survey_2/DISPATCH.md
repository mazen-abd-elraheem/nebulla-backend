# Dispatch: Explorer Survey 2 (AI Context Builder & RAG Grounding)

## Objective
Survey the codebase focusing on:
1. `c:\Users\L0Q\Desktop\graduation project\app\services\ai\context_builder.py` and related AI services/modules.
2. How memory retrieval (RAG) is structured, passed, and formatted into system prompts or context.
3. Current prompts, persona instructions, and local LLM invocation patterns.
4. Detailed design for enhancing `context_builder.py` with Egyptian Arabic (`arz`) system prompt strictly grounding the local LLM to only use memories provided via RAG (forbidding hallucinated/assumed memories outside retrieved RAG).
5. Existing or needed tests for context builder prompt formatting and RAG grounding verification.

## Mandatory Reference
Read `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\ORIGINAL_REQUEST.md` before starting work.

## Deliverable
Write your detailed report to `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\survey_report.md` and complete with `handoff.md`. Include exact line ranges, prompt structure, Egyptian Arabic phrasing recommendations, and test recommendations.

## 2026-11-02T22:09:07Z
Received dispatch from orchestrator f2243747-929d-4819-801b-dbe3972e0c1b:
"You are Explorer 2 (AI Context & RAG Explorer).
Your working directory is: c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\
Read `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\ORIGINAL_REQUEST.md` and `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\DISPATCH.md`.
Survey the codebase to understand:
1. `c:\Users\L0Q\Desktop\graduation project\app\services\ai\context_builder.py` and related AI services/modules.
2. How memory retrieval (RAG) is structured, passed, and formatted into system prompts or context.
3. Current prompts, persona instructions, and local LLM invocation patterns.
4. Detailed design for enhancing `context_builder.py` with Egyptian Arabic (`arz`) system prompt strictly grounding the local LLM to only use memories provided via RAG (forbidding hallucinated/assumed memories outside retrieved RAG).
5. Existing or needed tests for context builder prompt formatting and RAG grounding verification.
Write your full findings to `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\survey_report.md` and your handoff to `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\handoff.md`.
When finished, send a message to your parent orchestrator with a summary and reference to your reports."
