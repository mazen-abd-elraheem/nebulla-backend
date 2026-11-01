"""
End-to-end test for VoiceTut Egyptian voice cloning with Masri + English code-switching.
"""

import asyncio
import sys
import wave
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.voice_clone.voice_clone_service import VoiceCloneService


async def main():
    svc = VoiceCloneService.get_instance()
    test_text = (
        "أهلاً بيك يا فندم، الـ ID بتاعك جاهز والـ API شغال تمام الساعة 3:30، "
        "وعندنا meeting بكرة في تيم نيبولا."
    )
    print(f"Input text: {test_text}")

    wav_bytes = await svc.synthesize(
        text=test_text,
        personality_id=1,
        num_step=48,
        guidance_scale=2.2,
    )

    out_file = Path("data/voice_samples/production_masri_codeswitch_test.wav")
    out_file.write_bytes(wav_bytes)

    with wave.open(str(out_file), "rb") as wf:
        sr = wf.getframerate()
        ch = wf.getnchannels()
        dur = wf.getnframes() / sr

    print(f"SUCCESS: Generated {len(wav_bytes):,} bytes to {out_file}")
    print(f"Sample Rate: {sr} Hz, Channels: {ch}, Duration: {dur:.2f}s")


if __name__ == "__main__":
    asyncio.run(main())
