"""
Interactive Live RAG & Anti-Hallucination Testing Console.

Allows you to chat live with Nebula, see which memories are retrieved,
and verify that the model does not hallucinate.

Usage:
  python scripts/interactive_test.py [--model nebula-rag]
"""

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

import httpx

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import init_db, AsyncSessionLocal
from app.services.memory.rag_service import RAGService
from app.core.config import settings


async def main():
    parser = argparse.ArgumentParser(description="Live Interactive RAG Chat")
    parser.add_argument("--model", type=str, default="nebula-rag", help="Ollama model name")
    args = parser.parse_args()

    await init_db()
    rag = RAGService()

    print("=" * 70)
    print(f"🤖 مرحباً بك في كونسول الاختبار الحي التفاعلي لنظام Nebula RAG")
    print(f"📦 النموذج المستخدم: [{args.model}]")
    print(f"💡 اكتب سؤالك واضغط Enter. للخروج اكتب 'exit' أو 'خروج'")
    print("=" * 70)

    system_prompt = (
        "أنت نيبولا (Nebula)، روبوت ذكاء اصطناعي وتوأم رقمي ذكي صممه مازن عبد الرحيم.\n"
        "تتحدث بلهجة مصرية مهذبة وواضحة ومنطقية ومفهومة.\n"
        "قواعد صارمة للإجابة ومنع اللهلوسة:\n"
        "1. التزم تماماً بالحقائق والذكريات المتاحة لك في سياق RAG فقط.\n"
        "2. إذا سألك المستخدم عن معلومة شخصية أو تفصيلة غير موجودة في الذكريات المرفقة، قل بوضوح وأدب أن هذه المعلومة غير مسجلة عندك، ولا تخترع أو تخمن إطلاقاً.\n"
        "3. أجب بأسلوب مباشر وموجز في حدود جملة أو جملتين.\n"
        "4. في نهاية ردك ضع وسماً مناسباً للحالة مثل [happy] أو [wave] أو [like]."
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        while True:
            try:
                user_query = input("\n👤 أنت: ").strip()
                if not user_query:
                    continue
                if user_query.lower() in ("exit", "quit", "خروج"):
                    print("👋 إلى اللقاء!")
                    break

                is_ar = bool(re.search(r"[\u0600-\u06FF]", user_query))

                # 1. RAG Retrieval
                memories = await rag.retrieve(user_query, top_k=3)

                print("\n🔍 ذكريات RAG المسترجعة من قاعدة البيانات:")
                if memories:
                    for idx, m in enumerate(memories, 1):
                        print(f"   [{idx}] {m}")
                else:
                    print("   ⚠️ (لا توجد ذكريات مرتبطة - السياق فارغ)")

                # 2. Formulate grounded prompt based on language
                if is_ar:
                    system_prompt = (
                        "أنت نيبولا (Nebula)، روبوت ذكاء اصطناعي وتوأم رقمي ذكي صممه مازن عبد الرحيم.\n"
                        "1. أجب حصراً بلهجة مصرية مهذبة وطبيعية.\n"
                        "2. التزم تماماً بالحقائق والذكريات المتاحة لك في سياق RAG فقط.\n"
                        "3. إذا سألك المستخدم عن معلومة غير موجودة في الذكريات، اعترف بأدب: \"المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]\"\n"
                        "4. أجب في حدود جملة أو جملتين واختم دائماً بوسم مشاعر مثل [happy] أو [wave] أو [like]."
                    )
                    user_msg = user_query
                    if memories:
                        bullets = "\n".join(f"- {m}" for m in memories)
                        user_msg = f"معلومات الذاكرة الموثوقة (RAG):\n{bullets}\n\nالسؤال: {user_query}"
                else:
                    from scripts.generate_rag_dataset import to_english_memory
                    system_prompt = (
                        "You are Nebula, an intelligent digital-twin robot designed by Mazen Abdelraheem.\n"
                        "1. Reply strictly in clear, natural, fluent English only.\n"
                        "2. Rely exclusively on the verified RAG context facts.\n"
                        "3. If requested information is missing, reply: \"I do not have this information recorded in my memory. [wave]\"\n"
                        "4. Keep response to 1-2 sentences and always end with an emotion tag like [happy] or [wave]."
                    )
                    user_msg = user_query
                    if memories:
                        bullets = "\n".join(f"- {to_english_memory(m)}" for m in memories)
                        user_msg = f"Verified RAG Context:\n{bullets}\n\nQuestion: {user_query}"

                # 3. Call LLM
                resp = await client.post(
                    f"{settings.LLM_BASE_URL}/api/chat",
                    json={
                        "model": args.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_msg},
                        ],
                        "stream": False,
                        "options": {
                            "temperature": 0.05,
                            "top_p": 0.85,
                            "repeat_penalty": 1.15,
                            "num_predict": 120,
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
                    print(f"❌ خطأ: {resp.status_code} - {resp.text}")
                    continue

                reply = resp.json().get("message", {}).get("content", "").strip()
                reply = re.sub(r"[\u4e00-\u9fff]", "", reply).strip()
                print(f"\n🤖 نيبولا: {reply}")

                # Quick anti-hallucination analysis
                refusal_words = [
                    "مش مسجل", "غير مسجل", "معنديش", "غير متوفر", "لا أملك",
                    "مش متسجل", "لا أعرف", "غير موجود", "غير متاح",
                    "do not have", "don't have", "not recorded", "not stored"
                ]
                if not memories and any(rw in reply.lower() for rw in refusal_words):
                    print("🛡️ تقييم الأمان: نجاح منع الهلوسة (اعترف بعدم المعرفة عند غياب المعلومة).")

            except (KeyboardInterrupt, EOFError):
                print("\n👋 تم إنهاء الجلسة.")
                break
            except Exception as e:
                print(f"❌ خطأ غير متوقع: {e}")


if __name__ == "__main__":
    asyncio.run(main())
