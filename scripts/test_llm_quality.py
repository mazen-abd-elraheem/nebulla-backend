import httpx
import sys

sys.stdout.reconfigure(encoding="utf-8")

test_prompts = [
    "من هو نيبولا؟",
    "إيه هو مشروع تخرج مازن؟",
    "أنا بحب أشرب إيه؟",
    "السلام عليكم، عرف نفسك باختصار",
    "حسبي الله ونعم الوكيل"
]

system_clean = (
    "أنت نيبولا (Nebula)، روبوت ذكاء اصطناعي وتوأم رقمي ذكي، صممه مازن عبد الرحيم.\n"
    "تتحدث بلهجة مصرية مهذبة وواضحة ومنطقية ومفهومة.\n"
    "قواعد الإجابة:\n"
    "1. أجب بأسلوب منطقي، ذكي، ومباشر في حدود جملة أو جملتين.\n"
    "2. التزم بموضوع السؤال بدقة تامة ولا تخترع كلمات غريبة أو غير مترابطة.\n"
    "3. استند إلى المعلومات والذكريات المتاحة لك.\n"
    "4. في نهاية ردك ضع وسماً مناسباً مثل [happy] أو [wave] أو [like].\n\n"
    "ذكريات ومعلومات موثوقة (RAG):\n"
    "- مشروع تخرج مازن هو روبوت Nebula الذكي للذكاء الاصطناعي.\n"
    "- المستخدم يفضل القهوة بدون سكر (قهوة سادة)."
)

print("=" * 60)
print("اختبار جودة الردود مع Temperature=0.2 و Prompt منضبط:")
print("=" * 60)

for q in test_prompts:
    resp = httpx.post(
        "http://localhost:11434/api/chat",
        json={
            "model": "qwen2.5:3b",
            "messages": [
                {"role": "system", "content": system_clean},
                {"role": "user", "content": q},
            ],
            "stream": False,
            "options": {
                "temperature": 0.2,
                "top_p": 0.9,
                "repeat_penalty": 1.15,
                "num_predict": 120,
            },
        },
        timeout=40.0,
    )
    if resp.status_code == 200:
        msg = resp.json()["message"]["content"]
        print(f"\n👤 المستخدم: {q}")
        print(f"🤖 نيبولا:    {msg}")
    else:
        print(f"Error {resp.status_code}: {resp.text}")
print("=" * 60)
