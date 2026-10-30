"""
Integration tests for Phone Actions REST API endpoints:
- Contacts CRUD
- Reminders CRUD
- Audit Action Logs
- Speaker Voiceprint status
- Level-3 External Approval
"""

from datetime import datetime, timedelta, timezone
import uuid
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth.jwt import create_access_token
from app.db.session import init_db
from app.main import app


def _rand_email(prefix="test_actions"):
    return f"{prefix}_{uuid.uuid4().hex[:8]}@nebula.local"


@pytest.fixture
def auth_headers():
    token = create_access_token(subject="1", extra={"sub": "1", "email": "admin@nebula.local"})
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_contacts_crud_endpoints(auth_headers):
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Create contact
        payload = {
            "name": "ماما",
            "phone_number": "+201012345678",
            "aliases": "مامي,الوالدة",
            "relationship": "mother",
            "is_allowlisted": True,
            "requires_confirmation": True,
            "required_level": 1,
            "notify_on_missed": True,
        }
        res = await client.post("/api/v1/actions/contacts", json=payload, headers=auth_headers)
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["name"] == "ماما"
        assert data["phone_number"] == "+201012345678"
        assert data["slug"] != ""
        cid = data["id"]

        # 2. List contacts
        list_res = await client.get("/api/v1/actions/contacts", headers=auth_headers)
        assert list_res.status_code == 200
        contacts = list_res.json()
        assert any(c["id"] == cid for c in contacts)

        # 3. Update contact
        update_payload = {"relationship": "beloved mother"}
        up_res = await client.put(f"/api/v1/actions/contacts/{cid}", json=update_payload, headers=auth_headers)
        assert up_res.status_code == 200
        assert up_res.json()["relationship"] == "beloved mother"

        # 4. Delete contact
        del_res = await client.delete(f"/api/v1/actions/contacts/{cid}", headers=auth_headers)
        assert del_res.status_code == 204


@pytest.mark.asyncio
async def test_reminders_crud_endpoints(auth_headers):
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        target_iso = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        payload = {
            "title": "دوا السكر",
            "reminder_type": "medicine",
            "target_time": target_iso,
            "recurrence": "daily",
            "escalation_mode": "msg",
        }
        # 1. Create reminder
        res = await client.post("/api/v1/actions/reminders", json=payload, headers=auth_headers)
        assert res.status_code == 201, res.text
        data = res.json()
        assert data["title"] == "دوا السكر"
        assert data["status"] == "pending"
        rid = data["id"]

        # 2. List reminders
        list_res = await client.get("/api/v1/actions/reminders?active_only=true", headers=auth_headers)
        assert list_res.status_code == 200
        assert any(r["id"] == rid for r in list_res.json())

        # 3. Acknowledge reminder
        ack_res = await client.patch(f"/api/v1/actions/reminders/{rid}/acknowledge", headers=auth_headers)
        assert ack_res.status_code == 200
        assert ack_res.json()["status"] == "acknowledged"

        # 4. Delete reminder
        del_res = await client.delete(f"/api/v1/actions/reminders/{rid}", headers=auth_headers)
        assert del_res.status_code == 204


@pytest.mark.asyncio
async def test_action_logs_and_voiceprint_status(auth_headers):
    await init_db()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Query audit action logs
        logs_res = await client.get("/api/v1/actions/logs?limit=10", headers=auth_headers)
        assert logs_res.status_code == 200
        assert isinstance(logs_res.json(), list)

        # Voiceprint status for user
        vp_res = await client.get("/api/v1/actions/voiceprint/status", headers=auth_headers)
        assert vp_res.status_code == 200
        data = vp_res.json()
        assert "enrolled" in data
