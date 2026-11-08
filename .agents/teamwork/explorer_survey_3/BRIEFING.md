# BRIEFING — 2026-11-02T22:28:00Z

## Mission
Survey the entire codebase to inventory all project documentation, frontend UI text, backend user-facing strings, and AI persona prompts requiring unification to Egyptian Arabic (`arz`).

## 🔒 My Identity
- Archetype: explorer
- Roles: Language Unification Explorer (arz)
- Working directory: c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_3\
- Original parent: f2243747-929d-4819-801b-dbe3972e0c1b
- Milestone: codebase-survey

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Scope: Documentation, frontend UI, backend user-facing strings, AI system prompts and personas
- Target dialect: authentic Egyptian Arabic (`arz`)

## Current Parent
- Conversation ID: f2243747-929d-4819-801b-dbe3972e0c1b
- Updated: not yet

## Investigation State
- **Explored paths**:
  - Documentation: `README.md`, `read me/nebula_architecture.md`, `nebula-frontend-main/README.md`, `nebula-frontend-main/nebulla/README.md`
  - Frontend UI: Flutter app (`screens/*.dart`, `widgets/common_widgets.dart`, `services/nebula_repository.dart`), web templates (`app/templates/chat_ui.html`, `app/static/faces_studio.html`)
  - Backend API: `app/auth/router.py`, `app/auth/jwt.py`, `app/auth/schemas.py`, `app/api/v1/endpoints/*.py` (14 endpoint modules), `app/core/security.py`, `app/main.py`
  - AI System Prompts & Modelfiles: `app/services/ai/context_builder.py`, `app/services/ai/pipeline.py`, `Modelfile.nebula-*`, `app/db/session.py` (seed data), `scripts/generate_rag_dataset.py`
- **Key findings**:
  - Found extensive mixed usage of English and Modern Standard Arabic (MSA / الفصحى) across all four domains.
  - Project documentation is currently 100% in English.
  - Flutter UI and auth endpoints use formal MSA or English errors rather than authentic Egyptian Arabic (`arz`).
  - Context builder and Modelfiles have English system prompts and English fallback branches which need to be strictly unified to Egyptian Arabic (`arz`) with strict zero-hallucination RAG grounding.
- **Unexplored areas**: None, full codebase scan completed.

## Key Decisions Made
- Catalog exact files, line ranges, current strings, and authentic Egyptian Arabic (`arz`) replacement translations.
- Establish comprehensive linguistic transformation guidelines for Egyptian Arabic (`arz`) specifically tailored for human-robot conversational interaction and control interfaces.

## Artifact Index
- DISPATCH.md — Dispatch instructions
- BRIEFING.md — Working memory
- progress.md — Liveness heartbeat
- survey_report.md — Comprehensive language survey report
- handoff.md — 5-component handoff report
