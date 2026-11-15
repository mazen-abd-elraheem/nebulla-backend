import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nebulla/screens/persona_memory_specs_screen.dart';
import 'package:nebulla/screens/register_screen.dart';

void main() {
  testWidgets('RegisterScreen renders profile image picker and expandable questions',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const MaterialApp(
        home: RegisterScreen(),
      ),
    );
    await tester.pump();

    // Verify profile picture picker label
    expect(find.text('إضافة صورة شخصية'), findsOneWidget);

    // Verify expandable questionnaire title
    expect(find.text('أسئلة تخصيص الذكاء الاصطناعي'), findsOneWidget);
    expect(find.text('اضغط للإجابة عن أسئلة التخصيص'), findsOneWidget);

    // Tap to expand questions
    await tester.tap(find.text('أسئلة تخصيص الذكاء الاصطناعي'));
    await tester.pumpAndSettle();

    // Verify questions appear
    expect(find.text('1. ما هو أسلوب التفاعل المفضل لديك؟'), findsOneWidget);
    expect(find.text('2. ما هو مجال اهتمامك الأساسي؟'), findsOneWidget);
    expect(find.text('3. معلومة شخصية تريد من المساعد حفظها بذاكرته:'), findsOneWidget);
    expect(find.text('نصي وصوتي'), findsOneWidget);
    expect(find.text('البرمجة والتقنية'), findsOneWidget);
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
