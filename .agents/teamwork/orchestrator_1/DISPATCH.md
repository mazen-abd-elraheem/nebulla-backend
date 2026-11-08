# Dispatch Log

## 2026-11-02T22:07:17Z
Unify languages across the entire project (including documentation and frontend/backend strings) to Egyptian Arabic (arz), implement production-ready user registration and login API endpoints with JWT authentication and password hashing, and enhance `context_builder.py` with a detailed prompt in arz strictly grounding the local LLM to only use memories provided via RAG.

Integrity mode: development

## Requirements

### R1. Project-Wide Language Unification (arz)
Unify languages across the entire project to Egyptian Arabic (`arz`), covering project documentation, frontend user-facing strings, backend API messages and responses, and AI system prompts and personas.

### R2. User Registration and Login API Endpoints
Implement API endpoints for user registration and user login using username or email and password authentication. The endpoints must securely hash passwords and issue JSON Web Tokens (JWT) upon successful authentication.

### R3. Context Builder Prompt Enhancement & Local LLM Memory Grounding
In `c:\Users\L0Q\Desktop\graduation project\app\services\ai\context_builder.py`, expand the prompt with detailed instructions written in Egyptian Arabic (`arz`). Enforce strict prompt directives ensuring that the local LLM relies solely on retrieved RAG context and does not generate, hallucinate, or assume any memories outside what RAG provides.

## Acceptance Criteria

### Language Unification
- [ ] User-facing strings in frontend components, backend API responses, prompts, and documentation are unified to Egyptian Arabic (`arz`).
- [ ] No untranslated or mixed default language strings remain in user-facing workflows where Egyptian Arabic (`arz`) is required.

### Authentication Endpoints
- [ ] User registration endpoint accepts valid credentials (username/email and password), hashes passwords securely, and registers new accounts.
- [ ] User login endpoint validates credentials and returns a valid JWT access token for authenticated users.
- [ ] Registration and login endpoints reject invalid payloads or incorrect credentials with appropriate HTTP status codes and error messages.

### Context Builder & RAG Grounding
- [ ] The system prompt in `app/services/ai/context_builder.py` is comprehensive, detailed, and written in Egyptian Arabic (`arz`).
- [ ] The prompt contains strict directives forbidding the local LLM from generating or hallucinating memories outside the retrieved RAG context.
- [ ] Responses from the local LLM rely exclusively on the provided RAG context for memory-related interactions.

### Verification
- [ ] Automated tests covering user registration, user login, and context builder prompt formatting/grounding are implemented and pass.
