# Project: Nebula Digital Twin Robot — Language Unification (arz), Authentication, and RAG Grounding

## Architecture
- **Framework**: FastAPI (v0.115.0) async REST & WebSocket server.
- **Database & ORM**: SQLAlchemy 2.0 with aiosqlite (WAL mode) and automated migration in `app/db/session.py`.
- **Security & Authentication Subsystem**:
  - `app/models/user.py`: `User` model with `id`, `full_name`, `username`, `email`, `hashed_password`, `face_profile_id`, `terms_accepted`, timestamps.
  - `app/core/security.py`: bcrypt password hashing with 12 rounds and constant-time verification.
  - `app/auth/jwt.py`: PyJWT with HS256 algorithm, 8-hour standard expiration, 30-day "remember me" expiration.
  - `app/auth/schemas.py`: Pydantic v2 schemas (`UserRegister`, `UserLogin`, `UserResponse`, `AuthTokenResponse`) supporting username or email, validated in Egyptian Arabic (`arz`).
  - `app/auth/router.py`: REST endpoints mounted at `/api/v1/auth` (`/register`, `/login`, `/me`, `/forgot-password`, `/reset-password`, etc.).
- **AI Context & RAG Grounding Subsystem**:
  - `app/services/ai/context_builder.py`: Constructs system prompts strictly in authentic Egyptian Arabic (`arz`).
  - Strict negative grounding: Forbids guessing, hallucinating, or assuming any memories or facts outside retrieved RAG context.
  - Deterministic standard refusal: `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"`.
  - Preserves system diagnostics and active personality context block for full test compatibility.
- **Language Unification**:
  - All user-facing documentation, frontend UI (Flutter screens and web templates), backend API error messages/responses, and AI prompts unified to authentic Cairo Egyptian Arabic (`arz`).

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Username DB Column & Auto-Migration | Add `username` column to `users` table and migration in `init_db()` | M1 (DONE) | Survey 1 (R2) |
| 2 | User Registration with Username or Email | Support `username` in `UserRegister` schema, unique validation, bcrypt hashing | M1 (DONE) | Survey 1 (R2) |
| 3 | Flexible User Login with Username or Email | Authenticate via `username` or `email`, return JWT access token and user profile | M1 (DONE) | Survey 1 (R2) |
| 4 | Auth Error & Validation Messages in arz | All auth validation errors, duplicate checks, and token exceptions in Egyptian Arabic | M1 (DONE) | Survey 1 (R1/R2) |
| 5 | RAG Grounding & Zero-Hallucination Directives | Strict Egyptian Arabic directives forcing LLM to rely solely on retrieved RAG | M2 (DONE) | Survey 2 (R3) |
| 6 | Standardized Refusal Formula in arz | Deterministic refusal `"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"` | M2 (DONE) | Survey 2 (R3) |
| 7 | Cleanup & Unification of context_builder.py | Remove broken English/Arabic duplicates and unused script imports | M2 (DONE) | Survey 2 (R3) |
| 8 | Preserve System Status Block in System Prompt | Maintain active personality and hardware telemetry block for test compatibility | M2 (DONE) | Survey 2 (R3) |
| 9 | Project Documentation Unification in arz | Translate `README.md` and `read me/nebula_architecture.md` into authentic Egyptian Arabic | M3 | Survey 3 (R1) |
| 10 | Backend API Responses & Exceptions in arz | Unify all `app/api/v1/endpoints/*.py` HTTP exceptions and messages to `arz` | M3 | Survey 3 (R1) |
| 11 | Frontend UI Strings Unification in arz | Unify Flutter screens (`lib/screens/*.dart`) and web templates to Egyptian Arabic | M3 | Survey 3 (R1) |
| 12 | AI Persona Modelfiles & System Seeds in arz | Unify Ollama Modelfiles and DB initial seed personas to Egyptian Arabic | M3 | Survey 3 (R1) |
| 13 | Context Builder Unit Test Suite | Comprehensive tests in `tests/unit/test_context_builder.py` covering 6 test cases | M4 | Survey 2 (R3/AC) |
| 14 | Integration Tests for Username Auth | Extend `tests/integration/test_user_auth_endpoints.py` for username reg/login | M4 | Survey 1 (R2/AC) |
| 15 | Adversarial Verification & Integrity Audit | Full test suite execution, adversarial edge case checks, and forensic audit | M4 | All Surveys |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: User Registration & Login Endpoints | `app/models/user.py`, `app/db/session.py`, `app/auth/schemas.py`, `app/auth/router.py`, `app/auth/jwt.py` | none | DONE |
| 2 | M2: Context Builder Prompt Enhancement & RAG Grounding | `app/services/ai/context_builder.py` | none | DONE |
| 3 | M3: Project-Wide Language Unification to Egyptian Arabic | `README.md`, `read me/nebula_architecture.md`, `app/api/v1/endpoints/*.py`, `nebula-frontend-main/`, `Modelfile.*` | M1, M2 | IN_PROGRESS |
| 4 | M4: Comprehensive Automated Testing & Verification | `tests/unit/test_context_builder.py`, `tests/integration/test_user_auth_endpoints.py`, test suite execution, audit | M1, M2, M3 | PLANNED |

---

## Interface Contracts
### Client ↔ Auth API (`/api/v1/auth`)
- **Register**: `POST /api/v1/auth/register`
  - Input: `{"full_name": str, "email": str, "username": Optional[str], "password": str, "confirm_password": str, "terms_accepted": bool}`
  - Output: `201 Created` -> `AuthTokenResponse(access_token=str, token_type="bearer", expires_in=int, user=UserResponse)`
  - Validation Errors: `422 Unprocessable Entity` with details in Egyptian Arabic (`arz`).
  - Duplicate Error: `400 Bad Request` with detail `"البريد الإلكتروني ده مسجل بالفعل عندنا..."` or `"اسم المستخدم ده مسجل بالفعل..."`.
- **Login**: `POST /api/v1/auth/login`
  - Input: `{"email": Optional[str], "username": Optional[str], "identifier": Optional[str], "password": str, "remember_me": bool = False}`
  - Output: `200 OK` -> `AuthTokenResponse(access_token=str, token_type="bearer", expires_in=int, user=UserResponse)`
  - Bad Credentials: `401 Unauthorized` with detail `"البريد الإلكتروني / اسم المستخدم أو كلمة المرور مش صحيحة. اتأكد وجرب تاني."`

### AI Pipeline ↔ Context Builder (`build_grounding_context`)
- **Signature**: `async def build_grounding_context(message: str, personality_id: Optional[int] = None, user_id: Optional[int] = None, db: Optional[AsyncSession] = None) -> Tuple[str, List[str], GroundingInfo, Optional[int]]`
- **Output Contract**:
  - `grounded_system_prompt`: Formatted Egyptian Arabic prompt with strict RAG directives, negative refusal rule, persona info, and system context block.
  - `memories`: List of retrieved memory strings from RAG.
  - `grounding_data`: `GroundingInfo` metadata.
  - `active_pid`: Active personality ID.

---

## Code Layout
- `app/models/user.py`: User SQLAlchemy model
- `app/db/session.py`: Database engine, async sessionmaker, and `_migrate()` auto-migration
- `app/auth/schemas.py`: Authentication Pydantic schemas and validators
- `app/auth/router.py`: FastAPI auth router and endpoint functions
- `app/auth/jwt.py`: JWT token generation, verification, and user extraction
- `app/core/security.py`: bcrypt password hashing utilities
- `app/services/ai/context_builder.py`: RAG memory and persona grounding prompt builder
- `tests/unit/test_context_builder.py`: Dedicated unit tests for context builder
- `tests/integration/test_user_auth_endpoints.py`: Integration tests for auth endpoints
