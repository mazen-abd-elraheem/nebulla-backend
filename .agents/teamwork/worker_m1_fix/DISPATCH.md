## 2026-11-02T22:59:04Z
You are Worker M1 Fix (Auth Remediation Worker).
Your working directory is: c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m1_fix\
Read `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\ORIGINAL_REQUEST.md`, `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\PROJECT.md`, and `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m1_fix\DISPATCH.md`.
Read Reviewer 2 feedback at `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\reviewer_m1_2\review.md`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Implement the 3 specific remediations:
1. In `app/auth/jwt.py`: Restrict `first_user` admin fallback in `get_current_user_model` to `if sub in ("dev_user", "api_key_client", "control_room_desktop"):`. For unknown subjects, raise 401.
2. In `app/auth/schemas.py`: Remove `min_length=3` from `UserRegister.username` Field. Allow empty strings to normalize to `None`, or validate length >= 3 in Egyptian Arabic.
3. In `app/auth/router.py`: Wrap `await db.commit()` in `try...except IntegrityError` to return 400 with Egyptian Arabic message on race duplicate.
4. Verify by running `pytest tests/integration/test_user_auth_endpoints.py`.
Document changes in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m1_fix\changes.md` and handoff in `c:\Users\L0Q\Desktop\graduation project\.agents\teamwork\worker_m1_fix\handoff.md`.
When finished, send a message to your parent orchestrator.
