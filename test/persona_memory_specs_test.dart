import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nebulla/screens/persona_memory_specs_screen.dart';
import 'package:nebulla/screens/register_screen.dart';

void main() {
  testWidgets('RegisterScreen renders 4-step wizard: Step 0 Credentials',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const MaterialApp(
        home: RegisterScreen(initialStep: 0),
      ),
    );
    await tester.pump();

    // Verify Stepper Header
    expect(find.text('البيانات'), findsOneWidget);
    expect(find.text('الأفاتار'), findsOneWidget);
    expect(find.text('التخصيص'), findsOneWidget);
    expect(find.text('الصوت'), findsOneWidget);

    // Verify Credentials Form fields
    expect(find.text('إنشاء حساب جديد'), findsOneWidget);
    expect(find.text('الاسم كامل'), findsOneWidget);
    expect(find.text('البريد الإلكتروني'), findsOneWidget);
    expect(find.text('كلمة المرور'), findsOneWidget);
    expect(find.text('تأكيد كلمة المرور'), findsOneWidget);
    expect(find.text('المتابعة: خطوة الأفاتار'), findsOneWidget);
  });

  testWidgets('RegisterScreen Step 1 renders Profile Image to Avatar conversion',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const MaterialApp(
        home: RegisterScreen(initialStep: 1),
      ),
    );
    await tester.pump();

    expect(find.text('تحويل صورتك إلى أفاتار ذكي'), findsOneWidget);
    expect(find.text('إضافة صورة شخصية'), findsOneWidget);
    expect(find.text('الكاميرا'), findsOneWidget);
    expect(find.text('المعرض'), findsOneWidget);
    expect(find.text('تأكيد الأفاتار ومتابعة لأسئلة التخصيص'), findsOneWidget);
  });

  testWidgets('RegisterScreen Step 2 renders Expandable AI Onboarding Questions',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const MaterialApp(
        home: RegisterScreen(initialStep: 2),
      ),
    );
    await tester.pump();

    // Verify expandable questionnaire title matching user image
    expect(find.text('أسئلة تخصيص الذكاء الاصطناعي'), findsOneWidget);

    // Verify questions appear
    expect(find.text('1. ما هو أسلوب التفاعل المفضل لديك؟'), findsOneWidget);
    expect(find.text('2. ما هو مجال اهتمامك الأساسي؟'), findsOneWidget);
    expect(find.text('3. معلومة شخصية تريد من المساعد حفظها بذاكرته:'), findsOneWidget);
    expect(find.text('نصي وصوتي'), findsOneWidget);
    expect(find.text('البرمجة والتقنية'), findsOneWidget);
    expect(find.text('حفظ التخصيص ومتابعة لاستنساخ الصوت'), findsOneWidget);
  });

  testWidgets('RegisterScreen Step 3 renders XTTS Voice Cloning interface',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const MaterialApp(
        home: RegisterScreen(initialStep: 3),
      ),
    );
    await tester.pump();

    expect(find.text('استنساخ صوتك بالذكاء الاصطناعي'), findsOneWidget);
    expect(find.text('الجملة المقترحة للقراءة بصوتك:'), findsOneWidget);
    expect(find.byIcon(Icons.mic_rounded), findsNWidgets(2));
    expect(find.text('إتمام التسجيل والبدء في نيبولا'), findsOneWidget);
  });

  testWidgets('PersonaMemorySpecsScreen renders header with menu and exit buttons',
      (WidgetTester tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: PersonaMemorySpecsScreen(),
      ),
    );
    await tester.pump();

    // Verify title and icons
    expect(find.text('ذاكرة ومواصفات الشخصية'), findsOneWidget);
    expect(find.byIcon(Icons.menu_rounded), findsOneWidget);
    expect(find.byIcon(Icons.arrow_forward_rounded), findsOneWidget);
  });
}
