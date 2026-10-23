"""Live quality and speed test for VoiceTut on CUDA GPU."""

import asyncio
import io
import math
import struct
import sys
import time
import wave

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")

import torch
print("=" * 65)
print("🚀 فحص كارت الشاشة والـ CUDA:")
print("CUDA Available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("GPU Device:", torch.cuda.get_device_name(0))
    print("VRAM Total:", f"{torch.cuda.get_device_properties(0).total_memory / (1024**3):.2f} GB")
print("=" * 65)

from app.providers.tts.voicetut import VoiceTutProvider


async def run_test():
    test_text = "أخباركم إيه يا شباب؟ الصوت دلوقتي سريع جداً ومخارج الحروف نقية مية في المية!"
    print(f"\n[1] 🧪 جاري توليد الجملة بـ 32 خطوة Diffusion كاملة على كارت الشاشة:")
    print(f"النص: \"{test_text}\"")

    p = VoiceTutProvider()
    t0 = time.time()
    wav_bytes = await p.synthesize(
        text=test_text,
        ref_audio="data/voice_samples/personality_1.wav",
    )
    t1 = time.time()
    elapsed = t1 - t0

    out_file = "test_cuda_output.wav"
    with open(out_file, "wb") as f:
        f.write(wav_bytes)

    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        dur = wf.getnframes() / wf.getframerate()
        frames = wf.readframes(wf.getnframes())
        samples = struct.unpack(f"<{len(frames)//2}h", frames)
        rms = math.sqrt(sum(s**2 for s in samples) / len(samples))
        peak = max(abs(s) for s in samples)

    print("\n" + "=" * 65)
    print(f"🎉 تم الانتهاء بنجاح باهر!")
    print(f"⚡ الوقت المستغرق: {elapsed:.2f} ثانية فقط!")
    print(f"🔊 مدة المقطع الصوتي: {dur:.2f} ثانية")
    print(f"📈 أقصى سعة للصوت: {peak}")
    print(f"📉 متوسط طاقة الصوت (RMS): {rms:.1f}")
    print(f"📁 تم حفظ الملف الصوتي كـ: {out_file}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(run_test())
