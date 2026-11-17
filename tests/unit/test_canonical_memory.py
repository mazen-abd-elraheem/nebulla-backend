import sys
sys.path.insert(0, ".")
import asyncio
from app.db.session import AsyncSessionLocal
from app.api.v1.endpoints.conversations import chat_with_llm, ChatRequest
from app.services.memory.chat_memory_extractor import ChatMemoryExtractor
from app.services.memory.fact_verifier import FactVerifier
from starlette.requests import Request

async def main():
    # 1. Test extractor parsing
    res = ChatMemoryExtractor.process_message("عدل وظيفة مصعب خليه طيار")
    assert res is not None
    assert res["action"] == "update"
    assert res["new_fact"] == "مصعب شغال طيار"
    print("Test 1 (Extractor Normalization): PASSED ->", res["new_fact"])

    # 2. Test chat_with_llm for asking about Mosaab's job
    req = Request({"type": "http", "headers": []})
    async with AsyncSessionLocal() as db:
        chat_req = ChatRequest(message="مصعب شغال ايه؟", stream=False)
        resp = await chat_with_llm(request=req, body=chat_req, db=db, _user="dev_user")
        print("Retrieved memories:", resp.retrieved_memories)
        assert "مصعب شغال طيار" in resp.retrieved_memories
        assert "خليه" not in resp.retrieved_memories[0]

        # Test FactVerifier with mock LLM reply
        sanitized = FactVerifier.verify_and_sanitize(
            query="مصعب شغال ايه؟",
            response="مصعب شغال طيار. [happy]",
            retrieved_memories=resp.retrieved_memories,
        )
        print("FactVerifier Output:", sanitized)
        assert "مصعب شغال طيار" in sanitized

    print("ALL CANONICAL TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
