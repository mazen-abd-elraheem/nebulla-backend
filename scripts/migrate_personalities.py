import sqlite3

conn = sqlite3.connect('nebula.db')
c = conn.cursor()
c.execute('PRAGMA table_info(personalities)')
cols = [col[1] for col in c.fetchall()]
print('Existing cols:', cols)

if 'image_path' not in cols:
    c.execute('ALTER TABLE personalities ADD COLUMN image_path VARCHAR(256)')
    print('Added image_path')

if 'tone' not in cols:
    c.execute("ALTER TABLE personalities ADD COLUMN tone VARCHAR(128) DEFAULT 'ودود وعفوي ومباشر'")
    print('Added tone')

# Check if Personality 0 exists, if not create default system personality 0
c.execute('SELECT id, name FROM personalities WHERE id = 0')
row = c.fetchone()
if not row:
    c.execute("""
        INSERT INTO personalities (id, name, description, system_prompt, dialect, language_mix, voice_sample_path, image_path, tone, is_active, created_at)
        VALUES (0, 'نيبولا (الروبوت العام)', 'المساعد الذكي العام والنظام الافتراضي للروبوت', 'أنت نيبولا، المساعد الذكي العام ونظام التشغيل الافتراضي.', 'cairo', 'ar_en', 'data/voice_samples/default.wav', 'data/images/nebula.png', 'ودود وهادئ ومساعد', 0, datetime('now'))
    """)
    print('Created Personality 0')

# Check Personality 1 & 2 image and tone
c.execute("UPDATE personalities SET tone = 'اعتزاز وولاء مباشر وعفوية حماسية ومرحة', image_path = 'data/images/mazen.png' WHERE id = 1")
c.execute("UPDATE personalities SET tone = 'دافئ وودود ورياضي', image_path = 'data/images/ahmed.png' WHERE id = 2")

conn.commit()

c.execute('SELECT id, name, tone, image_path FROM personalities')
for r in c.fetchall():
    print(r)

conn.close()
