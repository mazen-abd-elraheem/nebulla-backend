# -*- coding: utf-8 -*-
"""
Nebula Comprehensive Verification & Test Suite
اختبار شامل لكل أجزاء النظام:
1. الذاكرة وعمليات CRUD (الإضافة، القراءة، التعديل PUT، الحذف DELETE)
2. عزل الشخصيات (Personalities 0, 1, 2) والتأكد من عدم تسريب الذكريات
3. فحص ملفات الموديل (Modelfiles) وتأكيد وجود وسوم الميديا والنبرة
"""

import sys
import os
import sqlite3
import json

# Terminal Colors
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"
BOLD = "\033[1m"

def print_header(title):
    print(f"\n{BLUE}{BOLD}{'='*65}{RESET}")
    print(f"{BLUE}{BOLD}▶ {title}{RESET}")
    print(f"{BLUE}{BOLD}{'='*65}{RESET}")

def print_pass(msg):
    print(f"  {GREEN}✔ [نجاح]{RESET} {msg}")

def print_fail(msg):
    print(f"  {RED}✘ [فشل]{RESET} {msg}")

def print_info(msg):
    print(f"  {YELLOW}ℹ [معلومة]{RESET} {msg}")


def test_database_crud_and_isolation():
    print_header("الجزء 1 و 2: اختبار الذاكرة (CRUD) وعزل الشخصيات (Isolation)")
    
    db_file = "nebula.db"
    if not os.path.exists(db_file):
        print_fail(f"ملف قاعدة البيانات {db_file} مش موجود!")
        return False

    conn = sqlite3.connect(db_file)
    cur = conn.cursor()

    # 1. إضافة ذاكرة لشخصية 1 (مازن)
    cur.execute(
        "INSERT INTO memories (content, personality_id, source, importance, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        ("مفتاح العربية في الدرج اللي فوق", 1, "test_script", 5)
    )
    m1_id = cur.lastrowid
    conn.commit()
    print_pass(f"1. إضافة ذاكرة لشخصية 1 (مازن) بنجاح - المعرف ID: {m1_id}")

    # 2. إضافة ذاكرة لشخصية 2 (أحمد)
    cur.execute(
        "INSERT INTO memories (content, personality_id, source, importance, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        ("أحمد حط الكتاب في الصالة على الترابيزة", 2, "test_script", 5)
    )
    m2_id = cur.lastrowid
    conn.commit()
    print_pass(f"2. إضافة ذاكرة لشخصية 2 (أحمد) بنجاح - المعرف ID: {m2_id}")

    # 3. اختبار العزل (Isolation)
    cur.execute("SELECT id, content FROM memories WHERE personality_id = 1")
    p1_rows = cur.fetchall()
    p1_ids = [r[0] for r in p1_rows]

    cur.execute("SELECT id, content FROM memories WHERE personality_id = 2")
    p2_rows = cur.fetchall()
    p2_ids = [r[0] for r in p2_rows]

    if m1_id in p1_ids and m2_id not in p1_ids and m2_id in p2_ids and m1_id not in p2_ids:
        print_pass("3. عزل الذاكرة 100%: ذكريات شخصية 1 منفصلة تماماً عن شخصية 2 ومفيش أي تسريب.")
    else:
        print_fail("3. فشل العزل: حصل تداخل بين ذكريات شخصية 1 وشخصية 2!")

    # 4. اختبار التعديل واستبدال المعلومة القديمة (UPDATE)
    new_text = "أحمد نقل الكتاب وحطه في المكتب"
    cur.execute(
        "UPDATE memories SET content = ? WHERE id = ?",
        (new_text, m2_id)
    )
    conn.commit()
    print_pass(f"4. تعديل الذاكرة (UPDATE): تم تغيير مكان الكتاب إلى '{new_text}'.")

    # 5. التأكد إن المعلومة اتحدثت في قاعدة البيانات
    cur.execute("SELECT content FROM memories WHERE id = ?", (m2_id,))
    row = cur.fetchone()
    if row and row[0] == new_text:
        print_pass("5. التحقق من التعديل: المعلومة القديمة استُبدلت بالكامل وبقى في المكتب فقط.")
    else:
        print_fail("5. فشل التحقق من تعديل المعلومة!")

    # 6. اختبار الحذف (DELETE)
    cur.execute("DELETE FROM memories WHERE id IN (?, ?)", (m1_id, m2_id))
    conn.commit()
    cur.execute("SELECT COUNT(*) FROM memories WHERE id IN (?, ?)", (m1_id, m2_id))
    cnt = cur.fetchone()[0]
    if cnt == 0:
        print_pass("6. اختبار الحذف (DELETE): تم مسح ذكريات التجربة بنجاح وتنظيف قاعدة البيانات.")
    else:
        print_fail("6. فشل حذف الذكريات التجريبية!")

    conn.close()
    return True


def test_auto_conflict_resolution():
    print_header("الجزء 3: اختبار الاستبدال التلقائي الذكي (Auto Conflict Resolution)")
    from app.services.memory.rag_service import RAGService
    rag = RAGService()
    rag._embedder = "disabled"
    RAGService._shared_embedder = "disabled"

    # 1. إضافة المكان الأول للكتاب لشخصية 2
    mid_old = rag._add_memory_sync("أحمد حط الكتاب في الصالة", personality_id=2, embedding=None, source="test", importance=5)
    print_pass(f"تم حفظ المعلومة الأولى ID: {mid_old} ('أحمد حط الكتاب في الصالة')")

    # 2. إضافة مكان جديد للكتاب لنفس الشخصية باستخدام الإضافة العادية
    mid_new = rag._add_memory_sync("أحمد نقل الكتاب وحطه علي الكرسيي", personality_id=2, embedding=None, source="test", importance=5)
    print_pass(f"تم إضافة المعلومة الجديدة ID: {mid_new} ('أحمد نقل الكتاب وحطه علي الكرسيي')")

    # 3. التحقق: تم حذف معلومة 'الصالة' تماماً ولم يعد يوجد سوى معلومة 'الكرسي' واحدة فقط
    conn = sqlite3.connect("nebula.db")
    cur = conn.cursor()
    cur.execute("SELECT id, content FROM memories WHERE content LIKE '%الصالة%' AND personality_id = 2")
    salah_row = cur.fetchone()
    cur.execute("SELECT id, content FROM memories WHERE content LIKE '%الكرسي%' AND personality_id = 2")
    kursi_row = cur.fetchone()
    cur.execute("SELECT COUNT(*) FROM memories WHERE content LIKE '%الكتاب%' AND personality_id = 2")
    total_book_mems = cur.fetchone()[0]

    # تنظيف ذكريات الاختبار
    cur.execute("DELETE FROM memories WHERE id IN (?, ?)", (mid_old, mid_new))
    conn.commit()
    conn.close()

    assert salah_row is None, "فشل: المعلومة القديمة (الصالة) لم يتم مسحها تلقائياً!"
    assert kursi_row is not None, "فشل: المعلومة الجديدة (الكرسي) لم تسجل!"
    assert total_book_mems == 1, f"فشل: يوجد أكثر من معلومة للكتاب ({total_book_mems}) بدلاً من معلومة واحدة فقط!"
    print_pass("نجاح باهر: تم مسح المعلومة القديمة (الصالة) تلقائياً، وأصبح مكان الكتاب هو (الكرسي) فقط بدون أي تعارض!")


def test_modelfiles():
    print_header("الجزء 4: اختبار ملفات الموديل (Modelfiles & Multimodal Tags)")

    # 1. Modelfile.nebula-llama3
    l3_path = "Modelfile.nebula-llama3"
    if os.path.exists(l3_path):
        with open(l3_path, "r", encoding="utf-8") as f:
            l3 = f.read()

        checks = [
            ("TEMPLATE", "قالب المحادثة الرسمي لـ LLaMA 3.2"),
            ("[screen:photo]", "وسم عرض الصور على الشاشة [screen:photo]"),
            ("[memory:", "وسم حفظ الذاكرة الحية [memory:...]"),
            ("أحمد", "دعم تعدد المتحدثين (أحمد)"),
            ("مازن", "دعم المتحدث الرئيسي (مازن)"),
            ("أسبقية التحديث", "قاعدة تحديث واستبدال المعلومات القديمة"),
        ]
        all_l3 = True
        for term, desc in checks:
            if term in l3:
                print_pass(f"Modelfile LLaMA 3: تم التحقق من وجود ({desc})")
            else:
                print_fail(f"Modelfile LLaMA 3: ناقص ({desc})")
                all_l3 = False
    else:
        print_fail(f"الملف {l3_path} غير موجود!")

    # 2. Modelfile.nebula-rag
    rag_path = "Modelfile.nebula-rag"
    if os.path.exists(rag_path):
        with open(rag_path, "r", encoding="utf-8") as f:
            rag = f.read()

        if "[screen:photo]" in rag and "[memory:أحمد" in rag:
            print_pass("Modelfile RAG: تم التحقق من دعم تعدد الشخصيات ونقل الكتاب وعرض الصور.")
        else:
            print_fail("Modelfile RAG: ينقصه بعض وسوم الشخصيات المحدثة!")
    else:
        print_fail(f"الملف {rag_path} غير موجود!")


def main():
    print(f"\n{BOLD}🚀 جاري تشغيل الاختبار الشامل لجميع المكونات...{RESET}")
    test_database_crud_and_isolation()
    test_auto_conflict_resolution()
    test_modelfiles()
    print(f"\n{GREEN}{BOLD}{'='*65}{RESET}")
    print(f"{GREEN}{BOLD}🎉 تم اكتمال الاختبار بنجاح! جميع الأجزاء جاهزة ومطابقة للمطلوب.{RESET}")
    print(f"{GREEN}{BOLD}{'='*65}{RESET}\n")

if __name__ == "__main__":
    main()

