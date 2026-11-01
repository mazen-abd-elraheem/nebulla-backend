"""
Unit tests for RAG + LLM integration and prompt builder.
"""

from app.providers.llm.prompt_builder import (
    build_rag_system_prompt,
    build_rag_messages,
    build_personality_prompt,
    render_dynamic_template,
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


def test_build_personality_prompt_dynamic():
    p_dict = {
        "name": "كليو",
        "description": "مساعد صوتي ذكي للروبوت",
        "dialect": "alex",
        "language_mix": "ar_en",
        "system_prompt": "دايماً خليك متفائل وبتهزر.",
    }
    persona_p = build_personality_prompt(personality=p_dict, user_name="سارة")
    assert "كليو" in persona_p
    assert "الإسكندرانية" in persona_p
    assert "سارة" in persona_p
    assert "متفائل وبتهزر" in persona_p


def test_render_dynamic_template():
    rendered = render_dynamic_template(
        "أهلاً يا {user_name}، نسبة البطارية {battery}% والمسافة {distance} سم.",
        {"user_name": "عمر", "battery": 88, "distance": 40},
    )
    assert "عمر" in rendered
    assert "88" in rendered
    assert "40" in rendered


def test_dynamic_rag_detailed_context_and_device_state():
    detailed_mems = [
        {
            "content": "الروبوت يحب متابعة كرة القدم والأهلي",
            "score": 0.932,
            "source": "conversation",
            "created_at": "2026-10-23T01:00:00",
        },
        "الروبوت متصل بشبكة الواي فاي المنزلية",
    ]
    rag_p = build_rag_system_prompt(
        context=detailed_mems,
        personality={"name": "كليو", "dialect": "cairo"},
        device_state={"battery_voltage": 12.3, "distance_cm": 25},
        user_name="عمر",
    )
    assert "93%" in rag_p
    assert "المصدر: محادثة سابقة" in rag_p
    assert "الروبوت متصل بشبكة الواي فاي المنزلية" in rag_p
    assert "12.3V" in rag_p
    assert "25 سم" in rag_p


def test_rag_service_lexical_scoring():
    rag = RAGService()
    score_high = rag._lexical_score("أحمد مهندس", "أحمد يعمل مهندس برمجيات في الشركة")
    score_zero = rag._lexical_score("الطقس اليوم", "أحمد يعمل مهندس برمجيات")
    assert score_high > 0.0
    assert score_zero == 0.0



def test_rag_service_arabic_stemming_and_variants():
    rag = RAGService()
    # Test pronoun suffixes (ك, ي, نا)
    tokens_ismak = rag._tokenize("ما هو اسمك؟")
    assert "اسم" in tokens_ismak

    # Test spelling variants
    tok_nebula1 = rag._tokenize("نيبولا")
    tok_nebula2 = rag._tokenize("نيبيولا")
    assert tok_nebula1.intersection(tok_nebula2) == {"نيبولا"}

    # Test conversational question expansion
    tok_meen = rag._tokenize("مين انت؟")
    assert "روبوت" in tok_meen
    assert "اسم" in tok_meen


def test_rag_deduplication_before_top_k():
    rag = RAGService()
    from unittest.mock import MagicMock
    mem1 = MagicMock(id=1, content="اسم الروبوت هو نيبيولا ومهمته هي المساعدة والتحكم الذكي في الأجهزة.")
    mem2 = MagicMock(id=2, content="اسم الروبوت هو نيبيولا ومهمته هي المساعدة والتحكم الذكي في الأجهزة.")
    mem3 = MagicMock(id=3, content="اسم الروبوت هو نيبيولا ومهمته هي المساعدة والتحكم الذكي في الأجهزة.")
    mem4 = MagicMock(id=4, content="الروبوت نيبولا يمتلك 12 محرك سيرفو فائق الدقة.")
    mem5 = MagicMock(id=5, content="الروبوت مزود بكاميرا تتبع الوجوه.")

    scored = [
        (0.95, mem1),
        (0.95, mem2),
        (0.95, mem3),
        (0.85, mem4),
        (0.80, mem5),
    ]

    top_k = 3
    seen = set()
    unique_top = []
    for score, mem in scored:
        norm = rag._normalize_for_dedup(mem.content)
        if norm not in seen:
            seen.add(norm)
            unique_top.append(mem)
            if len(unique_top) >= top_k:
                break

    assert len(unique_top) == 3
    assert unique_top[0].id == 1
    assert unique_top[1].id == 4
    assert unique_top[2].id == 5


def test_rag_load_memories_sync():
    rag = RAGService()
    mems = rag._load_memories_sync(personality_id=1)
    assert len(mems) > 0
    assert any(m.id == 1 for m in mems)
