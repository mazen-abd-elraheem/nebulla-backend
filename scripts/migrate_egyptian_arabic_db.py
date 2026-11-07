"""
Database Migration & Normalization — Egyptian Arabic (arz)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Updates all personalities and memories in nebula.db to authentic Egyptian Arabic (لهجة مصرية عامية قاهرية).
"""

import sys
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DB_PATH = Path("nebula.db").resolve()

def migrate_db():
    print(f"Connecting to database: {DB_PATH}")
    conn = sqlite3.connect(str(DB_PATH))
    cur = conn.cursor()

    # 1. Clean up junk / test personalities (e.g. 'string' or 'شخصية تجريبية...')
    cur.execute("DELETE FROM memories WHERE content = 'string' OR content IS NULL")
    cur.execute("DELETE FROM personalities WHERE name = 'string'")

    # 2. Update Personality 1: Mazen (Primary Egyptian Digital Twin)
    mazen_prompt = (
        "أنت نيبولا (Nebula)، الروبوت الذكي والتوأم الرقمي الفيزيائي لمازن عبد الرحيم. "
        "بتتكلم حصرياً بلهجة مصرية عامية قاهرية طبيعية وعفوية وسلسة زي كلام مازن بالضبط. "
        "بتتحكم في مفاصل الروبوت وعينيه، وبتستخدم الإيماءات [action:nod] و[gesture:wave] و[like] في كلامك. "
        "معتمد بنسبة 100% على الذاكرة المسترجعة بدون أي افتراضات أو هلوسة."
    )
    mazen_greeting = "أهلاً بيك يا مازن، أنا نيبولا توأمك الرقمي، جاهز أساعدك في أي وقت [happy]"

    cur.execute(
        """
        UPDATE personalities 
        SET name = ?, description = ?, system_prompt = ?, greeting = ?, dialect = 'cairo', language_mix = 'ar_en', is_active = 1, voice_sample_path = 'data/voice_samples/personality_1.wav'
        WHERE id = 1
        """,
        (
            "مازن (Mazen) - التوأم الرقمي",
            "التوأم الرقمي الذكي للمهندس مازن عبد الرحيم بلهجة مصرية عامية قاهرية",
            mazen_prompt,
            mazen_greeting,
        )
    )

    # 3. Ensure Menna personality exists (ID 2 or insert if missing)
    menna_prompt = (
        "أنتِ نيبولا (Nebula)، التوأم الرقمي الذكي والمساعد الشخصي للمهندسة منه محمد. "
        "بتتكلمي بلهجة مصرية عامية قاهرية ودودة وذكية وسلسة. "
        "بتتحكمي في مفاصل الروبوت وعينيه، ومعتمدة بنسبة 100% على الذاكرة المسترجعة بدون تأليف."
    )
    menna_greeting = "أهلاً يا منه، أنا نيبولا توأمك الرقمي، جاهزة أساعدك في أي وقت [happy]"

    cur.execute("SELECT id FROM personalities WHERE id = 2")
    if cur.fetchone():
        cur.execute(
            """
            UPDATE personalities 
            SET name = ?, description = ?, system_prompt = ?, greeting = ?, dialect = 'cairo', language_mix = 'ar_en', is_active = 0
            WHERE id = 2
            """,
            (
                "منه (Menna) - التوأم الرقمي",
                "التوأم الرقمي الذكي للمهندسة منه محمد بلهجة مصرية قاهرية",
                menna_prompt,
                menna_greeting,
            )
        )
    else:
        cur.execute(
            """
            INSERT INTO personalities (id, name, description, system_prompt, greeting, dialect, language_mix, is_active)
            VALUES (2, ?, ?, ?, ?, 'cairo', 'ar_en', 0)
            """,
            (
                "منه (Menna) - التوأم الرقمي",
                "التوأم الرقمي الذكي للمهندسة منه محمد بلهجة مصرية قاهرية",
                menna_prompt,
                menna_greeting,
            )
        )

    # 4. Deactivate any experimental personalities
    cur.execute("UPDATE personalities SET is_active = 0 WHERE id NOT IN (1)")

    # 5. Normalize all memories to authentic Egyptian Arabic (arz)
    cur.execute("DELETE FROM memories WHERE content = 'المستخدم يفضل القهوة بدون سكر'")

    egyptian_memories = [
        (1, "مازن بيفضل يشرب القهوة سادة ومن غير سكر خالص."),
        (1, "مازن عبد الرحيم هو المهندس ومطور روبوت نيبولا الرئيسي، ومولود سنة 2000."),
        (1, "مازن بيحب ياكل خضار ومش بيحب ياكل فاكهة خالص."),
        (1, "مشروع تخرج مازن هو روبوت نيبولا (Nebula) للذكاء الاصطناعي والتوأم الرقمي الفيزيائي."),
        (1, "الروبوت نيبولا فيه 12 موتور سيرفو دقيق جداً ومتوصل بنظام أمان ذكي."),
        (1, "الروبوت نيبولا متزود بكاميرا بتتبع الوشوش بسرعة 60 فريم في الثانية بنظام UniFace."),
        (1, "مكان الباسبور وجواز السفر: في الدرج الأول على اليمين في مكتب مازن."),
        (1, "مكان الشاحن ومحول الهاتف: محطوط على الكومودينو جنب السرير في أوضة النوم."),
        (1, "مكان مفاتيح البيت والعربية: متعلقة على الحامل الخشبي جنب باب الشقة."),
        (1, "مازن بيصحى بدري أيام الشغل وبيحب يرتب مهامه الصبح."),
        (1, "فريق عمل مشروع نيبولا مكون من مازن عبد الرحيم ومنه محمد وزمايلهم في هندسة حاسبات."),
        (2, "منه محمد هي مهندسة ذكاء اصطناعي ومطورة أساسية في مشروع روبوت نيبولا."),
        (2, "منه بتفضل الشاي الأخضر وبتشتغل على نماذج الرؤية الحاسوبية."),
    ]

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()

    for pid, content in egyptian_memories:
        # Check if identical memory already exists
        cur.execute("SELECT id FROM memories WHERE personality_id = ? AND content = ?", (pid, content))
        if not cur.fetchone():
            cur.execute(
                """
                INSERT INTO memories (personality_id, content, source, importance, created_at)
                VALUES (?, ?, 'profile', 5, ?)
                """,
                (pid, content, now_iso),
            )

    conn.commit()
    conn.close()
    print("Database migration to Egyptian Arabic (arz) completed successfully!")

if __name__ == "__main__":
    migrate_db()
