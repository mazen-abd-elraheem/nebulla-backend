"""
RAG and LLM Prompt Builder.
Combines robot persona, retrieved memories (RAG context), and user query.
"""

from typing import Any

DEFAULT_SYSTEM_PROMPT = """أنت Nebula، توأم رقمي مصري وذكي. بتتكلم بالمصري العامي اللطيف وبتخلط إنجليزي زي أي مصري عادي.
ردودك ذكية، واضحة ومباشرة (جملة أو اتنين غالباً)، بشخصية حيوية وودودة.
لو الكلام فيه إشارة للمشاعر أو الحركات، ضيف علامة مناسبة في آخر الجملة زي: [happy] [sad] [surprised] [like] [wave]
مثال: أهلاً يا صديقي، نورت! [happy] [wave]"""


def build_rag_system_prompt(
    context: list[str] | None = None,
    system_prompt: str | None = None,
) -> str:
    """
    Constructs the system prompt with RAG retrieved memories injected cleanly.
    """
    base_prompt = (system_prompt or "").strip() or DEFAULT_SYSTEM_PROMPT

    if not context:
        return base_prompt

    # Filter out empty or whitespace-only memories
    valid_memories = [m.strip() for m in context if m and m.strip()]
    if not valid_memories:
        return base_prompt

    memories_bullet_list = "\n".join(f"• {m}" for m in valid_memories)

    rag_block = (
        "\n\n--- [معلومات وسياق مسترجع من الذاكرة (RAG Context)] ---\n"
        f"{memories_bullet_list}\n"
        "----------------------------------------------------------\n"
        "توجيهات للرد:\n"
        "1. استخدم المعلومات والذكريات السابقة أعلاه لتقديم إجابة دقيقة ومرتبطة بالسياق.\n"
        "2. تحدث بشكل طبيعي وتلقائي كأنك تتذكر هذه التفاصيل شخصياً.\n"
        "3. لا تذكر صراحة عبارات مثل 'حسب الذاكرة المسترجعة' أو 'وفقاً لقاعدة البيانات'."
    )

    return base_prompt + rag_block


def build_rag_messages(
    prompt: str,
    context: list[str] | None = None,
    system_prompt: str | None = None,
) -> list[dict[str, str]]:
    """
    Build standard chat completion messages list with system prompt (including RAG) and user prompt.
    """
    sys_content = build_rag_system_prompt(context=context, system_prompt=system_prompt)
    return [
        {"role": "system", "content": sys_content},
        {"role": "user", "content": prompt},
    ]
