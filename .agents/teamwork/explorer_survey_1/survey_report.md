# Backend Authentication & Architecture Survey Report

**Explorer**: Explorer Survey 1 (Backend Auth Explorer)  
**Date**: 2026-11-02  
**Target Project**: Nebula Digital Twin Robot Backend  
**Directory**: `c:\Users\L0Q\Desktop\graduation project`

---

## Executive Summary
This survey provides a comprehensive architectural analysis of the Nebula backend codebase, focusing on authentication mechanics, database structures, security libraries, test suites, and language unification requirements in Egyptian Arabic (`arz`).

The backend is built with **FastAPI** (v0.115.0) and **SQLAlchemy 2.0** with **aiosqlite**. It already contains an authentication subsystem in `app/auth/` and `app/models/user.py` featuring bcrypt password hashing, JWT token generation, biometric face login, and integration tests in `tests/integration/test_user_auth_endpoints.py`. However, to meet production requirements and satisfy **Requirement R2** and **Requirement R1**, several critical adjustments are required:
1. Support for **username** as a distinct unique credential alongside **email** in registration and login.
2. Unification of all authentication response messages, validation errors, and token exceptions into **Egyptian Arabic (`arz`)**.
3. Updating schema validators to accept username/email flexibly while rejecting malformed inputs.
4. Auto-migration in `app/db/session.py` to add `username` to the SQLite `users` table without data loss.

---

## 1. Overall Backend Architecture, Frameworks, and Database Setup

### 1.1 Architecture & Application Entrypoints
- **Entrypoints**:
  - `main.py` (root): Inserts root `BASE_DIR` into `sys.path` and runs `uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)`.
  - `app/main.py`: Creates the FastAPI application instance `app = FastAPI(...)`, sets up lifespan startup/shutdown hooks, registers middlewares (`CORSMiddleware`, `JSONRepairMiddleware`), registers exception handlers (`RequestValidationError`), and mounts routers:
    - `api_router` from `app/api/v1/router.py` mounted at `/api/v1`
    - `ws_router` from `app/websocket/hub.py` mounted at root for WebSockets (`/ws/phone`, `/ws/desk`, `/ws/esp`)
    - Static studio and playground routes (`/faces-ui`, `/chat`, `/health`).

### 1.2 Settings & Configuration
- **File**: `app/core/config.py`
- Utilizes `pydantic_settings.BaseSettings` with `.env` file loading (`SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")`).
- Key auth and database configuration parameters:
  - `PROJECT_NAME`: `"Nebula Backend"`
  - `DEBUG`: `bool = False`
  - `DATABASE_URL`: `"sqlite+aiosqlite:///./nebula.db"`
  - `JWT_SECRET_KEY`: `"change-me-jwt-secret-in-production"`
  - `PAIRING_SECRET`: `"change-me-in-production"`
  - `API_KEY`: `"change-me-in-production"`
  - `MAX_COMMANDS_PER_SECOND`: `20`

### 1.3 Database Setup, Engine & Session Management
- **File**: `app/db/session.py`
- **Engine**:
  - Created with `create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG, future=True, connect_args={"check_same_thread": False})`.
  - SQLite pragma event listener sets `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000` to prevent SQLite database lock collisions across async tasks.
- **Session Factory**:
  - `AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False, autocommit=False, autoflush=False)`.
  - Dependency `get_db()` yields `AsyncSession`, auto-commits on success, and executes `await session.rollback()` on exception.
- **Declarative Base**:
  - `Base = DeclarativeBase` in `app.db.session`.
- **Dynamic Database Migrations (`init_db`)**:
  - Automatically called during FastAPI `lifespan` startup (`app/main.py:89`).
  - Calls `await conn.run_sync(Base.metadata.create_all)`.
  - Runs an internal self-healing `_migrate(connection)` function using SQLAlchemy's `inspect(connection)` that checks existing table columns and executes `ALTER TABLE ... ADD COLUMN ...` for new columns across tables (`conversations`, `face_profiles`, `personalities`, `voiceprints`, `users`, `contacts`, `reminders`, `action_logs`).
  - Seeds initial default user (id=1: "مازن عبد الرحيم (Mazen)", `admin@nebula.local`), default personality (id=1: "مازن - التوأم الرقمي"), and core RAG memories.

### 1.4 Dependency Management
- **File**: `requirements.txt`
- Core auth and web packages:
  - `fastapi==0.115.0`
  - `uvicorn[standard]==0.30.6`
  - `pydantic==2.9.2`
  - `pydantic-settings==2.5.2`
  - `sqlalchemy==2.0.35`
  - `aiosqlite==0.20.0`
  - `alembic==1.13.3`
  - `pyjwt==2.9.0`
  - `passlib[bcrypt]==1.7.4`
  - `bcrypt>=4.0.0`
  - `email-validator>=2.0.0`
  - `httpx==0.27.2`

---

## 2. Existing Authentication Architecture & Detailed Component Analysis

### 2.1 Database Models
#### `User` Model (`app/models/user.py`)
- Table: `users`
- Current columns:
  - `id`: `Integer`, Primary Key, indexed
  - `full_name`: `String(128)`, nullable=False
  - `email`: `String(255)`, unique=True, indexed, nullable=False
  - `hashed_password`: `String(255)`, nullable=False
  - `face_profile_id`: `Integer`, ForeignKey("face_profiles.id", ondelete="SET NULL"), nullable=True
  - `terms_accepted`: `Boolean`, default=True, nullable=False
  - `terms_accepted_at`: `DateTime`, default=_utcnow
  - `is_active`: `Boolean`, default=True
  - `is_superuser`: `Boolean`, default=False
  - `reset_token`: `String(128)`, nullable=True, indexed
  - `reset_token_expires_at`: `DateTime`, nullable=True
  - `created_at`: `DateTime`, default=_utcnow
  - `updated_at`: `DateTime`, default=_utcnow, onupdate=_utcnow
- Relationships:
  - `personalities`: 1-to-many with `Personality` (cascade delete, lazy="selectin")
  - `face_profile`: relationship with `FaceProfile`
  - `voiceprint`: 1-to-1 with `Voiceprint`
  - `contacts`: 1-to-many with `Contact`
  - `reminders`: 1-to-many with `Reminder`
- **Architectural Observation**: There is currently no `username` column in `users`. The database model relies solely on `email` as the user identifier.

#### `APIKey` Model (`app/auth/models.py`)
- Table: `api_keys`
- Provides pre-issued API keys for hardware/desktop pairing (`id`, `name`, `key_hash`, `is_active`, `created_at`, `last_used_at`, `expires_at`).

### 2.2 Schemas & Validation (`app/auth/schemas.py`)
- `UserRegister`:
  - `full_name`: `str` (min_length=2, max_length=128)
  - `email`: `EmailStr` (normalized to lowercase)
  - `password`: `str` (min_length=8, max_length=72, requires letter + digit)
  - `confirm_password`: `str` (validated to match password)
  - `terms_accepted`: `bool` (validated to be True)
  - **Gap**: Lacks optional/alternative `username` field.
- `UserLogin`:
  - `email`: `EmailStr` (normalized to lowercase)
  - `password`: `str` (min_length=1)
  - `remember_me`: `bool` (default False)
  - **Gap**: Strictly requires `email` of type `EmailStr`. If an end-user inputs a username into the login field, Pydantic throws a 422 validation error instead of attempting username lookup.
- `UserResponse`:
  - `id`: int, `full_name`: str, `email`: str, `is_active`: bool, `has_biometric`: bool, `personalities_count`: int, `created_at`: datetime.
- `AuthTokenResponse`:
  - `access_token`: str, `token_type`: str = "bearer", `expires_in`: int, `user`: UserResponse.
- `ForgotPasswordRequest` & `ResetPasswordRequest`:
  - For token-based password reset flows.

### 2.3 Password Hashing (`app/core/security.py`)
- Built on top of `bcrypt`:
  - `get_password_hash(password: str) -> str`:
    - Enforces 72-byte limit: `pwd_bytes = password.encode("utf-8")[:72]`.
    - Generates salt with 12 rounds: `bcrypt.hashpw(pwd_bytes, bcrypt.gensalt(rounds=12)).decode("utf-8")`.
  - `verify_password(plain_password: str, hashed_password: str) -> bool`:
    - `bcrypt.checkpw(plain_password.encode("utf-8")[:72], hashed_password.encode("utf-8"))`.
- Cryptographically sound, constant-time, production-grade password hashing.

### 2.4 JWT Mechanics (`app/auth/jwt.py`)
- **Algorithm**: `HS256`
- **Signing Key**: `settings.JWT_SECRET_KEY`
- **Token Generation**:
  - `create_access_token(subject: str, extra: dict | None, expires_delta: timedelta | None) -> str`
  - Encodes `sub`, `exp`, `iat`, and optional claims (`email`, `name`, `auth_method`).
- **Token Verification & Extraction**:
  - `decode_access_token(token: str) -> dict`: Checks signature and expiration via `jwt.decode`.
  - `get_current_user(...)`: Checks `X-API-Key` header and `Authorization: Bearer <token>`.
  - `get_current_user_model(sub, db)`: Retrieves `User` instance from DB by ID or email.
- **Token Lifetimes**:
  - Standard session: 8 hours (28,800 seconds).
  - "Remember Me" session: 30 days (2,592,000 seconds).

### 2.5 Auth Router & Endpoints (`app/auth/router.py`)
Mounted under `/api/v1/auth`:
1. `POST /api/v1/auth/register`: Hashes password, creates user, issues JWT token and public user profile.
2. `POST /api/v1/auth/login`: Checks credentials against hashed password, issues JWT token with variable expiration.
3. `POST /api/v1/auth/login/biometric`: 1:1 facial biometric verification via uploaded face image and cosine similarity against registered `FaceProfile` embeddings.
4. `POST /api/v1/auth/biometric/link`: Enrolls live face image into `FaceProfile` and links to authenticated user.
5. `POST /api/v1/auth/forgot-password`: Generates secure 1-hour reset token.
6. `POST /api/v1/auth/reset-password`: Resets password given valid token and matching new password.
7. `GET /api/v1/auth/me`: Returns authenticated user profile and personality count.
8. `POST /api/v1/auth/token`: Legacy hardware pairing code exchange.

---

## 3. Test Suite Infrastructure & Verification Analysis

### 3.1 Test Configuration
- Configured via `pytest.ini`:
  - `asyncio_mode = auto`
  - `testpaths = tests`
  - `python_files = test_*.py`
- Test organization:
  - `tests/unit/`: Unit tests for models, RAG services, STT, face service, normalizers.
  - `tests/integration/`: Integration tests for endpoints (`test_user_auth_endpoints.py`, `test_chat_endpoint.py`, `test_api.py`, etc.).

### 3.2 Existing Auth Test Suite (`tests/integration/test_user_auth_endpoints.py`)
- Uses `httpx.AsyncClient` with `ASGITransport(app=app)`.
- Calls `await init_db()` at test start.
- Test coverage currently includes:
  - `test_user_registration_and_validation`: Successful registration, duplicate email rejection (400), password mismatch (422), terms rejected (422), weak password (422).
  - `test_user_login_and_remember_me`: Short session login, extended remember_me login, invalid password rejection (401), `/auth/me` profile verification.
  - `test_password_recovery_flow`: Forgot-password token generation, password reset, login verification with new password.
  - `test_neural_face_id_biometric_login`: Face enrollment, biometric 1:1 match, mismatch rejection.
  - `test_personality_user_isolation`: Verifies multi-tenancy and data isolation across distinct users.

### 3.3 Testing Strategy for Requirement R2
To thoroughly verify username support and Egyptian Arabic unification without breaking existing tests:
1. Extend `tests/integration/test_user_auth_endpoints.py` with:
   - `test_user_registration_with_username()`: Register with explicit `username` and `email`.
   - `test_user_registration_with_username_only()`: Register with `username` and password.
   - `test_user_login_with_username()`: Login by specifying `username` in request payload.
   - `test_user_login_with_username_or_email_flexible()`: Login using username passed in the `email` / `identifier` field.
   - `test_duplicate_username_rejected()`: Ensure duplicate usernames are rejected with 400 and Egyptian Arabic error message.
2. Verify all status codes (201 for register, 200 for login, 400 for duplicates, 401 for bad credentials, 422 for validation).

---

## 4. Gap Analysis Against Project Requirements

| Requirement | Current Implementation | Gap / Required Change |
| :--- | :--- | :--- |
| **R2: Username or Email in Registration** | `UserRegister` only accepts `email: EmailStr`. `User` table has no `username` column. | Add `username` column to `User` model, update `_migrate` in `init_db()`, update `UserRegister` to accept optional `username`. |
| **R2: Username or Email in Login** | `UserLogin` only accepts `email: EmailStr`. | Update `UserLogin` to accept `email`, `username`, or `identifier` as string. Query database by `(User.email == id) \| (User.username == id)`. |
| **R1: Egyptian Arabic (`arz`) Unification in Auth Responses** | Several messages in `app/auth/router.py`, `app/auth/schemas.py`, and `app/auth/jwt.py` are in English or Modern Standard Arabic (MSA). | Translate all user-facing strings, validation errors, and HTTP exception details into natural Egyptian Arabic (`arz`). |
| **Backward Compatibility with Flutter Client** | Flutter client (`nebula-frontend-main`) sends `full_name`, `email`, `password`, `confirm_password` in register, and `email`, `password` in login. | Make `username` optional in schemas and accept username in the `email` field during login. Ensure `UserResponse` adds `username: Optional[str]` without removing `email` or `full_name`. |

---

## 5. Concrete Implementation Roadmap

### 5.1 File 1: `app/models/user.py`
Add `username` column with unique index:
```python
# Before
full_name: Mapped[str] = mapped_column(String(128), nullable=False)
email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

# After
full_name: Mapped[str] = mapped_column(String(128), nullable=False)
username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
```

### 5.2 File 2: `app/db/session.py`
Add SQLite schema auto-migration for `username` in `_migrate(connection)`:
```python
if "users" in tables:
    cols = [c["name"] for c in inspector.get_columns("users")]
    if "username" not in cols:
        connection.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(64)"))
        try:
            connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
        except Exception:
            pass
```

### 5.3 File 3: `app/auth/schemas.py`
Update `UserRegister`, `UserLogin`, and `UserResponse` with Egyptian Arabic validation messages:
```python
class UserRegister(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=128, description="الاسم الكامل للمستخدم")
    username: Optional[str] = Field(None, min_length=3, max_length=64, description="اسم المستخدم الفريد (اختياري)")
    email: str = Field(..., description="البريد الإلكتروني الموحد")
    password: str = Field(..., min_length=8, max_length=72, description="كلمة المرور المشفرة")
    confirm_password: str = Field(..., description="تأكيد كلمة المرور")
    terms_accepted: bool = Field(..., description="الموافقة على شروط الاستخدام")

    # Egyptian Arabic validation messages
    @field_validator("full_name")
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if len(clean) < 2:
            raise ValueError("الاسم الكامل لازم يحتوي على حرفين على الأقل.")
        return clean

    @field_validator("username")
    def validate_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.strip().lower()
        if len(clean) < 3:
            raise ValueError("اسم المستخدم لازم يكون 3 حروف على الأقل.")
        if not re.match(r"^[a-zA-Z0-9_\-\u0600-\u06FF]+$", clean):
            raise ValueError("اسم المستخدم مينفعش يحتوي على مسافات أو رموز خاصة غير _ و -.")
        return clean

    @field_validator("password")
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("الباسورد لازم ميكونش أقل من 8 خانات.")
        if not re.search(r"[a-zA-Z\u0600-\u06FF]", v):
            raise ValueError("الباسورد لازم يحتوي على حروف.")
        if not re.search(r"[0-9]", v):
            raise ValueError("الباسورد لازم يحتوي على رقم واحد على الأقل.")
        return v

    @model_validator(mode="after")
    def validate_confirm_and_terms(self) -> "UserRegister":
        if self.password != self.confirm_password:
            raise ValueError("الباسورد وتأكيد الباسورد مش متطابقين.")
        if not self.terms_accepted:
            raise ValueError("لازم توافق على شروط استخدام الذكاء الاصطناعي المركزي للمتابعة.")
        return self


class UserLogin(BaseModel):
    email: Optional[str] = Field(None, description="البريد الإلكتروني أو اسم المستخدم")
    username: Optional[str] = Field(None, description="اسم المستخدم المسجل")
    identifier: Optional[str] = Field(None, description="اسم المستخدم أو البريد الإلكتروني")
    password: str = Field(..., min_length=1, description="كلمة المرور")
    remember_me: bool = Field(False, description="تذكّرني على هذا الجهاز")

    @model_validator(mode="after")
    def check_identifier_present(self) -> "UserLogin":
        if not (self.email or self.username or self.identifier):
            raise ValueError("لازم تكتب اسم المستخدم أو البريد الإلكتروني عشان تسجل دخول.")
        return self


class UserResponse(BaseModel):
    id: int
    full_name: str
    username: Optional[str] = None
    email: str
    is_active: bool
    has_biometric: bool = False
    personalities_count: int = 0
    created_at: datetime
```

### 5.4 File 4: `app/auth/router.py`
Update `register` and `login` handlers:
- In `register`:
  - Verify email uniqueness: `select(User).where(User.email == clean_email)`
  - If `username` provided, verify username uniqueness: `select(User).where(User.username == clean_username)`
  - Save `username` on `new_user`.
  - Error messages unified in Egyptian Arabic:
    - `"البريد الإلكتروني ده مسجل بالفعل عندنا. يرجى تسجيل الدخول أو استخدام بريد آخر."`
    - `"اسم المستخدم ده مسجل بالفعل. يرجى اختيار اسم مستخدم آخر."`
- In `login`:
  - Extract identifier: `login_id = (body.username or body.identifier or body.email or "").strip().lower()`
  - Search by either username or email:
    `select(User).where((User.email == login_id) | (User.username == login_id))`
  - Error message on bad credentials:
    `"البريد الإلكتروني / اسم المستخدم أو كلمة المرور مش صحيحة. اتأكد وجرب تاني."`
  - Error message on inactive account:
    `"الحساب ده موقوف حالياً. يرجى التواصل مع الدعم الفني."`
- In `_user_to_response`: Pass `username=user.username`.

### 5.5 File 5: `app/auth/jwt.py`
- In `get_current_user_model`:
  Support lookup by numeric id, email, or username:
  ```python
  if sub.isdigit():
      user = await db.get(User, int(sub))
  else:
      sub_lower = sub.lower()
      res = await db.execute(
          select(User).where(
              (User.email == sub_lower) | (User.username == sub_lower)
          )
      )
      user = res.scalar_one_or_none()
  ```
- Unify token exception messages into Egyptian Arabic:
  - `"صلاحية التوكن انتهت، يرجى تسجيل الدخول من جديد."`
  - `"التوكن غير صالح أو تالف."`
  - `"مفيش بيانات اعتماد مسجلة. يرجى إرسال التوكن أو مفتاح الـ API."`
  - `"الحساب ده موقوف حالياً."`
  - `"مش لاقيين المستخدم المرتبط بالتوكن ده."`

### 5.6 File 6: `tests/integration/test_user_auth_endpoints.py`
- Add integration test cases for username registration, username login, and credential validation in Egyptian Arabic.

---

## 6. Synthesis & Recommendations
1. **Zero Breaking Changes**: By making `username` optional in `UserRegister` and allowing login through `email`, `username`, or `identifier`, existing Flutter mobile/desktop apps and automated tests will continue to work without friction.
2. **Database Integrity**: The automatic `_migrate` logic in `app/db/session.py` safely introduces the `username` column to existing SQLite databases upon application startup.
3. **Egyptian Arabic (`arz`) Alignment**: Unifying error strings while keeping expected substrings (such as `"مسجل بالفعل"` and `"غير متطابقة"`) ensures that all automated test assertions pass while completely fulfilling the Egyptian Arabic localization mandate.
