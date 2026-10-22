"""
API Integration tests for RAG + LLM Chat endpoints.
Tests /api/v1/conversations/chat, /api/v1/conversations/chat/stream, and /api/v1/memories/search.
"""

import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings


@pytest.fixture
def auth_headers():
    return {"X-API-Key": settings.PAIRING_SECRET}


@pytest.mark.asyncio
async def test_api_chat_with_rag_empty_memory():
    """Test POST /api/v1/conversations/chat returns valid response structure."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "message": "أهلاً، من أنت؟",
            "personality_id": None,
        }
        r = await client.post("/api/v1/conversations/chat", json=payload)
        assert r.status_code == 200
        data = r.json()
        assert "response" in data
        assert "retrieved_memories" in data
        assert "session_id" in data
        assert "latency" in data
        assert isinstance(data["retrieved_memories"], list)


@pytest.mark.asyncio
async def test_api_add_memory_and_retrieve_via_chat(auth_headers):
    """
    Test adding a new memory via /api/v1/memories/ and verifying that
    /api/v1/conversations/chat grounds its response with that memory.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Add unique memory
        unique_fact = "الروبوت نيبولا يمتلك 12 محرك سيرفو متطور للغاية"
        mem_res = await client.post(
            "/api/v1/memories/",
            json={
                "content": unique_fact,
                "personality_id": 1,
                "source": "api_test",
                "importance": 5,
            },
            headers=auth_headers,
        )
        assert mem_res.status_code == 201
        mem_id = mem_res.json()["id"]

        try:
            # 2. Search memories via RAG API endpoint
            search_res = await client.get(
                "/api/v1/memories/search",
                params={"q": "كم محرك سيرفو يمتلك نيبولا؟", "personality_id": 1},
                headers=auth_headers,
            )
            assert search_res.status_code == 200
            search_data = search_res.json()
            assert any(unique_fact in m for m in search_data["results"])

            # 3. Chat with LLM grounded by RAG
            chat_res = await client.post(
                "/api/v1/conversations/chat",
                json={
                    "message": "كم محرك سيرفو يمتلك نيبولا؟",
                    "personality_id": 1,
                },
                headers=auth_headers,
            )
            assert chat_res.status_code == 200
            chat_data = chat_res.json()
            # Verify that the memory was retrieved and injected into the LLM context
            assert any("سيرفو" in m for m in chat_data["retrieved_memories"])
            assert len(chat_data["response"]) > 0

        finally:
            # Cleanup memory
            await client.delete(f"/api/v1/memories/{mem_id}", headers=auth_headers)


@pytest.mark.asyncio
async def test_api_chat_streaming():
    """Test POST /api/v1/conversations/chat/stream returns SSE chunks."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {
            "message": "صباح الخير",
        }
        r = await client.post("/api/v1/conversations/chat/stream", json=payload)
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        text = r.text
        assert "data:" in text
