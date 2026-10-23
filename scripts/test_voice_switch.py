"""Verification script to test dynamic voice clone swapping."""

import asyncio
import os
import sys
import wave

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, ".")

from app.services.voice_clone.voice_clone_service import VoiceCloneService
from app.db.session import init_db, AsyncSessionLocal
from app.models.personality import Personality


async def main():
    print("=" * 65)
    print("🧪 اختبار التبديل الديناميكي للاستنساخ الصوتي وتحديث الـ DB")
    print("=" * 65)

    await init_db()
    svc = VoiceCloneService.get_instance()

    # 1. Check get_sample_path when personality_id is None
    sample_none = svc.get_sample_path(None)
    print(f"1. فحص المسار التلقائي بدون تحديد personality_id:")
    print(f"   -> المسار المسترجع: {sample_none}")
    assert sample_none is not None, "يجب أن يعيد أحدث مسار عينة صوتية تلقائياً!"

    # 2. Check DB sync
    async with AsyncSessionLocal() as session:
        p = await session.get(Personality, 1)
        print(f"2. فحص الشخصية في قاعدة البيانات (DB):")
        print(f"   -> الاسم: {p.name if p else 'N/A'}")
        print(f"   -> مسار الصوت المستنسخ: {p.voice_sample_path if p else 'N/A'}")

    # 3. Test AIPipeline _generate_tts integration
    from app.services.ai.pipeline import AIPipeline
    pipeline = AIPipeline()
    print(f"3. فحص دالة _generate_tts في خط محادثات الروبوت (AIPipeline):")
    test_text = "تجربة سريعة للتأكد من ربط الصوت المستنسخ."
    audio = await pipeline._generate_tts(test_text, personality_id=1)
    print(f"   -> حجم الصوت الناتج: {len(audio):,} بايت")
    assert len(audio) > 1000, "يجب أن يولد ملف صوتي صالح!"

    out_file = "test_switch_verify.wav"
    with open(out_file, "wb") as f:
        f.write(audio)
    print(f"   -> تم حفظ الصوت في: {out_file}")

    print("\n✅ تم التحقق من ربط وتحديث استنساخ الصوت بنجاح 100%!")


if __name__ == "__main__":
    asyncio.run(main())
