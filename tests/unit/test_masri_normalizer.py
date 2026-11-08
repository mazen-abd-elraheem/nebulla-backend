"""
Unit tests for Egyptian Arabic (Masri) Dialect & Code-Switching Normalizer
"""

import pytest
from app.utils.masri_normalizer import clean_llm_output_for_speech, MasriNormalizer


def test_code_switching_definite_article_spacing():
    """Arabic definite article (ال / الـ) must cleanly separate from English words."""
    norm = MasriNormalizer()
    assert "ال ID" in norm.normalize("الID الخاص بيك")
    assert "ال ID" in norm.normalize("الـID بتاعك جاهز")
    assert "بال API" in norm.normalize("اتصلت بالـAPI")
    assert "لل system" in norm.normalize("تعديل للـsystem")


def test_code_switching_transition_pause():
    """Insert micro-pause comma (،) after English word before Arabic text."""
    norm = MasriNormalizer()
    res = norm.normalize("عندي meeting بكرة الصبح")
    assert "meeting،" in res or "meeting ،" in res


def test_formal_fusha_to_masri_and_tashkeel():
    """Formal phrases replaced with colloquial Egyptian or explicit Tashkeel."""
    norm = MasriNormalizer()
    res1 = norm.normalize("اتكلم معايا بالعامية المصرية")
    assert "بِالعَامِّيَّة المَصْرِيَّة" in res1

    res2 = norm.normalize("يرجى الانتظار دقيقة")
    assert "ثواني خليك معايا" in res2

    res3 = norm.normalize("العملية تم بنجاح")
    assert "اتعمل" in res3 and "تَمامْ" in res3


def test_numbers_and_clock_times_to_egyptian_words():
    """Numbers and times convert into Egyptian Arabic words."""
    norm = MasriNormalizer()
    res_time = norm.normalize("الساعة 3:30")
    assert "تَلَاتَة و نُصّ" in res_time

    res_num = norm.normalize("معايا 250 جنيه")
    assert "مِتِين" in res_num and "خَمْسِين" in res_num
    assert "جنيه" in res_num


def test_clean_llm_output_for_speech_strips_tags():
    """Strip chain-of-thought, action tags, and normalize speech."""
    raw = "<think>Internal thinking</think>[action:nod] أهلاً بيك يا فندم بالـAPI الساعة 4:15"
    cleaned = clean_llm_output_for_speech(raw)
    assert "<think>" not in cleaned
    assert "[action:nod]" not in cleaned
    assert "بال API" in cleaned
    assert "أَرْبَعَه و رُبع" in cleaned


def test_quote_and_url_shielding():
    """Protected quotes, URLs, and code blocks must remain uncorrupted by dialect transforms."""
    norm = MasriNormalizer()
    text = 'قال لي "لا تقلق سوف أساعدك" وزور https://example.com/api'
    res = norm.normalize(text)
    # The text inside quotes is protected from "ماتقلقش" / "هساعدك"
    assert '"لا تقلق سوف أساعدك"' in res
    assert "https://example.com/api" in res


def test_egyptian_phone_numbers_speech():
    """Egyptian mobile numbers should expand into natural spoken digit words."""
    norm = MasriNormalizer()
    res = norm.normalize("رقمي هو 01012345678 كلمني")
    assert "صفر واحد صفر واحد اتنين تلاتة أربعة خمسة ستة سبعة تمانية" in res


def test_egyptian_dual_and_countable_plurals():
    """Colloquial Egyptian duals and 3-10 plural truncation."""
    norm = MasriNormalizer()
    res_dual = norm.normalize("فاضل 2 يوم و 2 ساعة و 2 جنيه")
    assert "يومين" in res_dual
    assert "ساعتين" in res_dual
    assert "جنيهين" in res_dual

    res_plural = norm.normalize("عشت هناك 3 سنين و 5 شهور")
    assert "تلات سنين" in res_plural
    assert "خمس شهور" in res_plural


def test_contextual_verbal_negations_and_modals():
    """Authentic Masri verbal negation and modal conversion."""
    norm = MasriNormalizer()
    assert "مش هقدر" in norm.normalize("أنا لا أستطيع الخروج")
    assert "ماعرفش" in norm.normalize("أنا لا أعرف الإجابة")
    assert "معنديش" in norm.normalize("ليس لدي رصيد")
    assert "مفيش" in norm.normalize("لا يوجد حل آخر")
    assert "هساعدك" in norm.normalize("سوف أساعدك حالا")
    assert "لازم" in norm.normalize("يجب أن ترتاح")

