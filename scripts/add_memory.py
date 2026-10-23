"""
CLI Tool to easily add new memories into Nebula DB for RAG.

Usage:
  1. Add single memory text:
     python scripts/add_memory.py "مازن يعمل مهندس ذكاء اصطناعي"

  2. Add memories from a text file (line by line):
     python scripts/add_memory.py --file data/knowledge/sample_facts.txt

  3. List existing memories:
     python scripts/add_memory.py --list
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.db.session import AsyncSessionLocal, init_db
from app.models.memory import Memory
from app.models.personality import Personality
from app.services.memory.rag_service import RAGService


async def list_memories():
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Memory).order_by(Memory.id.desc()))
        memories = res.scalars().all()
        print("=" * 65)
        print(f"📋 الذكريات المسجلة حالياً في قاعدة البيانات ({len(memories)} معلومة):")
        print("=" * 65)
        for idx, m in enumerate(memories, 1):
            print(f"[{m.id}] {m.content}")
        print("=" * 65)


async def add_single_memory(content: str, importance: int = 5):
    await init_db()
    rag = RAGService()
    async with AsyncSessionLocal() as session:
        # Get active personality
        res = await session.execute(select(Personality.id).where(Personality.is_active == True).limit(1))  # noqa: E712
        active_p = res.scalar_one_or_none() or 1

    mid = await rag.add_memory(
        content=content.strip(),
        personality_id=active_p,
        source="cli",
        importance=importance,
    )
    print(f"✅ تم حفظ المعلومة بنجاح في قاعدة البيانات [ID: {mid}]:")
    print(f"   \"{content.strip()}\"")


async def add_file_memories(file_path: Path):
    if not file_path.exists():
        print(f"❌ الملف غير موجود: {file_path}")
        return

    lines = [
        line.strip()
        for line in file_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    if not lines:
        print("⚠️ الملف لا يحتوي على أسطر صالحة.")
        return

    print(f"⏳ جاري إضافة {len(lines)} معلومة من الملف: {file_path.name}...")
    await init_db()
    rag = RAGService()
    async with AsyncSessionLocal() as session:
        res = await session.execute(select(Personality.id).where(Personality.is_active == True).limit(1))  # noqa: E712
        active_p = res.scalar_one_or_none() or 1

    added = 0
    for line in lines:
        await rag.add_memory(
            content=line,
            personality_id=active_p,
            source=f"file:{file_path.name}",
            importance=5,
        )
        added += 1

    print(f"🎉 تم حفظ {added} معلومة بنجاح في الذاكرة!")


async def main():
    parser = argparse.ArgumentParser(description="Add memories to Nebula RAG")
    parser.add_argument("text", nargs="?", type=str, help="Text of the memory to add")
    parser.add_argument("--file", type=str, default=None, help="Path to text file containing memories")
    parser.add_argument("--list", action="store_true", help="List all stored memories")
    parser.add_argument("--importance", type=int, default=5, help="Importance score 1-10")
    args = parser.parse_args()

    if args.list:
        await list_memories()
        return

    if args.file:
        await add_file_memories(Path(args.file))
        return

    if args.text:
        await add_single_memory(args.text, args.importance)
        return

    parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
