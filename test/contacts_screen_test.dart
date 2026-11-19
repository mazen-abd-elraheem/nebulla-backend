import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nebulla/screens/contacts_screen.dart';

void main() {
  testWidgets('ContactsScreen renders light futuristic header, tabs, and FAB',
      (WidgetTester tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      const MaterialApp(
        home: ContactsScreen(),
      ),
    );
    await tester.pump();

    // Verify Header Elements
    expect(find.text('جهات الاتصال والتليفون'), findsOneWidget);
    expect(find.text('تحكم في الأرقام التي يتواصل معها نيبولا بصوتك'), findsOneWidget);
    expect(find.byIcon(Icons.menu_rounded), findsOneWidget);
    expect(find.byIcon(Icons.sync_rounded), findsNWidgets(2));

    // Verify Search Bar
    expect(find.text('ابحث بالاسم أو الرقم أو صلة القرابة...'), findsOneWidget);
    expect(find.byIcon(Icons.search_rounded), findsOneWidget);

    // Verify Segmented Control Tabs
    expect(find.textContaining('جهات نيبولا'), findsOneWidget);
    expect(find.text('دليل الموبايل'), findsOneWidget);

    // Verify Floating Action Button
    expect(find.text('جهة جديدة'), findsOneWidget);
    expect(find.byIcon(Icons.person_add_rounded), findsOneWidget);
  });
}
