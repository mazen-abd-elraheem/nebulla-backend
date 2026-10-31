import asyncio
import os
import sys
import time
import soundfile as sf

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")

from app.providers.tts.voicetut import VoiceTutProvider

async def test_synth():
    print("=" * 60)
    print("Testing VoiceTut Cloning with Studio Settings:")
    print("num_step=16, guidance_scale=2.6, speed=1.15")
    print("=" * 60)

    p = VoiceTutProvider()
    test_text = "أهلاً بيكم يا شباب، دي تجربة الصوت المصري المستنسخ بعد ما ظبطنا مخارج الحروف والسرعة ونبرة الصوت."
    
    t0 = time.time()
    wav_bytes = await p.synthesize(
        text=test_text,
        ref_audio="data/voice_samples/personality_1.wav",
        num_step=16,
        guidance_scale=2.6,
        speed=1.15,
        language="arz",
    )
    elapsed = time.time() - t0

    out_file = "test_verified_clone.wav"
    with open(out_file, "wb") as f:
        f.write(wav_bytes)

    info = sf.info(out_file)
    print(f"Synthesis finished in {elapsed:.2f}s!")
    print(f"Generated audio duration: {info.duration:.2f}s, Sample Rate: {info.samplerate}Hz")
    print(f"Output saved to: {out_file}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_synth())

