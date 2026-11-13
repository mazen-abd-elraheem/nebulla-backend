import 'dart:ui';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
import '../services/locale_service.dart';
import '../services/storage_service.dart';
import '../screens/login_screen.dart';
import '../screens/register_screen.dart';
import '../screens/main_shell.dart';

/// Nebula Side Menu redesigned to match Image 2 reference exactly:
/// - Clean close button (X) at the top without English switch
/// - Elegant AI Header card with avatar thumbnail (AI - 01) and 'المساعد الذكي' (no overflow)
/// - Items matching mockup: تسجيل الدخول, إنشاء حساب (جديد), إضافة شخصية, الدردشة (نشط), الأجهزة, الشخصيات
/// - Bottom dark button with cyan icon and 'خروج'
class NebulaSideMenu extends StatelessWidget {
  final int activeIndex;
  final ValueChanged<int>? onNavigate;
  final VoidCallback? onClose;

  const NebulaSideMenu({
    super.key,
    this.activeIndex = 1,
    this.onNavigate,
    this.onClose,
  });

  static Future<void> show(
    BuildContext context, {
    int activeIndex = 1,
    ValueChanged<int>? onNavigate,
  }) {
    return showGeneralDialog(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'SideMenu',
      barrierColor: Colors.black.withValues(alpha: 0.4),
      transitionDuration: const Duration(milliseconds: 260),
      transitionBuilder: (context, anim1, anim2, child) {
        final isArabic = LocaleService.instance.isArabic;
        final slide = Tween<Offset>(
          begin: Offset(isArabic ? -1.0 : 1.0, 0.0),
          end: Offset.zero,
        ).animate(CurvedAnimation(parent: anim1, curve: Curves.easeOutCubic));

        return SlideTransition(
          position: slide,
          child: child,
        );
      },
      pageBuilder: (context, anim1, anim2) {
        return Directionality(
          textDirection: LocaleService.instance.textDirection,
          child: Material(
            color: Colors.transparent,
            child: NebulaSideMenu(
              activeIndex: activeIndex,
              onNavigate: (idx) {
                Navigator.of(context).pop();
                onNavigate?.call(idx);
              },
              onClose: () => Navigator.of(context).pop(),
            ),
          ),
        );
      },
    );
  }

  void _handleItemTap(BuildContext context, int targetIdx) {
    if (onClose != null) {
      onClose!();
    } else {
      Navigator.of(context).maybePop();
    }

    if (targetIdx == -1) {
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const LoginScreen()),
      );
      return;
    }
    if (targetIdx == -2) {
      Navigator.of(context).push(
        MaterialPageRoute(builder: (_) => const RegisterScreen()),
      );
      return;
    }

    if (onNavigate != null) {
      onNavigate!(targetIdx);
    }
    MainShell.navigateTo(context, targetIdx);
  }

  @override
  Widget build(BuildContext context) {
    final audioService = AvatarAudioService.instance;
    final locale = LocaleService.instance;
    final isArabic = locale.isArabic;

    return Directionality(
      textDirection: locale.textDirection,
      child: Material(
        color: Colors.transparent,
        child: Stack(
          children: [
            // Tap outside backdrop to dismiss
            Positioned.fill(
              child: GestureDetector(
                onTap: onClose ?? () => Navigator.of(context).maybePop(),
                behavior: HitTestBehavior.opaque,
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
                  child: Container(
                    color: Colors.black.withValues(alpha: 0.15),
                  ),
                ),
              ),
            ),

            // Side Menu Card: Left in Arabic, Right in English
            Align(
              alignment: isArabic ? Alignment.centerLeft : Alignment.centerRight,
              child: Container(
                width: 310,
                height: double.infinity,
                margin: const EdgeInsets.symmetric(vertical: 20, horizontal: 16),
                decoration: BoxDecoration(
                  color: const Color(0xFFF8FAFC),
                  borderRadius: BorderRadius.circular(28),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.15),
                      blurRadius: 36,
                      offset: const Offset(6, 0),
                    ),
                  ],
                ),
                child: SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        // 1. Top Close Button (X) Only - EN toggle removed per user request
                        Align(
                          alignment: isArabic ? Alignment.centerLeft : Alignment.centerRight,
                          child: InkWell(
                            onTap: onClose ?? () => Navigator.of(context).maybePop(),
                            borderRadius: BorderRadius.circular(20),
                            child: Container(
                              width: 36,
                              height: 36,
                              decoration: BoxDecoration(
                                color: Colors.white,
                                shape: BoxShape.circle,
                                border: Border.all(color: const Color(0xFFE2E8F0)),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.04),
                                    blurRadius: 6,
                                    offset: const Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: const Icon(
                                Icons.close_rounded,
                                size: 18,
                                color: Color(0xFF475569),
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(height: 12),

                        // 2. AI Header Card matching Image 2 reference (clean, no overflow)
                        ValueListenableBuilder<String>(
                          valueListenable: audioService.activeAvatarType,
                          builder: (context, avatarType, _) {
                            final isFemale = avatarType == 'female';
                            final avatarImg = isFemale
                                ? 'assets/images/avatar_female.png'
                                : 'assets/images/avatar_male.jpg';

                            return Container(
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(color: const Color(0xFFE2E8F0)),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.04),
                                    blurRadius: 10,
                                    offset: const Offset(0, 4),
                                  ),
                                ],
                              ),
                              child: Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  // Title: المساعد الذكي
                                  Expanded(
                                    child: Text(
                                      isArabic ? 'المساعد الذكي' : 'Smart Assistant',
                                      style: const TextStyle(
                                        fontFamily: 'Cairo',
                                        fontWeight: FontWeight.w800,
                                        fontSize: 15,
                                        color: Color(0xFF1E293B),
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 12),

                                  // Avatar Image with AI-01 badge
                                  Stack(
                                    clipBehavior: Clip.none,
                                    children: [
                                      Container(
                                        width: 48,
                                        height: 48,
                                        decoration: BoxDecoration(
                                          borderRadius: BorderRadius.circular(14),
                                          border: Border.all(
                                            color: const Color(0xFF00B4D8),
                                            width: 1.5,
                                          ),
                                        ),
                                        child: ClipRRect(
                                          borderRadius: BorderRadius.circular(12),
                                          child: Image.asset(
                                            avatarImg,
                                            fit: BoxFit.cover,
                                            alignment: Alignment.topCenter,
                                          ),
                                        ),
                                      ),
                                      Positioned(
                                        bottom: -4,
                                        left: -2,
                                        child: Container(
                                          padding: const EdgeInsets.symmetric(
                                              horizontal: 5, vertical: 1.5),
                                          decoration: BoxDecoration(
                                            color: const Color(0xFF00B4D8),
                                            borderRadius: BorderRadius.circular(6),
                                          ),
                                          child: Text(
                                            isFemale ? 'AI - 02' : 'AI - 01',
                                            style: const TextStyle(
                                              fontFamily: 'Cairo',
                                              fontSize: 8.5,
                                              fontWeight: FontWeight.bold,
                                              color: Colors.white,
                                            ),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                        const SizedBox(height: 16),

                        // 3. Navigation Menu Items List matching Image 2 exactly
                        Expanded(
                          child: ListView(
                            padding: EdgeInsets.zero,
                            children: [
                              // 1: تسجيل الدخول
                              _MenuItemCard(
                                title: isArabic ? 'تسجيل الدخول' : 'Sign In',
                                icon: Icons.login_rounded,
                                iconBoxColor: const Color(0xFFE0F2FE),
                                iconColor: const Color(0xFF0284C7),
                                hasArrow: true,
                                onTap: () => _handleItemTap(context, -1),
                              ),
                              const SizedBox(height: 9),

                              // 2: إنشاء حساب (جديد)
                              _MenuItemCard(
                                title: isArabic ? 'إنشاء حساب' : 'Create Account',
                                icon: Icons.person_add_alt_1_rounded,
                                iconBoxColor: const Color(0xFFDCFCE7),
                                iconColor: const Color(0xFF16A34A),
                                badgeText: isArabic ? 'جديد' : 'New',
                                badgeColor: const Color(0xFF10B981),
                                badgeTextColor: Colors.white,
                                onTap: () => _handleItemTap(context, -2),
                              ),
                              const SizedBox(height: 9),

                              // 3: إضافة شخصية
                              _MenuItemCard(
                                title: isArabic ? 'إضافة شخصية' : 'Add Persona',
                                icon: Icons.add_rounded,
                                iconBoxColor: const Color(0xFFEDE9FE),
                                iconColor: const Color(0xFF7C3AED),
                                hasArrow: true,
                                onTap: () => _handleItemTap(context, 2),
                              ),
                              const SizedBox(height: 9),

                              // 4: الدردشة (ACTIVE Highlight matching Image 2)
                              _MenuItemCard(
                                title: isArabic ? 'الدردشة' : 'Chat',
                                icon: Icons.chat_bubble_outline_rounded,
                                iconBoxColor: const Color(0xFFE0F2FE),
                                iconColor: const Color(0xFF0284C7),
                                isActive: activeIndex == 1,
                                badgeText: activeIndex == 1
                                    ? (isArabic ? 'نشط' : 'Active')
                                    : null,
                                badgeColor: Colors.white,
                                badgeTextColor: const Color(0xFF1E88E5),
                                onTap: () => _handleItemTap(context, 1),
                              ),
                              const SizedBox(height: 9),

                              // 5: الأجهزة
                              _MenuItemCard(
                                title: isArabic ? 'الأجهزة' : 'Devices',
                                icon: Icons.computer_rounded,
                                iconBoxColor: const Color(0xFFFEF3C7),
                                iconColor: const Color(0xFFD97706),
                                hasPillIndicator: true,
                                isActive: activeIndex == 4,
                                onTap: () => _handleItemTap(context, 4),
                              ),
                              const SizedBox(height: 9),

                              // 6: الشخصيات
                              _MenuItemCard(
                                title: isArabic ? 'الشخصيات' : 'Personas',
                                icon: Icons.groups_rounded,
                                iconBoxColor: const Color(0xFFF3E8FF),
                                iconColor: const Color(0xFF9333EA),
                                hasArrow: true,
                                isActive: activeIndex == 2,
                                onTap: () => _handleItemTap(context, 2),
                              ),
                            ],
                          ),
                        ),

                        // 4. Divider with Cyan Indicator Dot
                        Row(
                          children: [
                            const Expanded(
                              child: Divider(
                                color: Color(0xFFE2E8F0),
                                thickness: 1.2,
                              ),
                            ),
                            const SizedBox(width: 8),
                            Container(
                              width: 8,
                              height: 8,
                              decoration: const BoxDecoration(
                                color: Color(0xFF00E5FF),
                                shape: BoxShape.circle,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),

                        // 5. Logout Button: Dark button with cyan icon and 'خروج' matching Image 2
                        InkWell(
                          onTap: () async {
                            await StorageService.instance.clearToken();
                            if (context.mounted) {
                              Navigator.of(context).pushAndRemoveUntil(
                                MaterialPageRoute(builder: (_) => const LoginScreen()),
                                (route) => false,
                              );
                            }
                          },
                          borderRadius: BorderRadius.circular(16),
                          child: Container(
                            height: 48,
                            decoration: BoxDecoration(
                              color: const Color(0xFF0F172A),
                              borderRadius: BorderRadius.circular(16),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: 0.15),
                                  blurRadius: 10,
                                  offset: const Offset(0, 3),
                                ),
                              ],
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                const Icon(
                                  Icons.logout_rounded,
                                  color: Color(0xFF00E5FF),
                                  size: 20,
                                ),
                                const SizedBox(width: 8),
                                Text(
                                  isArabic ? 'خروج' : 'Logout',
                                  style: const TextStyle(
                                    fontFamily: 'Cairo',
                                    fontWeight: FontWeight.bold,
                                    fontSize: 14.5,
                                    color: Colors.white,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Menu item card matching Image 2:
/// - Rounded white card (or vibrant blue when active)
/// - Pastel icon container on the right
/// - Arrow / badge / pill indicator on the left
class _MenuItemCard extends StatelessWidget {
  final String title;
  final IconData icon;
  final Color iconBoxColor;
  final Color iconColor;
  final bool isActive;
  final bool hasArrow;
  final bool hasPillIndicator;
  final String? badgeText;
  final Color? badgeColor;
  final Color? badgeTextColor;
  final VoidCallback? onTap;

  const _MenuItemCard({
    required this.title,
    required this.icon,
    required this.iconBoxColor,
    required this.iconColor,
    this.isActive = false,
    this.hasArrow = false,
    this.hasPillIndicator = false,
    this.badgeText,
    this.badgeColor,
    this.badgeTextColor,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeInOut,
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
        decoration: BoxDecoration(
          color: isActive ? const Color(0xFF1E88E5) : Colors.white,
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: isActive ? const Color(0xFF1E88E5) : const Color(0xFFF1F5F9),
            width: 1.2,
          ),
          boxShadow: isActive
              ? [
                  BoxShadow(
                    color: const Color(0xFF1E88E5).withValues(alpha: 0.35),
                    blurRadius: 10,
                    offset: const Offset(0, 4),
                  ),
                ]
              : [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.02),
                    blurRadius: 4,
                    offset: const Offset(0, 2),
                  ),
                ],
        ),
        child: Row(
          children: [
            // Left Side: Badge, Arrow, or Pill indicator
            if (badgeText != null)
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: badgeColor ?? const Color(0xFF10B981),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  badgeText!,
                  style: TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 10.5,
                    fontWeight: FontWeight.bold,
                    color: badgeTextColor ?? Colors.white,
                  ),
                ),
              )
            else if (hasArrow)
              const Icon(
                Icons.arrow_back_rounded,
                size: 15,
                color: Color(0xFF94A3B8),
              )
            else if (hasPillIndicator)
              Container(
                width: 7,
                height: 14,
                decoration: BoxDecoration(
                  color: const Color(0xFFCBD5E1),
                  borderRadius: BorderRadius.circular(4),
                ),
              )
            else
              const SizedBox(width: 15),

            const Spacer(),

            // Title
            Text(
              title,
              style: TextStyle(
                fontFamily: 'Cairo',
                fontWeight: isActive ? FontWeight.bold : FontWeight.w600,
                fontSize: 14,
                color: isActive ? Colors.white : const Color(0xFF1E293B),
              ),
            ),
            const SizedBox(width: 12),

            // Icon Container
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: isActive
                    ? Colors.white.withValues(alpha: 0.22)
                    : iconBoxColor,
                borderRadius: BorderRadius.circular(10),
              ),
              child: Icon(
                icon,
                color: isActive ? Colors.white : iconColor,
                size: 19,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
