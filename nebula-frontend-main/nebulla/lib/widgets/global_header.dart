import 'package:flutter/material.dart';
import '../services/locale_service.dart';
import '../services/storage_service.dart';
import '../screens/login_screen.dart';

/// Reusable Global Header Component
/// - Arabic mode: Menu on the LEFT, Logout/Exit on the RIGHT.
/// - English mode: Swaps between Menu (RIGHT) and Logout/Exit (LEFT).
/// - Removed 'المساعد الذكي' from header as requested.
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
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
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
                ? 'هل أنت متأكد من تسجيل الخروج؟'
                : 'Are you sure you want to sign out?',
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
                backgroundColor: const Color(0xFF0F172A), // Black background
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
    final isArabic = locale.isArabic;
    final t = locale.translate;

    // Menu Widget (Transparent background)
    final menuBtn = InkWell(
      onTap: onOpenMenu,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: const Color(0xFFCBD5E1),
            width: 1.4,
          ),
        ),
        child: const Icon(
          Icons.menu_rounded,
          size: 20,
          color: Color(0xFF0F172A),
        ),
      ),
    );

    // Exit Arrow Widget (Transparent background matching other screens)
    final logoutSection = showLogout
        ? InkWell(
            onTap: () => _handleLogout(context),
            borderRadius: BorderRadius.circular(12),
            child: Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: Colors.transparent,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: const Color(0xFFCBD5E1),
                  width: 1.4,
                ),
              ),
              child: Icon(
                isArabic
                    ? Icons.arrow_forward_rounded
                    : Icons.arrow_back_rounded,
                size: 20,
                color: const Color(0xFF0F172A),
              ),
            ),
          )
        : const SizedBox.shrink();

    // Swap Menu and Logout between Arabic (Menu=LEFT, Logout=RIGHT) and English (Menu=RIGHT, Logout=LEFT)
    final leftSide = isArabic ? menuBtn : logoutSection;
    final rightSide = isArabic ? logoutSection : menuBtn;

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
              // Visual LEFT
              leftSide,
              const SizedBox(width: 12),

              // Visual CENTER (Brand Name + status indicator, 'المساعد الذكي' removed)
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
                        ],
                      ),
                      Text(
                        subtitle ?? t('online_now'),
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

              // Visual RIGHT
              rightSide,
            ],
          ),
        ),
      ),
    );
  }
}
