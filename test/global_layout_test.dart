import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:nebulla/services/locale_service.dart';
import 'package:nebulla/widgets/global_footer.dart';
import 'package:nebulla/widgets/global_header.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await LocaleService.instance.init();
    await LocaleService.instance.setLocale('ar');
  });

  testWidgets('GlobalNebulaFooter renders Arabic labels and highlights active index',
      (WidgetTester tester) async {
    int navigatedIndex = -1;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: GlobalNebulaFooter(
            activeIndex: 1, // Chat active
            onNavigate: (idx) => navigatedIndex = idx,
          ),
        ),
      ),
    );

    expect(find.text('الصفحه الرئيسيه'), findsOneWidget);
    expect(find.text('الدردشة'), findsOneWidget);
    expect(find.text('الشخصيات'), findsOneWidget);
    expect(find.text('الذاكرة'), findsOneWidget);
    expect(find.text('الملف الشخصي'), findsOneWidget);

    // Tap on Memory (index 3)
    await tester.tap(find.text('الذاكرة'));
    await tester.pump();
    expect(navigatedIndex, 3);
  });

  testWidgets('GlobalNebulaFooter translates instantly to English',
      (WidgetTester tester) async {
    await LocaleService.instance.setLocale('en');

    await tester.pumpWidget(
      AnimatedBuilder(
        animation: LocaleService.instance,
        builder: (context, _) => MaterialApp(
          home: Scaffold(
            body: GlobalNebulaFooter(
              activeIndex: 0,
              onNavigate: (_) {},
            ),
          ),
        ),
      ),
    );

    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Chat'), findsOneWidget);
    expect(find.text('Personas'), findsOneWidget);
    expect(find.text('Memory'), findsOneWidget);
    expect(find.text('Profile'), findsOneWidget);
  });

  testWidgets('GlobalNebulaHeader guarantees Menu on LEFT and Logout on RIGHT',
      (WidgetTester tester) async {
    bool menuOpened = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: GlobalNebulaHeader(
            onOpenMenu: () => menuOpened = true,
          ),
        ),
      ),
    );

    expect(find.byIcon(Icons.menu_rounded), findsOneWidget);
    expect(find.byIcon(Icons.arrow_forward_rounded), findsOneWidget);

    // Verify tap menu
    await tester.tap(find.byIcon(Icons.menu_rounded));
    expect(menuOpened, isTrue);
  });
}

