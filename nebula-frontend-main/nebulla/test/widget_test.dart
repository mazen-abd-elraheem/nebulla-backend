import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:nebulla/main.dart';
import 'package:nebulla/screens/chat_screen.dart';
import 'package:nebulla/screens/dashboard_screen.dart';
import 'package:nebulla/screens/diagnostics_screen.dart';
import 'package:nebulla/screens/memory_personas_screen.dart';
import 'package:nebulla/services/storage_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await StorageService.instance.init();
  });

  testWidgets('App smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const NebulaApp());
    expect(find.byType(NebulaApp), findsOneWidget);
  });

  testWidgets('DashboardScreen renders cleanly', (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1200, 900);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const MaterialApp(
        home: Directionality(
          textDirection: TextDirection.rtl,
          child: DashboardScreen(),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('لوحة التحكم'), findsOneWidget);
    expect(find.text('حالة الاتصال'), findsOneWidget);
  });

  testWidgets('MemoryPersonasScreen renders with all components',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const MaterialApp(
        home: Directionality(
          textDirection: TextDirection.rtl,
          child: MemoryPersonasScreen(),
        ),
      ),
    );
    expect(find.text('إعداد الذاكرة والشخصيات'), findsOneWidget);
    expect(find.text('ذاكرة الوصول العشوائي'), findsOneWidget);
    expect(find.text('إضافة شخصية جديدة'), findsOneWidget);
    expect(find.text('إدارة الشخصيات'), findsOneWidget);
    expect(find.text('المساعد البحثي الأكاديمي'), findsWidgets);
    expect(find.text('الرفيق الودي التفاعلي'), findsOneWidget);
  });

  testWidgets('DiagnosticsScreen renders with all hardware components',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const MaterialApp(
        home: Directionality(
          textDirection: TextDirection.rtl,
          child: DiagnosticsScreen(),
        ),
      ),
    );
    expect(find.text('تحليل حالة hardware'), findsOneWidget);
    expect(find.text('نسبة طاقة البطارية والمكثفات'), findsOneWidget);
    expect(find.text('مصفوفة الفحص الشامل'), findsOneWidget);
    expect(find.text('وحدة الرؤية والعمق البصري'), findsOneWidget);
    expect(find.text('مصفوفة محركات السيرفو'), findsOneWidget);
    expect(find.text('تسجيل صوتك'), findsOneWidget);
    expect(find.text('معايرة زوايا الرأس والسيرفو'), findsOneWidget);
    expect(find.text('إعادة فحص المستشعرات الشامل'), findsOneWidget);
  });

  testWidgets('ChatScreen renders with full modern layout and welcome items',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const MaterialApp(
        home: Directionality(
          textDirection: TextDirection.rtl,
          child: ChatScreen(),
        ),
      ),
    );
    expect(find.text('المساعد الذكي'), findsWidgets);
    expect(find.text('متصل الآن'), findsOneWidget);
    expect(find.text('متصل الآن - استجابة فورية'), findsOneWidget);
    expect(find.text('جلسة جديدة'), findsOneWidget);
    expect(find.text('تلخيص نص طويل'), findsOneWidget);
    expect(find.text('اقتراح أفكار إبداعية'), findsOneWidget);
    expect(find.text('المساعدة في كتابة محتوى'), findsOneWidget);
  });
}
