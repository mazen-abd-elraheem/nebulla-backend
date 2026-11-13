import 'package:flutter/material.dart';
import '../services/locale_service.dart';
import '../services/storage_service.dart';
import '../screens/login_screen.dart';

/// Reusable Global Header Component
/// - Guaranteed Sidebar Hamburger on the LEFT side
/// - Guaranteed Logout Button on the RIGHT side
/// - Real-time language switching (Arabic / English)
/// - Personality branding and status indicator
class GlobalNebulaHeader extends StatelessWidget {
  final VoidCallback onOpenMenu;
  final String? title;
  final String? subtitle;
  final bool showLogout;
  final bool showLangSwitch;

  const GlobalNebulaHeader({
    super.key,
    required this.onOpenMenu,
    this.title,
    this.subtitle,
    this.showLogout = true,
    this.showLangSwitch = true,
  });

  Future<void> _handleLogout(BuildContext context) async {
    final t = LocaleService.instance.translate;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => Directionality(
        textDirection: LocaleService.instance.textDirection,
        child: AlertDialog(
          backgroundColor: Colors.white,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: Text(
            t('logout'),
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontWeight: FontWeight.w800,
              fontSize: 18,
              color: Color(0xFF0F172A),
            ),
          ),
          content: Text(
            LocaleService.instance.isArabic
                ? 'هل أنت متأكد من تسجيل الخروج من حسابك؟'
                : 'Are you sure you want to sign out from your account?',
            style: const TextStyle(
              fontFamily: 'Cairo',
              fontSize: 14,
              color: Color(0xFF475569),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text(
                t('cancel'),
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  color: Color(0xFF64748B),
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF0F172A), // Black background button
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                ),
                elevation: 0,
              ),
              onPressed: () => Navigator.of(ctx).pop(true),
              child: Text(
                t('logout'),
                style: const TextStyle(
                  fontFamily: 'Cairo',
                  fontWeight: FontWeight.w800,
                  color: Color(0xFFEF4444),
                ),
              ),
            ),
          ],
        ),
      ),
    );

    if (confirmed == true && context.mounted) {
      await StorageService.instance.clearToken();
      if (context.mounted) {
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const LoginScreen()),
          (route) => false,
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final locale = LocaleService.instance;
    final t = locale.translate;

    // Enforce fixed visual layout: LEFT = Menu & Branding, RIGHT = Lang & Logout
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border(
            bottom: BorderSide(
              color: const Color(0xFFE2E8F0).withValues(alpha: 0.8),
              width: 1,
            ),
          ),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF0F172A).withValues(alpha: 0.03),
              blurRadius: 10,
              offset: const Offset(0, 3),
            ),
          ],
        ),
        child: SafeArea(
          bottom: false,
          child: Row(
            children: [
              // 1. LEFT SIDE: Menu Button (strictly on the left)
              InkWell(
                onTap: onOpenMenu,
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(
                    color: const Color(0xFF0F172A), // Black button styling
                    borderRadius: BorderRadius.circular(12),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.15),
                        blurRadius: 6,
                        offset: const Offset(0, 2),
                      ),
                    ],
                  ),
                  child: const Icon(
                    Icons.menu_rounded,
                    size: 20,
                    color: Colors.white,
                  ),
                ),
              ),
              const SizedBox(width: 12),

              // 2. CENTER-LEFT: Personality / App Identity
              Expanded(
                child: Directionality(
                  textDirection: locale.textDirection,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            title ?? t('brand_name'),
                            style: const TextStyle(
                              fontFamily: 'Cairo',
                              fontSize: 16,
                              fontWeight: FontWeight.w900,
                              color: Color(0xFF0F172A),
                              letterSpacing: -0.2,
                            ),
                          ),
                          const SizedBox(width: 6),
                          Container(
                            width: 7,
                            height: 7,
                            decoration: const BoxDecoration(
                              color: Color(0xFF10B981), // Active status dot
                              shape: BoxShape.circle,
                            ),
                          ),
                        ],
                      ),
                      Text(
                        subtitle ?? '${t('ai_assistant')} • ${t('online_now')}',
                        style: const TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: Color(0xFF64748B),
                        ),
                      ),
                    ],
                  ),
                ),
              ),

              // 3. RIGHT SIDE: Language Toggle & Logout Button (strictly on the right)
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // Language Switcher Pill
                  if (showLangSwitch)
                    InkWell(
                      onTap: () => locale.toggleLanguage(),
                      borderRadius: BorderRadius.circular(10),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 8, vertical: 5),
                        decoration: BoxDecoration(
                          color: const Color(0xFFF1F5F9),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: const Color(0xFFE2E8F0)),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.language_rounded,
                              size: 14,
                              color: Color(0xFF0284C7),
                            ),
                            const SizedBox(width: 4),
                            Text(
                              locale.isArabic ? 'EN' : 'عربي',
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11,
                                fontWeight: FontWeight.w800,
                                color: Color(0xFF0F172A),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  const SizedBox(width: 8),

                  // Black Logout Button (strictly on the RIGHT)
                  if (showLogout)
                    InkWell(
                      onTap: () => _handleLogout(context),
                      borderRadius: BorderRadius.circular(10),
                      child: Container(
                        height: 38,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: const Color(0xFF0F172A), // Black background
                          borderRadius: BorderRadius.circular(10),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.12),
                              blurRadius: 6,
                              offset: const Offset(0, 2),
                            ),
                          ],
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(
                              Icons.logout_rounded,
                              size: 15,
                              color: Color(0xFFF87171),
                            ),
                            const SizedBox(width: 6),
                            Text(
                              t('logout'),
                              style: const TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 11.5,
                                fontWeight: FontWeight.w800,
                                color: Colors.white,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

