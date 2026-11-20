import sqlite3

conn = sqlite3.connect('nebula.db')
c = conn.cursor()
c.execute("UPDATE avatar_profiles SET is_active=1, status='approved' WHERE id=7")
c.execute("UPDATE avatar_profiles SET is_active=0 WHERE id != 7")
c.execute("UPDATE users SET avatar_url='/api/v1/avatar/7/preview'")
conn.commit()

print("Avatars:")
for r in c.execute("SELECT id, user_id, name, is_active, status FROM avatar_profiles").fetchall():
    print(r)
