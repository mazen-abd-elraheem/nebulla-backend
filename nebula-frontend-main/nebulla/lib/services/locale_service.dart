import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Centralized Localization Service supporting dynamic, immediate language
/// switching between Arabic ('ar') and English ('en') with persistent storage.
class LocaleService extends ChangeNotifier {
  static final LocaleService instance = LocaleService._();
  LocaleService._();

  static const String _storageKey = 'nebula_selected_language';

  Locale _locale = const Locale('ar');

  Locale get currentLocale => _locale;
  String get languageCode => _locale.languageCode;
  bool get isArabic => _locale.languageCode == 'ar';
  TextDirection get textDirection =>
      isArabic ? TextDirection.rtl : TextDirection.ltr;

  Future<void> init() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString(_storageKey);
      if (saved != null && (saved == 'ar' || saved == 'en')) {
        _locale = Locale(saved);
      }
    } catch (_) {}
  }

  Future<void> setLocale(String langCode) async {
    if (langCode != 'ar' && langCode != 'en') return;
    if (_locale.languageCode == langCode) return;

    _locale = Locale(langCode);
    notifyListeners();

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_storageKey, langCode);
    } catch (_) {}
  }

  void toggleLanguage() {
    setLocale(isArabic ? 'en' : 'ar');
  }

  /// Translations Dictionary for Global Layout, Navigation, Header, Sidebar, and Buttons
  String translate(String key) {
    final Map<String, Map<String, String>> strings = {
      // Navigation
      'nav_home': {'ar': 'الصفحه الرئيسيه', 'en': 'Home'},
      'nav_chat': {'ar': 'الدردشة', 'en': 'Chat'},
      'nav_personas': {'ar': 'الشخصيات', 'en': 'Personas'},
      'nav_profile': {'ar': 'الملف الشخصي', 'en': 'Profile'},
      'nav_devices': {'ar': 'الأجهزة', 'en': 'Devices'},
      'nav_settings': {'ar': 'الإعدادات', 'en': 'Settings'},

      // Header
      'brand_name': {'ar': 'نيبولا', 'en': 'NEBULLA'},
      'ai_assistant': {'ar': 'المساعد الذكي', 'en': 'Smart Assistant'},
      'online_now': {'ar': 'متصل الآن', 'en': 'Online'},
      'logout': {'ar': 'تسجيل الخروج', 'en': 'Logout'},
      'notifications': {'ar': 'الإشعارات', 'en': 'Notifications'},
      'menu': {'ar': 'القائمة', 'en': 'Menu'},
      'switch_lang': {'ar': 'English', 'en': 'العربية'},

      // Sidebar
      'side_title': {'ar': 'نيبولا الذكي', 'en': 'Nebulla AI'},
      'side_subtitle': {'ar': 'نظام الذكاء الاصطناعي التفاعلي', 'en': 'Interactive AI System'},
      'login': {'ar': 'تسجيل الدخول', 'en': 'Sign In'},
      'create_account': {'ar': 'إنشاء حساب', 'en': 'Create Account'},
      'new_badge': {'ar': 'جديد', 'en': 'New'},
      'active_badge': {'ar': 'نشط', 'en': 'Active'},
      'add_new_persona': {'ar': 'إضافة شخصية جديدة', 'en': 'Add New Persona'},
      'memory_personas': {'ar': 'إعداد الذاكرة والشخصيات', 'en': 'Memory & Personas'},
      'appearance_and_lang': {'ar': 'لغة التطبيق والمظهر', 'en': 'Language & Appearance'},
      'diagnostics': {'ar': 'فحص النظام والأجهزة', 'en': 'Diagnostics & System'},
      'privacy': {'ar': 'الخصوصية والبيانات', 'en': 'Privacy & Data'},
      'about': {'ar': 'عن التطبيق', 'en': 'About Nebulla'},

      // Buttons & Actions
      'save': {'ar': 'حفظ التغييرات', 'en': 'Save Changes'},
      'save_memory': {'ar': 'حفظ وتثبيت في الذاكرة', 'en': 'Save & Commit to Memory'},
      'cancel': {'ar': 'إلغاء / تفريغ', 'en': 'Cancel / Clear'},
      'edit': {'ar': 'تعديل', 'en': 'Edit'},
      'add': {'ar': '+ إضافة', 'en': '+ Add'},
      'import': {'ar': 'استيراد', 'en': 'Import'},
      'add_image': {'ar': 'إضافة صورة', 'en': 'Add Image'},
      'activate': {'ar': 'تفعيل', 'en': 'Activate'},
      'active_now': {'ar': 'نشط حالياً', 'en': 'Currently Active'},
      'confirm': {'ar': 'تأكيد', 'en': 'Confirm'},
      'back': {'ar': 'رجوع', 'en': 'Back'},
      'send': {'ar': 'إرسال', 'en': 'Send'},
      'type_message': {'ar': 'اكتب رسالتك هنا...', 'en': 'Type your message here...'},
    };

    final lang = _locale.languageCode;
    return strings[key]?[lang] ?? strings[key]?['ar'] ?? key;
  }
}

