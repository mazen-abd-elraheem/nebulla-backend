# Dispatch: Reviewer 1 (Milestone 2 — Context Builder & RAG Grounding Review)

## Objective
Independently review the Milestone 2 changes in `app/services/ai/context_builder.py` for correctness, completeness, Egyptian Arabic language quality, strict RAG grounding directives, and dead branch removal.

## Target File
`c:\Users\L0Q\Desktop\graduation project\app\services\ai\context_builder.py`

## Worker M2 Documentation
- Changes: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m2\changes.md`
- Handoff: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m2\handoff.md`

## Mandatory References
- Requirements: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\ORIGINAL_REQUEST.md`
- Project Blueprint: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\PROJECT.md`
- Explorer 2 Design: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_2\survey_report.md`

## Verification Instructions
1. Inspect `app/services/ai/context_builder.py`.
2. Verify that English prompt templates and dead code blocks (previously lines 327-406) have been removed.
3. Verify that Egyptian Arabic (`arz`) system prompts are comprehensive, authentic in Cairo colloquial style, and strictly forbid hallucinations or assuming unrecorded memories.
4. Verify standard refusal formula `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`.
5. Write your review report to `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\reviewer_m2_1\review.md` and handoff to `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\reviewer_m2_1\handoff.md` with explicit verdict: `APPROVE` or `REQUEST_CHANGES`.

## 2026-11-02T23:28:13Z
You are Reviewer 1 (M2 Context Builder Prompt Reviewer).
Your working directory is: c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\reviewer_m2_1\
Read `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\ORIGINAL_REQUEST.md`, `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\PROJECT.md`, and `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\reviewer_m2_1\DISPATCH.md`.
Read Worker M2's handoff report at `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m2\handoff.md`.
Inspect `app/services/ai/context_builder.py`.
Verify correctness, prompt structure, Egyptian Arabic fluency, strict RAG grounding directives, and dead branch elimination.
Write your review report to `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\reviewer_m2_1\review.md` and your handoff to `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\reviewer_m2_1\handoff.md` with explicit verdict: APPROVE or REQUEST_CHANGES.
When finished, send a message to your parent orchestrator.

