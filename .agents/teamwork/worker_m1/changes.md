# Changes: Worker M1 (Milestone 1 — Auth Implementation)

## Overview
Worker M1 implemented production-ready user registration and login endpoints with flexible username and email authentication, JWT issuance, bcrypt password hashing, automatic SQLite database migration, and comprehensive Egyptian Arabic (`arz`) message localization.

## Modified Files

### 1. `app/models/user.py`
- Added `username` column to `User` ORM model:
  ```python
  username: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)
  ```
- Positioned between `full_name` and `email` to maintain model logical clarity and allow optional unique usernames for registered users.

### 2. `app/db/session.py`
- Updated self-healing database migration function `_migrate(connection)`:
  - Detects if `username` column exists in SQLite table `users`.
  - Automatically executes `ALTER TABLE users ADD COLUMN username VARCHAR(64)` and creates unique index `ix_users_username` on table creation or migration if missing.
- Added default `username="mazen"` to seeded default admin user (id=1).

### 3. `app/auth/schemas.py`
- `UserRegister`:
  - Added optional `username: Optional[str] = Field(None, min_length=3, max_length=64)`.
  - Added Egyptian Arabic field validator for `username`: enforces 3-64 character length and regex pattern allowing alphanumeric characters, Arabic script (`\u0600-\u06FF`), underscores, and hyphens without spaces.
  - Converted validation error messages (`full_name`, `password`, `confirm_password`, `terms_accepted`) into Egyptian Arabic (`arz`).
- `UserLogin`:
  - Updated to accept `email`, `username`, or `identifier` as string fields.
  - Added model validator checking that at least one identifier is present; raises an Egyptian Arabic error if none are provided.
- `ResetPasswordRequest`:
  - Converted password strength and mismatch validation messages to Egyptian Arabic.
- `UserResponse`:
  - Added `username: Optional[str] = None` to public user profile representation.

### 4. `app/auth/router.py`
- `_user_to_response`:
  - Maps `user.username` into `UserResponse`.
- `POST /register`:
  - Validates email uniqueness with Egyptian Arabic response preserving `"مسجل بالفعل"`.
  - Validates username uniqueness if provided with Egyptian Arabic error response.
  - Persists `username` and hashes password using bcrypt.
  - Issues 8-hour JWT token with user metadata (`sub`, `email`, `name`, `username`).
- `POST /login`:
  - Extracts identifier dynamically from `body.username`, `body.identifier`, or `body.email`.
  - Looks up user by `(User.email == login_id) | (User.username == login_id)`.
  - Verifies bcrypt password hash and handles inactive accounts.
  - Returns JWT token with variable expiration (8 hours standard, 30 days for `remember_me`).
  - Egyptian Arabic error message: `"البريد الإلكتروني / اسم المستخدم أو كلمة المرور مش صحيحة. اتأكد وجرب تاني."`
- `POST /login/biometric`:
  - Supports lookup by either email or username in the form parameter.
  - Localized messages into Egyptian Arabic while preserving substring `"غير متطابقة"` for test assertions.
- `POST /biometric/link`:
  - Localized feedback and error messages into Egyptian Arabic.
- `POST /forgot-password` and `POST /reset-password`:
  - Localized reset confirmation and token expiry messages into Egyptian Arabic.
- `POST /token`:
  - Localized pairing code validation error to Egyptian Arabic.

### 5. `app/auth/jwt.py`
- `decode_access_token`:
  - Localized token expiration and invalid token error details into Egyptian Arabic (`arz`).
- `get_current_user`:
  - Localized API key failure and missing credential errors into Egyptian Arabic (`arz`).
- `get_current_user_model`:
  - Extended lookup logic to match `User.id` (numeric), `User.email`, or `User.username`.
  - Added `username="mazen"` for developer auto-provisioning fallback.
  - Localized inactive account and user not found messages to Egyptian Arabic (`arz`).

## Verification
- Executed `pytest tests/integration/test_user_auth_endpoints.py`.
- Result: **5 passed** (100% success rate).
