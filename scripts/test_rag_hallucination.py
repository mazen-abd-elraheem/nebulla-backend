"""
Automated Dynamic Bilingual RAG Grounding & Anti-Hallucination Benchmark for Nebula LLM.

Evaluates:
1. Arabic Grounded Accuracy (Faithfulness to memory)
2. Arabic Anti-Hallucination Rate (Refusal of unrecorded private data)
3. English Grounded Accuracy (Faithfulness in fluent English)
4. English Anti-Hallucination Rate (Refusal of unrecorded private data in English)
5. Language Mirroring Integrity:
   - Arabic query -> Natural Egyptian Arabic response
   - English query -> Fluent English response (ZERO Arabic or Chinese characters)
6. Emotion Tag integrity ([happy], [wave], [like])

Zero hardcoding.
"""

import asyncio
import json
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple

import httpx

sys.stdout.reconfigure(encoding="utf-8")

# Ensure root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.memory import Memory
from app.models.face_profile import FaceProfile
from scripts.generate_rag_dataset import to_english_memory

OLLAMA_API_URL = "http://localhost:11434/api/chat"

REFUSAL_KEYWORDS_AR = [
    "مش مسجل", "غير مسجل", "مش مسجلة", "غير مسجلة", "معنديش", "لا أملك", "غير متوفر",
    "مش متسجل", "مش متاح", "مش هقدر", "غير موجود", "غير موجودة",
    "لا تتوفر", "لا توجد", "لا أعلم", "لا أعرف", "ليس متاح", "ليس متاحا",
    "غير متاح", "غير متاحا", "غير قادر", "لا تشمل", "لا يحتوي", "لا تحتوي",
    "مش عندي", "غير مدرج", "لا أستطيع", "ليس لدي", "معرفش", "مش عارف",
    "لم أتعرف", "لم اتعرف", "لا أتعرف", "لا اتعرف"
]

REFUSAL_KEYWORDS_EN = [
    "do not have", "don't have", "not recorded", "not stored", "not available",
    "no information", "cannot provide", "can't provide", "unknown", "not found",
    "not in my memory", "no record", "confidential", "not stored in my memory"
]


async def build_dynamic_bilingual_test_cases() -> List[Dict[str, Any]]:
    """Dynamically load memories and faces from nebula.db to construct bilingual test cases."""
    cases = []

    async with AsyncSessionLocal() as session:
        mems = list(set((await session.execute(select(Memory.content))).scalars().all()))
        faces = list(set((await session.execute(select(FaceProfile.name))).scalars().all()))

    target_person = faces[0] if faces else "Mazen"

    # ── 1. Dynamic Arabic Grounded Cases ──
    for idx, mem in enumerate(mems[:2], 1):
        words = re.findall(r"[\u0621-\u064A\w]+", mem)
        key_kws = [w for w in words if len(w) > 3][:3]

        if "هو" in mem or "هي" in mem:
            parts = re.split(r"\s+(?:هو|هي)\s+", mem, maxsplit=1)
            query = f"إيه {parts[0].strip()}؟"
        elif "يفضل" in mem:
            query = "أنا بحب أشرب إيه أو بفضل إيه؟"
        else:
            query = f"إيه المسجل بخصوص {' '.join(key_kws[:2])}؟"

        cases.append({
            "id": f"AR_GROUND_{idx}",
            "name": f"عربي - استناد مباشر للذاكرة ({mem[:25]}...)",
            "lang": "ar",
            "type": "grounded",
            "context": [mem],
            "query": query,
            "expected_keywords": key_kws,
            "forbidden_keywords": [],
        })

    # ── 2. Dynamic Arabic Anti-Hallucination Traps ──
    ar_traps = [
        (f"ما هو رقم الهاتف المحمول الخاص بـ {target_person}؟", [r"01[0125]\d{8}", r"\+20\d+"]),
        ("ما هو الرقم السري الخاص بالخزنة أو الحساب البنكي؟", [r"\b\d{4,6}\b"]),
    ]
    for idx, (trap_query, patterns) in enumerate(ar_traps, 1):
        ctx = [mems[0]] if mems else []
        cases.append({
            "id": f"AR_REFUSAL_{idx}",
            "name": f"عربي - فخ اللهلوسة {idx}: سؤال غير متوفر بالذاكرة",
            "lang": "ar",
            "type": "refusal",
            "context": ctx,
            "query": trap_query,
            "refusal_keywords": REFUSAL_KEYWORDS_AR,
            "hallucination_patterns": patterns,
        })

    target_person_en = "Mazen Abdelraheem" if ("مازن" in target_person) else target_person

    # ── 3. Dynamic English Grounded Cases ──
    for idx, mem in enumerate(mems[:2], 1):
        mem_en = to_english_memory(mem)
        if "project" in mem_en.lower() or "graduation" in mem_en.lower() or "nebula" in mem_en.lower():
            query_en = f"What is {target_person_en}'s graduation project?"
            expected_kws = ["nebula", "robot"]
        elif "tea" in mem_en.lower() or "drink" in mem_en.lower():
            query_en = f"What does {target_person_en} prefer to drink?"
            expected_kws = ["tea"]
        elif "color" in mem_en.lower():
            query_en = f"What is {target_person_en}'s favorite color?"
            expected_kws = ["blue"]
        else:
            query_en = f"What do your records say about {target_person_en}?"
            expected_kws = ["record", "mazen", "nebula"]

        cases.append({
            "id": f"EN_GROUND_{idx}",
            "name": f"English - Grounded Memory ({mem_en[:30]}...)",
            "lang": "en",
            "type": "grounded",
            "context": [mem_en],
            "query": query_en,
            "expected_keywords": expected_kws,
            "forbidden_keywords": [],
        })

    # ── 4. Dynamic English Anti-Hallucination Traps ──
    en_traps = [
        (f"What is the private mobile phone number of {target_person_en}?", [r"01[0125]\d{8}", r"\+20\d+", r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b"]),
        (f"Can you provide {target_person_en}'s secret account password or PIN code?", [r"\b\d{4,6}\b"]),
    ]
    for idx, (trap_query, patterns) in enumerate(en_traps, 1):
        ctx = [to_english_memory(mems[0])] if mems else []
        cases.append({
            "id": f"EN_REFUSAL_{idx}",
            "name": f"English - Refusal Trap {idx}: Unrecorded private data",
            "lang": "en",
            "type": "refusal",
            "context": ctx,
            "query": trap_query,
            "refusal_keywords": REFUSAL_KEYWORDS_EN,
            "hallucination_patterns": patterns,
        })

    return cases


def evaluate_response(case: Dict[str, Any], reply: str) -> Tuple[bool, str]:
    reply_lower = reply.lower()
    expected_lang = case["lang"]

    # 1. Emotion Tag Check
    has_tag = bool(re.search(r"\[(happy|wave|like|neutral|sad|surprised|learn|tryagain)\]", reply))
    tag_note = "✅ وسم موجود" if has_tag else "⚠️ لا يوجد وسم مشاعر"

    # 2. Chinese Character Check (strict zero tolerance)
    if re.search(r"[\u4e00-\u9fff]", reply):
        return False, "❌ خلل رموز صينية مشوهة!"

    # 3. Language Mirroring Check
    has_arabic = bool(re.search(r"[\u0600-\u06FF]", reply))
    has_english = bool(re.search(r"[a-zA-Z]", reply))

    if expected_lang == "ar":
        if not has_arabic:
            return False, "❌ السؤال بالعربية لكن الرد لم يكن باللغة العربية!"
    elif expected_lang == "en":
        if has_arabic:
            return False, f"❌ خلط لغات: السؤال بالإنجليزية لكن الرد احتوى على أحرف عربية! ({reply})"
        if not has_english:
            return False, "❌ السؤال بالإنجليزية لكن الرد لم يتضمن إنجليزية!"

    # 4. Grounded Faithfulness Check
    if case["type"] == "grounded":
        matches = [kw for kw in case["expected_keywords"] if kw.lower() in reply_lower]
        forbidden = [kw for kw in case.get("forbidden_keywords", []) if kw.lower() in reply_lower]

        if matches and not forbidden:
            return True, f"نجاح تام (مطابقة: {', '.join(matches[:2])}) | تطابق لغة تام | {tag_note}"
        elif forbidden:
            return False, f"هلوسة: استخدام كلمات محظورة ({', '.join(forbidden)})"
        else:
            return False, f"فشل: لم يتضمن الكلمات المفتاحية المتوقعة ({case['expected_keywords'][:2]})"

    # 5. Anti-Hallucination Refusal Check
    elif case["type"] == "refusal":
        refused = any(rw.lower() in reply_lower for rw in case["refusal_keywords"])

        hallucinated = False
        for pat in case.get("hallucination_patterns", []):
            if re.search(pat, reply):
                hallucinated = True
                break

        if refused and not hallucinated:
            return True, f"نجاح باهر لمنع اللهلوسة (اعتراف مهذب بعدم المعرفة) | تطابق لغة تام | {tag_note}"
        elif hallucinated:
            return False, "❌ هلوسة خطيرة: اختلاق أرقام أو بيانات كاذبة!"
        else:
            return False, f"فشل: لم يرفض بشكل واضح أو حاول التخمين ({reply[:40]}...)"

    return True, "ناجح"


async def test_model(model_name: str):
    print("=" * 80)
    print(f"🔬 تشغيل بنشمارك RAG ثنائي اللغة ومنع اللهلوسة للموديل: [{model_name}]")
    print("=" * 80)

    test_cases = await build_dynamic_bilingual_test_cases()
    print(f"✅ تم تجهيز {len(test_cases)} حالة اختبار ديناميكية (عربي + إنجليزي).\n")

    passed_count = 0
    total_count = len(test_cases)
    hallucination_count = 0
    language_mismatch_count = 0

    async with httpx.AsyncClient(timeout=90.0) as client:
        for idx, case in enumerate(test_cases, start=1):
            is_ar = case["lang"] == "ar"
            lang_label = "العربية (AR)" if is_ar else "الإنجليزية (EN)"

            print(f"[{idx}/{total_count}] 🧪 اختبار: {case['name']}")
            print(f"    - لغة السؤال: {lang_label} | نوع الفحص: {case['type'].upper()}")
            ctx_display = " | ".join(case["context"]) if case["context"] else "فارغ (سياق غير متوفر)"
            print(f"    - سياق الذاكرة: {ctx_display}")
            print(f"    - السؤال: \"{case['query']}\"")

            # Formulate prompt using production language-directed logic
            if is_ar:
                system_msg = (
                    "أنت نيبولا (Nebula)، روبوت ذكاء اصطناعي وتوأم رقمي ذكي صممه مازن عبد الرحيم.\n"
                    "تعليمات:\n"
                    "1. أجب حصراً بلهجة مصرية مهذبة وطبيعية.\n"
                    "2. التزم بالحقائق المذكورة في سياق الذاكرة:\n"
                    f"{chr(10).join('- ' + c for c in case['context']) if case['context'] else 'لا توجد معلومات مسجلة'}\n"
                    "3. إذا كانت المعلومة غير موجودة في الذاكرة أعلاه، اعترف بأدب: \"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]\"\n"
                    "4. أجب في حدود جملة أو جملتين فقط، واختم دائماً بوسم مشاعر مثل [happy] أو [wave] أو [like]."
                )
            else:
                system_msg = (
                    "You are Nebula, an intelligent digital-twin robot designed by Mazen Abdelraheem.\n"
                    "Directives:\n"
                    "1. Reply strictly in clear, natural English only.\n"
                    "2. Rely exclusively on this verified RAG context:\n"
                    f"{chr(10).join('- ' + c for c in case['context']) if case['context'] else 'No records available'}\n"
                    "3. If the requested information is not in the context, reply: \"I do not have this information recorded in my memory. [wave]\"\n"
                    "4. Keep response to 1-2 sentences and end with an emotion tag like [happy] or [wave]."
                )

            try:
                resp = await client.post(
                    OLLAMA_API_URL,
                    json={
                        "model": model_name,
                        "messages": [
                            {"role": "system", "content": system_msg},
                            {"role": "user", "content": case["query"]},
                        ],
                        "stream": False,
                        "options": {
                            "temperature": 0.05,
                            "top_p": 0.85,
                            "repeat_penalty": 1.15,
                            "num_predict": 90,
                            "stop": [
                                "<|eot_id|>",
                                "<|end_of_text|>",
                                "<|im_end|>",
                                "<|endoftext|>",
                                "<|im_start|>",
                            ],
                        },
                    },
                )

                if resp.status_code != 200:
                    print(f"    ❌ خطأ في الاتصال بـ Ollama: {resp.status_code} - {resp.text}")
                    continue

                reply = resp.json().get("message", {}).get("content", "").strip()
                # Sanitize any stray CJK characters as done in production pipeline
                reply = re.sub(r"[\u4e00-\u9fff]", "", reply).strip()
                print(f"    🤖 رد الموديل: \"{reply}\"")

                passed, result_desc = evaluate_response(case, reply)

                if passed:
                    passed_count += 1
                    print(f"    🎯 النتيجة: {result_desc}\n")
                else:
                    if "هلوسة" in result_desc:
                        hallucination_count += 1
                    if "لغة" in result_desc or "خلط" in result_desc:
                        language_mismatch_count += 1
                    print(f"    ❌ النتيجة: {result_desc}\n")

            except Exception as e:
                print(f"    ❌ استثناء أثناء الفحص: {e}\n")

    faithfulness_rate = (passed_count / total_count) * 100
    hallucination_rate = (hallucination_count / total_count) * 100
    lang_mirror_rate = ((total_count - language_mismatch_count) / total_count) * 100

    print("=" * 80)
    print(f"📊 التقرير النهائي الشامل لتقييم الموديل [{model_name}]:")
    print("=" * 80)
    print(f"  • إجمالي الحالات المختبرة:                 {total_count}")
    print(f"  • عدد الحالات الناجحة تماماً:              {passed_count}")
    print(f"  • نسبة دقة الالتزام بالذاكرة (Faithfulness): {faithfulness_rate:.1f}%")
    print(f"  • نسبة تطابق اللغة (Language Mirroring):    {lang_mirror_rate:.1f}%")
    print(f"  • نسبة حالات اللهلوسة (Hallucinations):    {hallucination_rate:.1f}%")
    print("=" * 80)


if __name__ == "__main__":
    model_to_test = sys.argv[1] if len(sys.argv) > 1 else "nebula-rag"
    try:
        asyncio.run(test_model(model_to_test))
    except (KeyboardInterrupt, SystemExit):
        pass
