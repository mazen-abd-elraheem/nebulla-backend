import os
import shutil
import sqlite3

os.makedirs('data/voice_samples', exist_ok=True)

src = 'api_tested_voice.wav'
if not os.path.exists(src):
    src = 'data/voice_samples/latest_synthesized.wav'

if os.path.exists(src):
    shutil.copy(src, 'data/voice_samples/default.wav')
    shutil.copy(src, 'data/voice_samples/personality_1.wav')
    shutil.copy(src, 'data/voice_samples/personality_2.wav')
    print('Copied sample files to data/voice_samples.')

conn = sqlite3.connect('nebula.db')
c = conn.cursor()
c.execute("UPDATE personalities SET voice_sample_path = 'data/voice_samples/default.wav' WHERE id = 0")
c.execute("UPDATE personalities SET voice_sample_path = 'data/voice_samples/personality_1.wav' WHERE id = 1")
c.execute("UPDATE personalities SET voice_sample_path = 'data/voice_samples/personality_2.wav' WHERE id = 2")
conn.commit()

for r in c.execute('SELECT id, name, voice_sample_path FROM personalities'):
    print(r)

conn.close()
