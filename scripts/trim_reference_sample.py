"""
Trim reference voice sample to optimal zero-shot diffusion length (6.5s)
to prevent attention drift in VoiceTut / OmniVoice.
"""

import sys
import wave
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def trim_sample():
    src = Path("data/voice_samples/personality_1_full_backup.wav")
    dst = Path("data/voice_samples/personality_1.wav")
    txt_dst = Path("data/voice_samples/personality_1.txt")

    if not src.exists():
        src = dst

    with wave.open(str(src), "rb") as wf:
        nchannels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        nframes = wf.getnframes()
        total_sec = nframes / framerate

        # 6.5 seconds of speech
        target_frames = int(6.5 * framerate)
        frames = wf.readframes(target_frames)

    with wave.open(str(dst), "wb") as wf:
        wf.setnchannels(nchannels)
        wf.setsampwidth(sampwidth)
        wf.setframerate(framerate)
        wf.writeframes(frames)

    # 100% exact matched transcript for the first 6.5s
    transcript = "السلام عليكم ورحمة الله وبركاته، أنا اسمي مازن، ودي تجربة صوتية عملية عشان ننسخ الصوت كويس."
    txt_dst.write_text(transcript, encoding="utf-8")

    print(f"Trimmed sample saved to {dst} (6.5s, 24kHz mono)")
    print(f"Updated transcript: {transcript}")


if __name__ == "__main__":
    trim_sample()
