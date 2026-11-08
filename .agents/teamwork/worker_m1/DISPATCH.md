# Dispatch: Worker 1 (Milestone 1 — User Registration and Login Endpoints)

## Objective
Implement production-ready user registration and login API endpoints with JWT authentication, password hashing, and Egyptian Arabic (`arz`) validation according to Requirement R2 and R1.

## Scope Boundaries & Exclusive File Ownership
You exclusively own and may edit the following files:
1. `c:\Users\L0Q\Desktop\graduation project\app\models\user.py`
2. `c:\Users\L0Q\Desktop\graduation project\app\db\session.py`
3. `c:\Users\L0Q\Desktop\graduation project\app\auth/schemas.py`
4. `c:\Users\L0Q\Desktop\graduation project\app\auth/router.py`
5. `c:\Users\L0Q\Desktop\graduation project\app\auth/jwt.py`

Do NOT touch any other files in this milestone.

## Mandatory References
1. Verbatim User Request: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\ORIGINAL_REQUEST.md`
2. Project Blueprint: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\PROJECT.md`
3. Explorer 1 Findings & Code Proposals: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_1\survey_report.md`
4. Language Unification (arz) Guidelines: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_3\survey_report.md`

## Detailed Implementation Requirements
1. **User Model (`app/models/user.py`)**:
   - Add `username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)`.
2. **Database Migration (`app/db/session.py`)**:
   - In `_migrate(connection)`, check if `username` is in `users` columns; if not, execute:
     `ALTER TABLE users ADD COLUMN username VARCHAR(64)` and create unique index `ix_users_username`.
3. **Schemas (`app/auth/schemas.py`)**:
   - `UserRegister`: Add `username: Optional[str] = None`. Validate `full_name`, `username` (3-64 chars, regex alphanumeric + arabic + `_` + `-`), `password` (>=8 chars, letter+digit), `confirm_password` matches password, and `terms_accepted` is True.
   - `UserLogin`: Allow `email`, `username`, or `identifier`. Check that at least one identifier is provided.
   - `UserResponse`: Add `username: Optional[str] = None`.
   - All validation error messages in authentic Egyptian Arabic (`arz`).
4. **Router (`app/auth/router.py`)**:
   - `register`: Check email uniqueness AND username uniqueness (if username provided). Save `username`. Return Egyptian Arabic messages for duplicate email/username. Keep substring `"مسجل بالفعل"` for test compatibility.
   - `login`: Resolve identifier from `username`, `identifier`, or `email`. Query `(User.email == login_id) | (User.username == login_id)`. Verify password hash with bcrypt. Issue JWT token.
   - Error responses in Egyptian Arabic (`arz`).
5. **JWT (`app/auth/jwt.py`)**:
   - Update `get_current_user_model` to resolve by user id, email, or username.
   - Unify token expiration/invalid messages into Egyptian Arabic (`arz`).
6. **User Rule**:
   - Directly edit the files using file editing tools — do NOT use python injection scripts.

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Deliverable
Run tests using pytest on existing test suite (`tests/integration/test_user_auth_endpoints.py`), verify all passing, document commands and results in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m1\changes.md` and complete with `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m1\handoff.md`.

## 2026-11-02T22:34:30Z
You are Worker M1 (Auth Implementation Worker).
Your working directory is: c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m1\
Read `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\ORIGINAL_REQUEST.md` and `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m1\DISPATCH.md`.
Read Explorer 1 findings in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_1\survey_report.md`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Implement Milestone 1:
1. `app/models/user.py`: Add `username` column with unique index.
2. `app/db/session.py`: In `_migrate`, add dynamic schema migration for `username` in `users`.
3. `app/auth/schemas.py`: Update `UserRegister`, `UserLogin`, `UserResponse` with flexible username support and Egyptian Arabic validation.
4. `app/auth/router.py`: Support registration and login via username or email, return JWT, handle duplicate username/email, all errors in arz.
5. `app/auth/jwt.py`: Support lookup by username in `get_current_user_model`, unify token exception messages in arz.
6. Verify your implementation by running pytest on `tests/integration/test_user_auth_endpoints.py`.
Document changes in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m1\changes.md` and handoff in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m1\handoff.md`.
When finished, send a message to your parent orchestrator.
