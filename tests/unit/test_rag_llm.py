"""
Unit tests for RAG + LLM integration and prompt builder.
"""

from app.providers.llm.prompt_builder import (
    build_rag_system_prompt,
    build_rag_messages,
    DEFAULT_SYSTEM_PROMPT,
)
from app.services.memory.rag_service import RAGService


def test_build_rag_system_prompt_empty():
    prompt = build_rag_system_prompt(context=[], system_prompt=None)
    assert DEFAULT_SYSTEM_PROMPT in prompt
    assert "RAG Context" not in prompt


def test_build_rag_system_prompt_with_context():
    context = ["صاحب المشروع اسمه أحمد", "تخرج من هندسة القاهرة عام 2024"]
    custom_sys = "أنت مساعد ذكي."
    prompt = build_rag_system_prompt(context=context, system_prompt=custom_sys)
    assert "أنت مساعد ذكي." in prompt
    assert "RAG Context" in prompt
    assert "صاحب المشروع اسمه أحمد" in prompt
    assert "تخرج من هندسة القاهرة عام 2024" in prompt


def test_build_rag_messages():
    context = ["الروبوت يدعى Nebula"]
    messages = build_rag_messages(
        prompt="ما هو اسمك؟",
        context=context,
        system_prompt="أنت روبوت مفيد.",
    )
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "Nebula" in messages[0]["content"]
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "ما هو اسمك؟"


def test_rag_service_lexical_scoring():
    rag = RAGService()
    score_high = rag._lexical_score("أحمد مهندس", "أحمد يعمل مهندس برمجيات في الشركة")
    score_zero = rag._lexical_score("الطقس اليوم", "أحمد يعمل مهندس برمجيات")
    assert score_high > 0.0
    assert score_zero == 0.0
