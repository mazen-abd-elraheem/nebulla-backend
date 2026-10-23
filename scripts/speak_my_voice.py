"""Interactive CLI tool to generate speech in user's cloned voice."""

import asyncio
import os
import sys
import time

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")

from app.services.voice_clone.voice_clone_service import VoiceCloneService


async def generate_speech(text: str, personality_id: int = 1):
    svc = VoiceCloneService.get_instance()
    print(f"\n⏳ جاري استنساخ وتوليد الصوت للنص: \"{text}\" ...")
    t0 = time.time()
    wav_bytes = await svc.synthesize(text=text, personality_id=personality_id)
    t1 = time.time()

    if not wav_bytes or len(wav_bytes) <= 1000:
        print("❌ فشل التوليد أو لم يتم إرجاع ملف صوتي صالح.")
        return

    out_file = "my_voice_output.wav"
    with open(out_file, "wb") as f:
        f.write(wav_bytes)

    elapsed = t1 - t0
    print(f"✅ تم التوليد بنجاح في {elapsed:.1f} ثانية!")
    print(f"📁 تم حفظ الملف كـ: {os.path.abspath(out_file)}")

    # On Windows, try opening the audio file in the default media player
    try:
        os.startfile(out_file)
    except Exception:
        pass


def main():
    if len(sys.argv) > 1:
        text = " ".join(sys.argv[1:]).strip()
    else:
        print("=" * 60)
        print("🎙️ استنساخ الصوت بالنص المخصص - نبيولا")
        print("=" * 60)
        try:
            text = input("✍️ اكتب النص اللي عايز تنطقه بصوتك: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nتم الإلغاء.")
            return

    if not text:
        print("⚠️ لم يتم إدخال أي نص.")
        return

    asyncio.run(generate_speech(text))


if __name__ == "__main__":
    main()
