# Milestone 1 Auth Remediation Changes

## Overview
Remediated the 3 security and robustness issues identified by Reviewer 2 in `reviewer_m1_2/review.md`:
1. Prevented privilege escalation / admin impersonation in `app/auth/jwt.py` for unknown JWT subjects.
2. Removed preemptive Pydantic `min_length=3` in `app/auth/schemas.py` to allow optional empty string usernames to normalize to `None` while maintaining Egyptian Arabic validation on short inputs.
3. Protected against race conditions on concurrent duplicate registration in `app/auth/router.py` using `try...except IntegrityError` returning HTTP 400 with Egyptian Arabic messages.
4. Added comprehensive automated tests in `tests/integration/test_user_auth_endpoints.py`.

---

## 1. `app/auth/jwt.py`
- **Location**: `get_current_user_model`, lines 163–188
- **Change**: Restricted fallback resolution of `first_user` (Admin) exclusively to recognized developer/hardware identities:
  ```python
  if sub in ("dev_user", "api_key_client", "control_room_desktop"):
      res_admin = await db.execute(select(User).order_by(User.id).limit(1))
      first_user = res_admin.scalar_one_or_none()
      if first_user:
          return first_user
      ...
  ```
- **Security Impact**: Any forged, expired, or non-existent user JWT subjects (numeric or string) can no longer masquerade as Admin User 1 (`admin@nebula.local`). They are rejected with HTTP 401 Unauthorized (`"صاحب الحساب المرتبط بالتوكن ده مش موجود."`).

---

## 2. `app/auth/schemas.py`
- **Location**: `UserRegister.username` Field definition, lines 34–38
- **Change**: Removed `min_length=3` constraint from `Field(...)`:
  ```python
  username: Optional[str] = Field(
      None,
      max_length=64,
      description="اسم المستخدم الفريد (اختياري)",
  )
  ```
- **UX & Robustness Impact**: When web form clients submit optional inputs as empty strings (`""`) or whitespace, the field validator strips the string and normalizes it to `None` instead of failing with an English Pydantic validation error (`"String should have at least 3 characters"`). Short strings (< 3 chars) continue to be rejected by the custom Egyptian Arabic validator with `"اسم المستخدم لازم يكون 3 حروف على الأقل."`.

---

## 3. `app/auth/router.py`
- **Location**: `register` endpoint, lines 145–154
- **Change**: Imported `IntegrityError` from `sqlalchemy.exc` and wrapped `await db.commit()` in `try...except IntegrityError`:
  ```python
  db.add(new_user)
  try:
      await db.commit()
      await db.refresh(new_user)
  except IntegrityError:
      await db.rollback()
      raise HTTPException(
          status_code=status.HTTP_400_BAD_REQUEST,
          detail="البريد الإلكتروني أو اسم المستخدم ده مسجل بالفعل عندنا. اختار بيانات تانية.",
      )
  ```
- **Robustness Impact**: Prevents unhandled 500 Internal Server Errors under concurrent duplicate registration races, returning HTTP 400 Bad Request with authentic Egyptian Arabic detail containing `"مسجل بالفعل"`.

---

## 4. `tests/integration/test_user_auth_endpoints.py`
- **Location**: Lines 319–412
- **New Tests Added**:
  1. `test_jwt_unknown_sub_rejection`: Asserts that unknown numeric and string JWT subjects receive 401 with `"صاحب الحساب المرتبط بالتوكن ده مش موجود."`.
  2. `test_username_empty_and_short_validation`: Asserts that empty `""` and whitespace-only `"   "` usernames normalize to `None` and register successfully (201), while short usernames (`"ab"`) return 422 with Egyptian Arabic detail `"اسم المستخدم لازم يكون 3 حروف على الأقل"`.
  3. `test_integrity_error_race_duplicate_handling`: Asserts that concurrent database `IntegrityError` during registration commit rolls back and returns 400 Bad Request with Egyptian Arabic message containing `"مسجل بالفعل"`.
