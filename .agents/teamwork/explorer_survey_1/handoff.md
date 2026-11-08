# Handoff Report — Explorer Survey 1 (Backend Auth Explorer)

**Agent**: Explorer Survey 1  
**Folder**: `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\explorer_survey_1`  
**Milestone**: Architecture & Auth Survey Complete  
**Handoff Type**: Hard  

---

## 1. Observation
1. **Entrypoints & Routing**:
   - `c:\Users\L0Q\Desktop\graduation project\main.py`: Root entrypoint wrapping `app.main:app`.
   - `c:\Users\L0Q\Desktop\graduation project\app\main.py:302`: `app.include_router(api_router, prefix="/api/v1")`.
   - `c:\Users\L0Q\Desktop\graduation project\app\api\v1\router.py:24`: `api_router.include_router(auth_router)`.
   - `c:\Users\L0Q\Desktop\graduation project\app\auth\router.py:42`: `router = APIRouter(prefix="/auth", tags=["auth"])`.
2. **Database Engine & Migration**:
   - `c:\Users\L0Q\Desktop\graduation project\app\db\session.py:21`: SQLite async engine configured with WAL mode (`PRAGMA journal_mode=WAL`) and `busy_timeout=5000`.
   - `c:\Users\L0Q\Desktop\graduation project\app\db\session.py:50-144`: `init_db()` runs `Base.metadata.create_all` followed by dynamic reflection-based schema migrations in `_migrate(connection)` executing `ALTER TABLE ... ADD COLUMN ...` for new model fields.
3. **User Model Structure**:
   - `c:\Users\L0Q\Desktop\graduation project\app\models\user.py:23-48`:
     `User` model contains `id`, `full_name`, `email`, `hashed_password`, `face_profile_id`, `terms_accepted`, `terms_accepted_at`, `is_active`, `is_superuser`, `reset_token`, `reset_token_expires_at`, `created_at`, `updated_at`.
     *Direct observation: The `users` table and `User` model currently do NOT have a `username` column.*
4. **Auth Schemas & Validators**:
   - `c:\Users\L0Q\Desktop\graduation project\app\auth\schemas.py:18-83`: `UserRegister` enforces `email: EmailStr`, `full_name`, `password` (min 8 chars, letter + digit), `confirm_password`, and `terms_accepted: bool`.
   - `c:\Users\L0Q\Desktop\graduation project\app\auth\schemas.py:85-110`: `UserLogin` enforces `email: EmailStr` and `password: str`. Any non-email string causes a Pydantic 422 error.
5. **Password Hashing & JWT**:
   - `c:\Users\L0Q\Desktop\graduation project\app\core\security.py:50-65`: Uses `bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=12))` and `bcrypt.checkpw(...)`.
   - `c:\Users\L0Q\Desktop\graduation project\app\auth\jwt.py:29-58`: Uses PyJWT with `HS256` and `settings.JWT_SECRET_KEY`.
6. **Language Representation**:
   - `c:\Users\L0Q\Desktop\graduation project\app\auth\jwt.py:55, 93, 113, 149`: Error messages are in English (`"Token expired"`, `"Invalid API key"`, `"No credentials provided..."`, `"User account is deactivated."`).
   - `c:\Users\L0Q\Desktop\graduation project\app\auth\router.py:116, 176`: Responses are in Modern Standard Arabic (MSA), e.g., `"البريد الإلكتروني مسجل بالفعل. يرجى تسجيل الدخول أو استخدام بريد آخر."`
7. **Test Suite**:
   - `c:\Users\L0Q\Desktop\graduation project\pytest.ini`: `asyncio_mode = auto`, `testpaths = tests`.
   - `c:\Users\L0Q\Desktop\graduation project\tests\integration\test_user_auth_endpoints.py`: Integration test suite using `httpx.AsyncClient` covering registration, duplicate email rejection, login, remember_me token lifetimes, face biometrics, and password recovery.

---

## 2. Logic Chain
1. *From Observation 3 & Requirement R2*: Requirement R2 explicitly requires user registration and login using username or email and password authentication. Since `User` only possesses `email`, a new column `username` (`String(64), unique=True, index=True, nullable=True`) must be added to `app/models/user.py`.
2. *From Observation 2*: Because existing SQLite databases (e.g. `nebula.db`) exist in the environment, modifying the model alone without updating `_migrate(connection)` in `app/db/session.py` could cause schema mismatch errors. Adding `ALTER TABLE users ADD COLUMN username VARCHAR(64)` in `_migrate()` ensures zero-friction automated upgrade.
3. *From Observation 4*: `UserLogin` currently restricts inputs to `EmailStr`. If an end-user attempts login with their username, the request is rejected with HTTP 422 before reaching the database query. Broadening `UserLogin` to accept `email`, `username`, or `identifier` allows seamless authentication by either credential.
4. *From Observation 4 & 6 & Requirement R1*: Requirement R1 mandates project-wide unification to Egyptian Arabic (`arz`). Updating validation errors in `app/auth/schemas.py`, endpoint error details in `app/auth/router.py`, and JWT exception details in `app/auth/jwt.py` to Egyptian Arabic fulfills R1 while preserving key substrings expected by existing tests.
5. *From Observation 7*: The existing integration test harness in `tests/integration/test_user_auth_endpoints.py` provides an ideal baseline. Adding test cases for username registration, username login, and credential validation will verify R2 without disturbing existing test flows.

---

## 3. Caveats
- No modifications were performed on the project source code in accordance with Explorer read-only constraints.
- Flutter frontend (`nebula-frontend-main`) already interfaces with `/api/v1/auth/login` and `/api/v1/auth/register`. All schema updates must maintain backward compatibility with Flutter payloads (`full_name`, `email`, `password`, `confirm_password`). Making `username` optional in registration and accepting username in `email` or `username` during login satisfies both requirements without breaking the frontend.
- Command execution was denied by environment permission check; survey was executed via deep static inspection of all relevant files.

---

## 4. Conclusion
The backend authentication foundation is structurally robust, with secure bcrypt hashing, JWT issuance, and integration test coverage already in place. The exact implementation path to achieve production readiness for R2 and R1 requires:
1. Adding `username` column to `User` model (`app/models/user.py`) and schema migration (`app/db/session.py`).
2. Expanding `UserRegister` and `UserLogin` schemas (`app/auth/schemas.py`) to support username/email flexibility.
3. Updating login logic in `app/auth/router.py` to query by `(User.email == identifier) | (User.username == identifier)`.
4. Updating `get_current_user_model` in `app/auth/jwt.py` to resolve users by ID, email, or username.
5. Unifying all auth validation, token, and API response strings into Egyptian Arabic (`arz`).
6. Adding integration tests in `tests/integration/test_user_auth_endpoints.py`.

A comprehensive breakdown and exact proposed code modifications are documented in `survey_report.md`.

---

## 5. Verification Method
1. **File Inspection**:
   - Inspect `app/models/user.py` for `username` field.
   - Inspect `app/db/session.py` lines 107-127 for `username` column migration.
   - Inspect `app/auth/schemas.py` for `username` validation and Egyptian Arabic error strings.
   - Inspect `app/auth/router.py` for username/email dual-lookup.
2. **Automated Integration Tests**:
   - Run: `pytest tests/integration/test_user_auth_endpoints.py -v`
   - Test criteria:
     - Register with email + password -> 201 Created.
     - Register with username + email + password -> 201 Created.
     - Login with email -> 200 OK + JWT access token.
     - Login with username -> 200 OK + JWT access token.
     - Invalid credentials -> 401 Unauthorized with Egyptian Arabic detail.
     - Duplicate email/username -> 400 Bad Request with Egyptian Arabic detail.
     - All pre-existing auth tests continue to pass.
