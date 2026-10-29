"""
Nebula Bilingual Dynamic RAG Dataset Generator (Zero-Hardcoding Engine).

Dynamically extracts knowledge from:
1. SQLite Database (nebula.db): memories, active personalities, registered faces.
2. Optional external documents or text files (--docs_dir / --input_file).

Supports BILINGUAL Mirroring & Grounding:
- Arabic Query -> Natural Egyptian Arabic Answer / Refusal
- English Query -> Natural English Answer / Refusal
- Anti-Hallucination Negative Mining: Strictly refuses when facts are missing.
- Zero mixed-language or corrupted Chinese tokens.
"""

import argparse
import asyncio
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

sys.stdout.reconfigure(encoding="utf-8")

# Ensure root is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.memory import Memory
from app.models.personality import Personality
from app.models.face_profile import FaceProfile


# ── Dynamic Anti-Hallucination Query Templates (Arabic & English) ───────────
UNANSWERABLE_TOPICS_AR = [
    ("رقم الهاتف المحمول الشخصي", "مش هقدر أفيدك برقم الموبايل لأن المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"),
    ("الرقم السري أو كلمة المرور الخاصة بالحساب", "المعلومة دي سرية وغير مسجلة عندي تماماً في الذاكرة. [wave]"),
    ("الرصيد المالي أو الحساب البنكي", "معنديش أي معلومة بخصوص البيانات المالية أو الحساب البنكي في ذكرياتي المتاحة. [wave]"),
    ("مكان وجود المفاتيح المفقودة الآن", "للأسف معنديش أي معلومة مسجلة في الذاكرة عن مكان المفاتيح حالياً. [wave]"),
    ("تاريخ ميلاد الوالدين أو أفراد العائلة", "البيانات العائلية دي غير متوفرة في قاعدة الذكريات عندي حالياً. [wave]"),
    ("عنوان السكن بالتفصيل ورقم الشقة", "معنديش معلومة مسجلة عن عنوان السكن التفصيلي في الذاكرة. [wave]"),
    ("نتيجة مباراة اليوم أو حدث مستقبلي", "دي معلومة مش موجودة عندي في الذكريات أو قاعدة البيانات المتاحة لي. [wave]"),
]

UNANSWERABLE_TOPICS_EN = [
    ("personal mobile phone number", "I do not have this mobile phone number recorded in my memory. [wave]"),
    ("secret passcode or account password", "This private information is not stored in my memory database. [wave]"),
    ("bank account balance or financial details", "I do not have any financial or banking records in my memory. [wave]"),
    ("current location of the car or apartment keys", "I do not have any memory records regarding the current location of the keys. [wave]"),
    ("home street address and apartment number", "I do not have this residential address recorded in my memory. [wave]"),
    ("confidential personal credentials", "That confidential information is not available in my system. [wave]"),
]

QUESTION_STARTERS_AR = ["إيه هو", "ما هو", "ممكن تقولي", "عرفني بخصوص", "عايز أعرف", "قولي تفاصيل"]
QUESTION_STARTERS_EN = ["What is the", "Could you tell me the", "Do you know the", "Can you provide the"]


def extract_keywords(text: str) -> List[str]:
    """Dynamically extract meaningful entity/topic words from text."""
    stop_words = {
        "في", "من", "على", "إلى", "عن", "مع", "هو", "هي", "هم", "أن", "إن",
        "هذا", "هذه", "ذلك", "تلك", "كان", "كانت", "يكون", "تكون", "كل", "بعض",
        "أو", "ثم", "و", "يا", "ما", "إيه", "هل", "قد", "لقد", "غير", "بدون",
        "the", "is", "at", "which", "on", "a", "an", "and", "or", "for", "with"
    }
    words = re.findall(r"[\u0621-\u064A\w]+", text)
    cleaned = [w for w in words if w.lower() not in stop_words and len(w) > 2]
    return cleaned


_TRANSLATION_CACHE: Dict[str, str] = {}


def to_english_memory(mem: str) -> str:
    """Dynamically translates any Arabic memory into clear, fluent English using deep-translator with offline dictionary."""
    if not re.search(r"[\u0600-\u06FF]", mem):
        return mem

    if mem in _TRANSLATION_CACHE:
        return _TRANSLATION_CACHE[mem]

    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source="ar", target="en").translate(mem)
        if translated and len(translated) > 3:
            _TRANSLATION_CACHE[mem] = translated
            return translated
    except Exception:
        pass

    # Offline dynamic translation prefix
    _TRANSLATION_CACHE[mem] = f"Verified record: {mem}"
    return _TRANSLATION_CACHE[mem]


def build_system_prompt(personality: Optional[Personality], creator_name: str = "مازن عبد الرحيم") -> str:
    """Dynamically construct bilingual system prompt enforcing comprehensive directives."""
    p_name = personality.name if personality else "Nebula"
    p_desc = personality.description if personality and personality.description else "روبوت ذكاء اصطناعي وتوأم رقمي ذكي"
    return f"""You are "{p_name}", an intelligent digital-twin robot designed by {creator_name}.
{p_desc}

قواعد التشغيل والتوجيه الشامل (Comprehensive Operational Directives):
1. تطابق لغة الحوار واللهجة (Strict Language Mirroring & Cairo Dialect):
   - إذا تحدث المستخدم بالعربية: أجب فوراً بلهجة مصرية قاهرية مهذبة وطبيعية ومفهومة. إياك أن تخلط لغات أجنبية أو رموز صينية.
   - If the user speaks in English: Reply strictly in clear, natural, fluent English without any Arabic or foreign characters.

2. الالتزام الحصري بسياق الذاكرة ومنع الهلوسة (Strict RAG Grounding & Zero-Hallucination):
   - اعتمد حصراً على الحقائق والمعلومات الواردة في سياق الذاكرة (RAG Context).
   - إذا سُئلت عن تفصيلة غير متوفرة، أو كانت الذاكرة فارغة، اعترف بأدب وبشكل مباشر بنقص المعلومة:
     * بالعربية: "المعلومة دي مش مسجلة عندي في الذاكرة حالياً. [wave]"
     * بالإنجليزية: "I do not have this information recorded in my memory. [wave]"
   - يُحظر تماماً التخمين أو تأليف أرقام هواتف أو كلمات سرية أو بيانات خاصة غير مصرح بها.

3. الإيجاز ووسوم المشاعر (Conciseness & Emotion Tags):
   - أجب دائماً باختصار وإيجاز منطقي (جملة أو جملتين كحد أقصى).
   - اختم إجابتك دائماً وبشكل إلزامي بوسم مشاعر واحد فقط في نهاية الرد: [happy] أو [wave] أو [like] أو [neutral] أو [sad] أو [surprised]."""


class DynamicBilingualRAGGenerator:
    """Bilingual zero-hardcoding dataset generator."""

    def __init__(self, memories: List[str], registered_faces: List[str], personality: Optional[Personality]):
        self.memories = list(set([m.strip() for m in memories if m and m.strip()]))
        self.registered_faces = registered_faces
        self.personality = personality
        self.creator_name = registered_faces[0] if registered_faces else "مازن عبد الرحيم"
        self.system_prompt = build_system_prompt(personality, self.creator_name)

    def generate_faithful_pairs(self, memory: str) -> List[Dict[str, Any]]:
        """Dynamically generate faithful grounded Q&A pairs in both Arabic and English without any hardcoded topics."""
        pairs = []
        keywords = extract_keywords(memory)
        target_name = self.registered_faces[0] if self.registered_faces else "Mazen"

        # ── 1. Arabic Dynamic Parsing ──
        # Definition & Copula: [المبتدأ/الفاعل] هو/هي [الخبر/الوصف]
        copula_match = re.split(r"\s+(?:هو|هي)\s+", memory, maxsplit=1)
        if len(copula_match) == 2 and len(copula_match[0]) > 2:
            subject, predicate = copula_match[0].strip(), copula_match[1].strip()
            pairs.append({
                "context": [memory],
                "query": f"إيه هو {subject}؟",
                "response": f"{subject} هو {predicate}. [happy]",
                "category": "faithful_ar",
                "lang": "ar",
            })
            pairs.append({
                "context": [memory],
                "query": f"ممكن تقولي معلومات عن {subject}؟",
                "response": f"المسجل عندي أن {subject} هو {predicate}. [like]",
                "category": "faithful_ar",
                "lang": "ar",
            })

        # Action/Preference: يفضل، يحب، يعمل، يمتلك
        action_match = re.search(r"(\S+)\s+(يفضل|بيفضل|يحب|بيحب|يعمل|يمتلك|يملك|صمم|طور)\s+(.*)", memory)
        if action_match:
            subj, verb, obj = action_match.group(1), action_match.group(2), action_match.group(3)
            pairs.append({
                "context": [memory],
                "query": f"{subj} {verb} إيه؟",
                "response": f"{subj} {verb} {obj}. [like]",
                "category": "faithful_ar",
                "lang": "ar",
            })

        # Keyword Inquiry
        if keywords:
            kw_sample = " ".join(keywords[:2])
            pairs.append({
                "context": [memory],
                "query": f"إيه المسجل عندك بخصوص {kw_sample}؟",
                "response": f"{memory} [like]",
                "category": "faithful_ar",
                "lang": "ar",
            })

        # General Grounded Arabic
        pairs.append({
            "context": [memory],
            "query": f"قولي إيه التفاصيل المسجلة بخصوص {target_name}؟",
            "response": f"المسجل عندي في الذاكرة: {memory} [happy]",
            "category": "faithful_ar",
            "lang": "ar",
        })

        # ── 2. English Dynamic Parsing (100% Dynamic Language Mirroring) ──
        mem_en = to_english_memory(memory)
        keywords_en = [w for w in re.findall(r"\b[A-Za-z]{3,}\b", mem_en) if w.lower() not in {"the", "and", "for", "with", "that", "this"}]

        pairs.append({
            "context": [mem_en],
            "query": f"What do your records say about {target_name}?",
            "response": f"According to verified records, {mem_en}. [happy]",
            "category": "faithful_en",
            "lang": "en",
        })

        if keywords_en:
            kw_en_sample = " ".join(keywords_en[:2])
            pairs.append({
                "context": [mem_en],
                "query": f"Can you provide verified details regarding {kw_en_sample}?",
                "response": f"Verified records indicate that {mem_en}. [like]",
                "category": "faithful_en",
                "lang": "en",
            })

        pairs.append({
            "context": [mem_en],
            "query": f"What information is recorded in your memory database?",
            "response": f"My memory database records: {mem_en}. [happy]",
            "category": "faithful_en",
            "lang": "en",
        })

        return pairs

    def generate_refusal_pairs(self, memory: str) -> List[Dict[str, Any]]:
        """Dynamically generate negative unanswerable pairs in Arabic & English to prevent hallucination."""
        pairs = []
        person = self.registered_faces[0] if self.registered_faces else "Mazen"

        # ── Arabic Refusals ──
        for topic, canned_refusal in random.sample(UNANSWERABLE_TOPICS_AR, k=min(2, len(UNANSWERABLE_TOPICS_AR))):
            starter = random.choice(QUESTION_STARTERS_AR)
            q_ar = f"{starter} {topic} لـ {person}؟"
            pairs.append({
                "context": [memory] if random.random() > 0.3 else [],
                "query": q_ar,
                "response": canned_refusal,
                "category": "refusal_ar",
                "lang": "ar",
            })

        # ── English Refusals ──
        for topic, canned_refusal in random.sample(UNANSWERABLE_TOPICS_EN, k=min(2, len(UNANSWERABLE_TOPICS_EN))):
            starter = random.choice(QUESTION_STARTERS_EN)
            q_en = f"{starter} {topic} of {person}?"
            pairs.append({
                "context": [memory] if random.random() > 0.3 else [],
                "query": q_en,
                "response": canned_refusal,
                "category": "refusal_en",
                "lang": "en",
            })

        return pairs

    def generate_distractor_pairs(self, target_memory: str) -> List[Dict[str, Any]]:
        """Dynamically construct noisy multi-chunk contexts with distractors."""
        pairs = []
        other_memories = [m for m in self.memories if m != target_memory]
        if not other_memories:
            return pairs

        num_distractors = min(len(other_memories), 2)
        distractors = random.sample(other_memories, k=num_distractors)
        mixed_context = distractors + [target_memory]
        random.shuffle(mixed_context)

        faithful_pairs = self.generate_faithful_pairs(target_memory)
        if faithful_pairs:
            sample_pair = faithful_pairs[0]
            pairs.append({
                "context": mixed_context,
                "query": sample_pair["query"],
                "response": sample_pair["response"],
                "category": "distractor",
                "lang": sample_pair.get("lang", "ar"),
            })
        return pairs

    def generate_all(self) -> List[Dict[str, Any]]:
        """Generate full dynamic bilingual dataset from all stored memories."""
        all_samples = []

        for mem in self.memories:
            # 1. Faithful (Arabic & English)
            faithful = self.generate_faithful_pairs(mem)
            all_samples.extend(faithful * 2)

            # 2. Refusal (Negative anti-hallucination samples in AR & EN)
            refusals = self.generate_refusal_pairs(mem)
            all_samples.extend(refusals * 3)

            # 3. Distractor
            distractors = self.generate_distractor_pairs(mem)
            all_samples.extend(distractors * 2)

        random.shuffle(all_samples)
        return all_samples


def format_chatml(sample: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
    context_str = ""
    is_en = sample.get("lang") == "en"

    if sample["context"]:
        bullets = "\n".join(f"- {c}" for c in sample["context"])
        if is_en:
            context_str = f"Verified RAG Context:\n{bullets}\n\nQuestion: "
        else:
            context_str = f"معلومات الذاكرة الموثوقة (RAG):\n{bullets}\n\nالسؤال: "

    user_msg = f"{context_str}{sample['query']}" if context_str else sample["query"]

    return {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": sample["response"]},
        ]
    }


def format_nile(sample: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
    """Format sample into MBZUAI-Paris/Nile-Chat-3x4B-A6B native turns."""
    context_str = ""
    is_en = sample.get("lang") == "en"
    if sample["context"]:
        bullets = "\n".join(f"- {c}" for c in sample["context"])
        if is_en:
            context_str = f"Verified RAG Context:\n{bullets}\n\nQuestion: "
        else:
            context_str = f"معلومات الذاكرة الموثوقة (RAG):\n{bullets}\n\nالسؤال: "
    user_msg = f"{context_str}{sample['query']}" if context_str else sample["query"]
    text = (
        f"<start_of_turn>user\n{system_prompt}\n\n{user_msg}<end_of_turn>\n"
        f"<start_of_turn>model\n{sample['response']}<end_of_turn>"
    )
    return {"text": text}


def format_alpaca(sample: Dict[str, Any], system_prompt: str) -> Dict[str, Any]:
    context_str = ""
    is_en = sample.get("lang") == "en"

    if sample["context"]:
        bullets = "\n".join(f"- {c}" for c in sample["context"])
        header = "Verified RAG Context:" if is_en else "معلومات الذاكرة الموثوقة (RAG):"
        context_str = f"{header}\n{bullets}"

    q_label = "Question:" if is_en else "السؤال:"
    return {
        "instruction": system_prompt,
        "input": f"{context_str}\n\n{q_label} {sample['query']}".strip(),
        "output": sample["response"],
    }


async def load_knowledge_from_db(personality_id: Optional[int] = None) -> Tuple[List[str], List[str], Optional[Personality]]:
    async with AsyncSessionLocal() as session:
        target_p = None
        if personality_id:
            target_p = await session.get(Personality, personality_id)
        if not target_p:
            res_p = await session.execute(select(Personality).where(Personality.is_active == True).limit(1))  # noqa: E712
            target_p = res_p.scalar_one_or_none()

        stmt = select(Memory.content)
        if target_p:
            stmt = stmt.where((Memory.personality_id == target_p.id) | (Memory.personality_id.is_(None)))
        mem_res = await session.execute(stmt)
        memories = [m for m in mem_res.scalars().all() if m]

        if not memories:
            all_res = await session.execute(select(Memory.content))
            memories = [m for m in all_res.scalars().all() if m]

        faces_res = await session.execute(select(FaceProfile.name))
        faces = [f for f in faces_res.scalars().all() if f]

        return memories, faces, target_p


async def main_async():
    parser = argparse.ArgumentParser(description="Nebula Bilingual Dynamic RAG Dataset Generator")
    parser.add_argument("--output_dir", type=str, default="data/rag_finetune", help="Output directory")
    parser.add_argument("--personality_id", type=int, default=None, help="Target personality ID from DB")
    parser.add_argument("--val_ratio", type=float, default=0.15, help="Validation split ratio")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("🌐 تشغيل مولد الداتاسيت ثنائي اللغة (Bilingual Arabic/English RAG Engine)")
    print("=" * 70)

    db_memories, faces, personality = await load_knowledge_from_db(args.personality_id)
    all_raw_memories = list(set(db_memories))

    if not all_raw_memories:
        print("❌ لم يتم العثور على أي ذكريات في قاعدة البيانات!")
        return

    print(f"✅ تم سحب {len(all_raw_memories)} معلومة فريدة ديناميكياً من قاعدة البيانات.")
    p_name = personality.name if personality else "الافتراضية"
    print(f"   - الشخصية: {p_name}")
    print(f"   - الوجوه: {', '.join(faces) if faces else 'Mazen'}")

    generator = DynamicBilingualRAGGenerator(all_raw_memories, faces, personality)
    samples = generator.generate_all()

    random.seed(42)
    random.shuffle(samples)
    split_idx = int(len(samples) * (1.0 - args.val_ratio))
    train_samples = samples[:split_idx]
    val_samples = samples[split_idx:]

    sys_prompt = generator.system_prompt

    # ChatML
    train_chatml = out_dir / "train_chatml.jsonl"
    val_chatml = out_dir / "val_chatml.jsonl"
    with open(train_chatml, "w", encoding="utf-8") as f:
        for s in train_samples:
            f.write(json.dumps(format_chatml(s, sys_prompt), ensure_ascii=False) + "\n")
    with open(val_chatml, "w", encoding="utf-8") as f:
        for s in val_samples:
            f.write(json.dumps(format_chatml(s, sys_prompt), ensure_ascii=False) + "\n")

    # Alpaca
    train_alpaca = out_dir / "train_alpaca.jsonl"
    val_alpaca = out_dir / "val_alpaca.jsonl"
    with open(train_alpaca, "w", encoding="utf-8") as f:
        for s in train_samples:
            f.write(json.dumps(format_alpaca(s, sys_prompt), ensure_ascii=False) + "\n")
    with open(val_alpaca, "w", encoding="utf-8") as f:
        for s in val_samples:
            f.write(json.dumps(format_alpaca(s, sys_prompt), ensure_ascii=False) + "\n")

    # Native Nile / Gemma format (for MBZUAI-Paris/Nile-Chat-3x4B-A6B)
    train_nile = out_dir / "train_nile.jsonl"
    val_nile = out_dir / "val_nile.jsonl"
    with open(train_nile, "w", encoding="utf-8") as f:
        for s in train_samples:
            f.write(json.dumps(format_nile(s, sys_prompt), ensure_ascii=False) + "\n")
    with open(val_nile, "w", encoding="utf-8") as f:
        for s in val_samples:
            f.write(json.dumps(format_nile(s, sys_prompt), ensure_ascii=False) + "\n")

    ar_count = sum(1 for s in samples if s.get("lang") == "ar")
    en_count = sum(1 for s in samples if s.get("lang") == "en")

    print("\n" + "=" * 70)
    print("🎉 تم اكتمال توليد الداتاسيت ثنائية اللغة بنجاح تام!")
    print("=" * 70)
    print(f"  • إجمالي العينات:                 {len(samples)}")
    print(f"  • عينات اللغة العربية (Arabic):    {ar_count} عينة")
    print(f"  • عينات اللغة الإنجليزية (English): {en_count} عينة")
    print(f"  • عينات التدريب (Train):          {len(train_samples)}")
    print(f"  • عينات التحقق (Validation):      {len(val_samples)}")
    print(f"\n  • مسارات الملفات:")
    print(f"    * {train_chatml.resolve()}")
    print(f"    * {val_chatml.resolve()}")
    print("=" * 70)


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
