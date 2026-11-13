import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:nebulla/services/locale_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await LocaleService.instance.init();
  });

  test('LocaleService initializes with Arabic as default', () {
    final service = LocaleService.instance;
    expect(service.isArabic, isTrue);
    expect(service.languageCode, 'ar');
    expect(service.textDirection, TextDirection.rtl);
    expect(service.translate('nav_home'), 'الصفحه الرئيسيه');
    expect(service.translate('logout'), 'تسجيل الخروج');
  });

  test('LocaleService switches to English and updates layout direction', () async {
    final service = LocaleService.instance;
    await service.setLocale('en');

    expect(service.isArabic, isFalse);
    expect(service.languageCode, 'en');
    expect(service.textDirection, TextDirection.ltr);
    expect(service.translate('nav_home'), 'Home');
    expect(service.translate('nav_chat'), 'Chat');
    expect(service.translate('logout'), 'Logout');
  });

  test('LocaleService toggles between languages seamlessly', () async {
    final service = LocaleService.instance;
    await service.setLocale('ar');
    expect(service.isArabic, isTrue);

    service.toggleLanguage();
    expect(service.isArabic, isFalse);
    expect(service.languageCode, 'en');

    service.toggleLanguage();
    expect(service.isArabic, isTrue);
    expect(service.languageCode, 'ar');
  });
}

