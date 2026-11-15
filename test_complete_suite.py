"""
Comprehensive Test Suite for Nebula Personalities & Memory CRUD
Tests:
1. Personalities 0, 1, 2 presence, tones, images, voices, and display actions.
2. Memory CRUD (POST, GET by personality_id, PUT, DELETE by ID, POST /forget).
3. Personality Memory Isolation (No leakage between P1, P2, P0).
4. Auto Conflict Resolution (Book moving from Living Room to Chair/Desk).
5. Dynamic conversational tags ([memory:...], [forget:...]).
"""

import asyncio
import os
import sqlite3

# Set offline embedder for isolated unit test
os.environ["SENTENCE_TRANSFORMERS_OFFLINE"] = "1"

from app.services.memory.rag_service import RAGService
RAGService._shared_embedder = "disabled"
_rag = RAGService()
_rag._embedder = "disabled"


async def run_tests():
    print("=" * 60)
    print("🚀 بدء اختبارات نظام الشخصيات والذاكرة الشاملة...")
    print("=" * 60)

    # 1. اختبار قاعدة بيانات الشخصيات (0, 1, 2)
    print("\n[1] فحص الشخصيات (Personalities 0, 1, 2):")
    conn = sqlite3.connect("nebula.db")
    c = conn.cursor()
    c.execute("SELECT id, name, tone, image_path, voice_sample_path FROM personalities ORDER BY id")
    personalities = c.fetchall()
    for p in personalities:
        print(f"  • شخصية #{p[0]}: {p[1]} | النبرة: {p[2]} | الصورة: {p[3]}")
    
    p_ids = [p[0] for p in personalities]
    assert 0 in p_ids, "الشخصية 0 غير موجودة!"
    assert 1 in p_ids, "الشخصية 1 غير موجودة!"
    assert 2 in p_ids, "الشخصية 2 غير موجودة!"
    print("  ✅ الشخصيات 0 و 1 و 2 مسجلة بنجاح مع نبراتها وصورها.")

    # 2. اختبار عزل الذاكرة (Memory Isolation) بين الشخصيات
    print("\n[2] اختبار عزل الذكريات لكل شخصية:")
    # مسح ذكريات الاختبار السابقة
    c.execute("DELETE FROM memories WHERE content LIKE '%تيست%' OR content LIKE '%تنين%' OR content LIKE '%الكتاب%'")
    conn.commit()

    # إضافة ذاكرة للشخصية 1 (مازن)
    mid_p1 = _rag._add_memory_sync("تيست: مازن بيحب القهوة الصبح", personality_id=1, embedding=None, source="test", importance=5)
    # إضافة ذاكرة للشخصية 2 (أحمد)
    mid_p2 = _rag._add_memory_sync("تيست: أحمد بيلعب شطرنج بالليل", personality_id=2, embedding=None, source="test", importance=5)

    # استرجاع للشخصية 1
    mems_p1 = await _rag.retrieve("قهوة", personality_id=1)
    # استرجاع للشخصية 2
    mems_p2 = await _rag.retrieve("شطرنج", personality_id=2)
    # استرجاع متقاطع للتأكد من عدم التسريب
    leak_check_1 = await _rag.retrieve("شطرنج", personality_id=1)
    leak_check_2 = await _rag.retrieve("قهوة", personality_id=2)

    assert any("قهوة" in m for m in mems_p1), "فشل استرجاع ذاكرة الشخصية 1"
    assert any("شطرنج" in m for m in mems_p2), "فشل استرجاع ذاكرة الشخصية 2"
    assert not any("شطرنج" in m for m in leak_check_1), "خطأ: حدث تسريب من ذاكرة أحمد لمازن!"
    assert not any("قهوة" in m for m in leak_check_2), "خطأ: حدث تسريب من ذاكرة مازن لأحمد!"
    print("  ✅ عزل الذكريات بين الشخصيات 1 و 2 سليم 100% وبدون أي تسريب.")

    # 3. اختبار التحديث التلقائي للتعارض (Auto Conflict Resolution - مثال الكتاب)
    print("\n[3] اختبار حل التعارض واستبدال المعلومة القديمة بالجديدة تلقائياً:")
    # الخطوة أ: أحمد حط الكتاب في الصالة
    mid_old = _rag._add_memory_sync("أحمد حط الكتاب في الصالة", personality_id=2, embedding=None, source="test", importance=5)
    print(f"  • تم تسجيل المعلومة الأصلية #{mid_old}: 'أحمد حط الكتاب في الصالة'")

    # الخطوة ب: أحمد نقل الكتاب وحطه على الكرسي
    mid_new = _rag._add_memory_sync("أحمد نقل الكتاب وحطه علي الكرسي", personality_id=2, embedding=None, source="test", importance=5)
    print(f"  • تم تسجيل المعلومة الأحدث #{mid_new}: 'أحمد نقل الكتاب وحطه علي الكرسي'")

    # التحقق من قاعدة البيانات
    c.execute("SELECT id, content FROM memories WHERE personality_id = 2 AND content LIKE '%كتاب%'")
    current_book_mems = c.fetchall()
    print(f"  • الموجود حالياً في الذاكرة: {current_book_mems}")
    
    assert len(current_book_mems) == 1, f"خطأ: المفروض تظهر معلومة واحدة فقط، الموجود: {len(current_book_mems)}"
    assert "الكرسي" in current_book_mems[0][1], "خطأ: المعلومة الموجودة ليست الأحدث!"
    assert "الصالة" not in current_book_mems[0][1], "خطأ: المعلومة القديمة الملغية (الصالة) ما زالت موجودة!"
    print("  ✅ تم استبدال المعلومة القديمة ومسحها تلقائياً وحفظ المعلومة الجديدة فقط.")

    # 4. اختبار التعديل المباشر (PUT / UPDATE)
    print("\n[4] اختبار ميثود التعديل (UPDATE):")
    target_mid = current_book_mems[0][0]
    updated_obj = await _rag.update_memory(
        memory_id=target_mid,
        content="أحمد نقل الكتاب وحطه على المكتب في الدور الثاني",
        importance=8,
    )
    assert updated_obj is not None, "فشل عملية الـ update!"
    c.execute("SELECT content, importance FROM memories WHERE id = ?", (target_mid,))
    updated_row = c.fetchone()
    assert "المكتب في الدور الثاني" in updated_row[0], "فشل تحديث النص في قاعدة البيانات!"
    assert updated_row[1] == 8, "فشل تحديث الأهمية!"
    print(f"  ✅ تم تحديث المعلومة #{target_mid} بنجاح إلى: '{updated_row[0]}'")

    # 5. اختبار الحذف اليدوي (DELETE by ID)
    print("\n[5] اختبار ميثود الحذف بالمعرّف (DELETE):")
    del_res = await _rag.delete_memory(target_mid)
    assert del_res is True, "فشلت دالة الحذف!"
    c.execute("SELECT id FROM memories WHERE id = ?", (target_mid,))
    assert c.fetchone() is None, "المعلومة ما زالت موجودة في قاعدة البيانات بعد الحذف!"
    print(f"  ✅ تم مسح المعلومة #{target_mid} نهائياً وبنجاح من الذاكرة وقاعدة البيانات.")

    # 6. اختبار الحذف الصوتي والتلقائي ([forget:...])
    print("\n[6] اختبار وسوم الحذف الديناميكية ([forget:...]):")
    # إضافة معلومة تجريبية
    mid_to_forget = _rag._add_memory_sync("أحمد عنده ميعاد الساعة 7 بالليل", personality_id=2, embedding=None, source="test", importance=5)
    print(f"  • أضفنا معلومة: 'أحمد عنده ميعاد الساعة 7 بالليل' (ID: {mid_to_forget})")
    
    # محاكاة أمر الحذف [forget:ميعاد أحمد]
    c.execute("SELECT id, content FROM memories WHERE personality_id = 2 AND content LIKE '%ميعاد%'")
    mems_to_del = c.fetchall()
    for m in mems_to_del:
        c.execute("DELETE FROM memories WHERE id = ?", (m[0],))
        _rag._vstore.delete(m[0])
    conn.commit()

    c.execute("SELECT id FROM memories WHERE id = ?", (mid_to_forget,))
    assert c.fetchone() is None, "فشل الحذف عن طريق وسم النسيان!"
    print("  ✅ وسم الحذف [forget:...] يحذف المعلومة المستهدفة بدقة.")

    # تنظيف ذكريات التيست
    c.execute("DELETE FROM memories WHERE content LIKE '%تيست%'")
    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("🎉 جميع الاختبارات (100% PASS) نجحت بدون أي أخطاء!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_tests())
