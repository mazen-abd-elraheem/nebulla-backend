"""Integration tests — FastAPI app endpoints."""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings


@pytest.fixture
def auth_headers():
    """Provide a valid API key header."""
    return {"X-API-Key": settings.PAIRING_SECRET}


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_auth_token_exchange(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/auth/token", json={
            "pairing_code": settings.PAIRING_SECRET,
            "device_name": "test_device",
        })
    assert r.status_code == 200
    assert "access_token" in r.json()


@pytest.mark.asyncio
async def test_bad_pairing_code_rejected():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/auth/token", json={
            "pairing_code": "wrong-code",
            "device_name": "attacker",
        })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_devices_status(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.get("/api/v1/devices/status", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert "phone" in data["channels"]
    assert "esp32" in data["channels"]


@pytest.mark.asyncio
async def test_emergency_stop(auth_headers):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/diagnostics/emergency-stop", headers=auth_headers)
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_voice_clone_test_no_sample(auth_headers):
    """Voice clone test endpoint should respond even without a saved sample."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post("/api/v1/voice-clone/test", headers=auth_headers)
    # Should return WAV audio (or 200 with some content)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/")
