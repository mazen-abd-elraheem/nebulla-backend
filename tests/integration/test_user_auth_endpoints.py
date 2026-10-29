"""
Comprehensive Integration Tests for User Authentication, Registration, Login,
Neural Face ID Biometrics, Password Recovery, and User-scoped Personalities.
"""

import io
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from PIL import Image
from unittest.mock import patch

from app.main import app
from app.db.session import init_db


def _create_jpeg_bytes(color=(210, 150, 110)) -> bytes:
    """Create a minimal JPEG in memory."""
    img = Image.new("RGB", (100, 100), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _rand_email(prefix="user") -> str:
    """Generate a unique email for test isolation."""
    return f"{prefix}_{uuid.uuid4().hex[:8]}@synth-core.ai"


@pytest.mark.asyncio
async def test_user_registration_and_validation():
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        test_email = _rand_email("dr.khaledi")
        payload = {
            "full_name": "د. عبد الرحمن الخالدي",
            "email": test_email,
            "password": "SecurePassword123",
            "confirm_password": "SecurePassword123",
            "terms_accepted": True,
        }
        # 1. Successful registration matching UI screen 2
        res = await client.post("/api/v1/auth/register", json=payload)
        assert res.status_code == 201, res.text
        data = res.json()
        assert "access_token" in data
        assert data["user"]["full_name"] == "د. عبد الرحمن الخالدي"
        assert data["user"]["email"] == test_email
        assert data["user"]["is_active"] is True

        # 2. Duplicate email rejected
        res_dup = await client.post("/api/v1/auth/register", json=payload)
        assert res_dup.status_code == 400
        assert "مسجل بالفعل" in res_dup.json()["detail"]

        # 3. Password mismatch validation
        bad_confirm = payload.copy()
        bad_confirm["email"] = _rand_email("mismatch")
        bad_confirm["confirm_password"] = "MismatchedPassword123"
        res_mismatch = await client.post("/api/v1/auth/register", json=bad_confirm)
        assert res_mismatch.status_code == 422

        # 4. Terms rejected validation
        bad_terms = payload.copy()
        bad_terms["email"] = _rand_email("noterms")
        bad_terms["terms_accepted"] = False
        res_terms = await client.post("/api/v1/auth/register", json=bad_terms)
        assert res_terms.status_code == 422

        # 5. Short/weak password rejected
        bad_pwd = payload.copy()
        bad_pwd["email"] = _rand_email("weak")
        bad_pwd["password"] = "short"
        bad_pwd["confirm_password"] = "short"
        res_weak = await client.post("/api/v1/auth/register", json=bad_pwd)
        assert res_weak.status_code == 422


@pytest.mark.asyncio
async def test_user_login_and_remember_me():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        user_email = _rand_email("sarah.eng")
        reg_payload = {
            "full_name": "سارة المهندس",
            "email": user_email,
            "password": "Password2026",
            "confirm_password": "Password2026",
            "terms_accepted": True,
        }
        await client.post("/api/v1/auth/register", json=reg_payload)

        # Standard login (remember_me=False -> 8 hours = 28,800s)
        res_login_short = await client.post(
            "/api/v1/auth/login",
            json={
                "email": user_email,
                "password": "Password2026",
                "remember_me": False,
            },
        )
        assert res_login_short.status_code == 200
        assert res_login_short.json()["expires_in"] == 28800
        token_short = res_login_short.json()["access_token"]

        # Extended login (remember_me=True -> 30 days = 2,592,000s)
        res_login_long = await client.post(
            "/api/v1/auth/login",
            json={
                "email": user_email,
                "password": "Password2026",
                "remember_me": True,
            },
        )
        assert res_login_long.status_code == 200
        assert res_login_long.json()["expires_in"] == 2592000

        # Wrong password rejected
        res_wrong = await client.post(
            "/api/v1/auth/login",
            json={
                "email": user_email,
                "password": "WrongPassword!",
            },
        )
        assert res_wrong.status_code == 401

        # Profile check via /auth/me
        res_me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_short}"})
        assert res_me.status_code == 200
        assert res_me.json()["email"] == user_email


@pytest.mark.asyncio
async def test_password_recovery_flow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        user_email = _rand_email("karim.test")
        reg_payload = {
            "full_name": "كريم عبد الله",
            "email": user_email,
            "password": "InitialPassword123",
            "confirm_password": "InitialPassword123",
            "terms_accepted": True,
        }
        await client.post("/api/v1/auth/register", json=reg_payload)

        # 1. Request forgot password
        res_forgot = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": user_email},
        )
        assert res_forgot.status_code == 200
        reset_token = res_forgot.json()["details"]["reset_token"]
        assert reset_token is not None

        # 2. Reset password
        res_reset = await client.post(
            "/api/v1/auth/reset-password",
            json={
                "token": reset_token,
                "new_password": "NewSecurePassword2026",
                "confirm_password": "NewSecurePassword2026",
            },
        )
        assert res_reset.status_code == 200

        # 3. Old password fails
        res_old = await client.post(
            "/api/v1/auth/login",
            json={"email": user_email, "password": "InitialPassword123"},
        )
        assert res_old.status_code == 401

        # 4. New password succeeds
        res_new = await client.post(
            "/api/v1/auth/login",
            json={"email": user_email, "password": "NewSecurePassword2026"},
        )
        assert res_new.status_code == 200


@pytest.mark.asyncio
async def test_neural_face_id_biometric_login():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        user_email = _rand_email("tarek.face")
        reg_payload = {
            "full_name": "طارق محمود",
            "email": user_email,
            "password": "Password123",
            "confirm_password": "Password123",
            "terms_accepted": True,
        }
        reg_res = await client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_res.status_code == 201, reg_res.text
        token = reg_res.json()["access_token"]

        test_face_embedding = [0.1] * 128
        different_embedding = [-0.1] * 128
        face_img_bytes = _create_jpeg_bytes()

        # 1. Link face to account
        with patch("app.services.vision.face_service.FaceService.extract_embedding_sync", return_value=test_face_embedding):
            files = {"file": ("my_face.jpg", face_img_bytes, "image/jpeg")}
            link_res = await client.post(
                "/api/v1/auth/biometric/link",
                files=files,
                headers={"Authorization": f"Bearer {token}"},
            )
            assert link_res.status_code == 200

        # 2. Biometric Login matching face (1:1)
        with patch("app.services.vision.face_service.FaceService.extract_embedding_sync", return_value=test_face_embedding):
            files = {"file": ("live_face.jpg", face_img_bytes, "image/jpeg")}
            data = {"email": user_email}
            bio_res = await client.post("/api/v1/auth/login/biometric", data=data, files=files)
            assert bio_res.status_code == 200
            assert "access_token" in bio_res.json()
            assert bio_res.json()["user"]["has_biometric"] is True

        # 3. Biometric Login with mismatched face fails
        with patch("app.services.vision.face_service.FaceService.extract_embedding_sync", return_value=different_embedding):
            files = {"file": ("intruder_face.jpg", face_img_bytes, "image/jpeg")}
            data = {"email": user_email}
            fail_res = await client.post("/api/v1/auth/login/biometric", data=data, files=files)
            assert fail_res.status_code == 401
            assert "غير متطابقة" in fail_res.json()["detail"]


@pytest.mark.asyncio
async def test_personality_user_isolation():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Create User Alpha
        alpha_email = _rand_email("user.alpha")
        alpha_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "المستخدم الأول",
                "email": alpha_email,
                "password": "PasswordAlpha123",
                "confirm_password": "PasswordAlpha123",
                "terms_accepted": True,
            },
        )
        assert alpha_reg.status_code == 201, alpha_reg.text
        alpha_token = alpha_reg.json()["access_token"]
        alpha_headers = {"Authorization": f"Bearer {alpha_token}"}

        # Create User Beta
        beta_email = _rand_email("user.beta")
        beta_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "full_name": "المستخدم الثاني",
                "email": beta_email,
                "password": "PasswordBeta123",
                "confirm_password": "PasswordBeta123",
                "terms_accepted": True,
            },
        )
        assert beta_reg.status_code == 201, beta_reg.text
        beta_token = beta_reg.json()["access_token"]
        beta_headers = {"Authorization": f"Bearer {beta_token}"}

        # User Alpha creates a personality
        p_res = await client.post(
            "/api/v1/personalities/",
            json={
                "name": "نيبولا ألفا الخاص",
                "description": "شخصية خاصة بالمستخدم ألفا",
                "system_prompt": "أنت مساعد ألفا الشخصي.",
            },
            headers=alpha_headers,
        )
        assert p_res.status_code == 201
        alpha_p_id = p_res.json()["id"]
        assert p_res.json()["user_id"] == alpha_reg.json()["user"]["id"]

        # User Alpha sees their own personality + default personality
        alpha_list = await client.get("/api/v1/personalities/", headers=alpha_headers)
        alpha_ids = [p["id"] for p in alpha_list.json()["personalities"]]
        assert alpha_p_id in alpha_ids

        # User Beta DOES NOT see Alpha's private personality
        beta_list = await client.get("/api/v1/personalities/", headers=beta_headers)
        beta_ids = [p["id"] for p in beta_list.json()["personalities"]]
        assert alpha_p_id not in beta_ids

        # User Beta cannot access or modify Alpha's personality
        forbidden_get = await client.get(f"/api/v1/personalities/{alpha_p_id}", headers=beta_headers)
        assert forbidden_get.status_code == 403

        forbidden_patch = await client.patch(
            f"/api/v1/personalities/{alpha_p_id}",
            json={"name": "محاولة تعديل غير مصرح بها"},
            headers=beta_headers,
        )
        assert forbidden_patch.status_code == 403

        forbidden_delete = await client.delete(f"/api/v1/personalities/{alpha_p_id}", headers=beta_headers)
        assert forbidden_delete.status_code == 403

        # User Alpha can update and delete their own personality
        ok_patch = await client.patch(
            f"/api/v1/personalities/{alpha_p_id}",
            json={"name": "نيبولا ألفا المطور"},
            headers=alpha_headers,
        )
        assert ok_patch.status_code == 200
        assert ok_patch.json()["name"] == "نيبولا ألفا المطور"

        ok_delete = await client.delete(f"/api/v1/personalities/{alpha_p_id}", headers=alpha_headers)
        assert ok_delete.status_code == 204
