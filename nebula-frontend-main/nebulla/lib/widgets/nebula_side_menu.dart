import 'dart:ui';
import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
import '../services/storage_service.dart';

/// The shared side menu overlay / drawer matching the provided design.
/// Can be opened from any screen via hamburger menu.
class NebulaSideMenu extends StatelessWidget {
  final int activeIndex;
  final ValueChanged<int>? onNavigate;
  final VoidCallback? onClose;

  const NebulaSideMenu({
    super.key,
    this.activeIndex = 3, // 3 = Chat by default or matching current screen
    this.onNavigate,
    this.onClose,
  });

  static Future<void> show(
    BuildContext context, {
    int activeIndex = 3,
    ValueChanged<int>? onNavigate,
  }) {
    return showGeneralDialog(
      context: context,
      barrierDismissible: true,
      barrierLabel: 'SideMenu',
      barrierColor: Colors.black.withValues(alpha: 0.35),
      transitionDuration: const Duration(milliseconds: 280),
      transitionBuilder: (context, anim1, anim2, child) {
        final slide = Tween<Offset>(
          begin: const Offset(-1.0, 0.0),
          end: Offset.zero,
        ).animate(CurvedAnimation(parent: anim1, curve: Curves.easeOutCubic));

        return SlideTransition(
          position: slide,
          child: child,
        );
      },
      pageBuilder: (context, anim1, anim2) {
        return NebulaSideMenu(
          activeIndex: activeIndex,
          onNavigate: (idx) {
            Navigator.of(context).pop();
            onNavigate?.call(idx);
          },
          onClose: () => Navigator.of(context).pop(),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final audioService = AvatarAudioService.instance;

    return BackdropFilter(
      filter: ImageFilter.blur(sigmaX: 8, sigmaY: 8),
      child: Align(
        alignment: Alignment.centerLeft,
        child: Container(
          width: 320,
          height: double.infinity,
          margin: const EdgeInsets.symmetric(vertical: 24, horizontal: 16),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.94),
            borderRadius: BorderRadius.circular(28),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.12),
                blurRadius: 32,
                offset: const Offset(8, 0),
              ),
            ],
          ),
          child: SafeArea(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Top Row: Close Button (X)
                  Row(
                    children: [
                      InkWell(
                        onTap: onClose ?? () => Navigator.of(context).maybePop(),
                        borderRadius: BorderRadius.circular(20),
                        child: Container(
                          width: 38,
                          height: 38,
                          decoration: BoxDecoration(
                            color: const Color(0xFFF1F5F9),
                            shape: BoxShape.circle,
                            border: Border.all(color: const Color(0xFFE2E8F0)),
                          ),
                          child: const Icon(Icons.close_rounded,
                              size: 20, color: Color(0xFF475569)),
                        ),
                      ),
                      const Spacer(),
                    ],
                  ),
                  const SizedBox(height: 14),

                  // Active AI Profile Header Card
                  ValueListenableBuilder<String>(
                    valueListenable: audioService.activeAvatarType,
                    builder: (context, avatarType, _) {
                      final isFemale = avatarType == 'female';
                      final avatarImg = isFemale
                          ? 'assets/images/avatar_female.png'
                          : 'assets/images/avatar_male.jpg';

                      return Container(
                        padding: const EdgeInsets.all(12),
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
                            // Text Label
                            Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  isFemale ? 'الرفيق الذكي (سارة)' : 'المساعد الذكي (مازن)',
                                  style: const TextStyle(
                                    fontFamily: 'Cairo',
                                    fontWeight: FontWeight.bold,
                                    fontSize: 15,
                                    color: Color(0xFF1E293B),
                                  ),
                                ),
                                const SizedBox(height: 2),
                                const Text(
                                  'متصل • استجابة فورية',
                                  style: TextStyle(
                                    fontFamily: 'Cairo',
                                    fontSize: 12,
                                    color: Color(0xFF00E5FF),
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                              ],
                            ),

                            // Avatar with AI-01 badge
                            Stack(
                              clipBehavior: Clip.none,
                              children: [
                                Container(
                                  width: 58,
                                  height: 58,
                                  decoration: BoxDecoration(
                                    borderRadius: BorderRadius.circular(16),
                                    border: Border.all(
                                      color: const Color(0xFF00E5FF),
                                      width: 1.5,
                                    ),
                                  ),
                                  child: ClipRRect(
                                    borderRadius: BorderRadius.circular(14),
                                    child: Image.asset(
                                      avatarImg,
                                      fit: BoxFit.cover,
                                    ),
                                  ),
                                ),
                                Positioned(
                                  bottom: -4,
                                  left: -4,
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 6, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: const Color(0xFF00E5FF),
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: Text(
                                      isFemale ? 'AI - 02' : 'AI - 01',
                                      style: const TextStyle(
                                        fontFamily: 'Cairo',
                                        fontSize: 9,
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
                  const SizedBox(height: 18),

                  // Menu Items List
                  Expanded(
                    child: ListView(
                      padding: EdgeInsets.zero,
                      children: [
                        // 1. تسجيل الدخول
                        _buildMenuItem(
                          icon: Icons.login_rounded,
                          title: 'تسجيل الدخول',
                          iconBg: const Color(0xFFEEF2FF),
                          iconColor: const Color(0xFF4F46E5),
                          hasArrow: true,
                          onTap: () => onNavigate?.call(-1),
                        ),
                        const SizedBox(height: 10),

                        // 2. إنشاء حساب (جديد)
                        _buildMenuItem(
                          icon: Icons.person_add_alt_1_rounded,
                          title: 'إنشاء حساب',
                          iconBg: const Color(0xFFECFDF5),
                          iconColor: const Color(0xFF10B981),
                          badgeText: 'جديد',
                          badgeBg: const Color(0xFF10B981),
                          onTap: () => onNavigate?.call(-2),
                        ),
                        const SizedBox(height: 10),

                        // 3. إضافة شخصية
                        _buildMenuItem(
                          icon: Icons.add_rounded,
                          title: 'إضافة شخصية',
                          iconBg: const Color(0xFFF3E8FF),
                          iconColor: const Color(0xFF9333EA),
                          hasArrow: true,
                          onTap: () => onNavigate?.call(2), // MemoryPersonas
                        ),
                        const SizedBox(height: 10),

                        // 4. الدردشة (Highlighted Active Blue Card)
                        _buildChatHighlightedItem(
                          isActive: activeIndex == 1,
                          onTap: () => onNavigate?.call(1), // ChatScreen
                        ),
                        const SizedBox(height: 10),

                        // 5. الأجهزة
                        _buildMenuItem(
                          icon: Icons.desktop_windows_outlined,
                          title: 'الأجهزة',
                          iconBg: const Color(0xFFFEF3C7),
                          iconColor: const Color(0xFFD97706),
                          onTap: () => onNavigate?.call(3), // Diagnostics
                        ),
                        const SizedBox(height: 10),

                        // 6. الشخصيات
                        _buildMenuItem(
                          icon: Icons.groups_outlined,
                          title: 'الشخصيات',
                          iconBg: const Color(0xFFFCE7F3),
                          iconColor: const Color(0xFFDB2777),
                          hasArrow: true,
                          onTap: () => onNavigate?.call(2), // Personas
                        ),
                      ],
                    ),
                  ),

                  // Divider with cyan dot
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
                  const SizedBox(height: 14),

                  // Logout Button (Dark Navy with Cyan Accent)
                  InkWell(
                    onTap: () async {
                      await StorageService.instance.clearToken();
                      if (context.mounted) {
                        Navigator.of(context).maybePop();
                      }
                    },
                    borderRadius: BorderRadius.circular(16),
                    child: Container(
                      height: 52,
                      decoration: BoxDecoration(
                        color: const Color(0xFF0F172A),
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.15),
                            blurRadius: 12,
                            offset: const Offset(0, 4),
                          ),
                        ],
                      ),
                      child: const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.logout_rounded,
                            color: Color(0xFF00E5FF),
                            size: 20,
                          ),
                          SizedBox(width: 10),
                          Text(
                            'خروج',
                            style: TextStyle(
                              fontFamily: 'Cairo',
                              fontWeight: FontWeight.bold,
                              fontSize: 16,
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
    );
  }

  Widget _buildMenuItem({
    required IconData icon,
    required String title,
    required Color iconBg,
    required Color iconColor,
    bool hasArrow = false,
    String? badgeText,
    Color? badgeBg,
    VoidCallback? onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          color: const Color(0xFFF8FAFC),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: const Color(0xFFF1F5F9)),
        ),
        child: Row(
          children: [
            // Left indicator or arrow
            if (hasArrow)
              const Icon(
                Icons.arrow_back_ios_rounded,
                size: 14,
                color: Color(0xFF94A3B8),
              )
            else if (badgeText != null)
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                decoration: BoxDecoration(
                  color: badgeBg ?? const Color(0xFF10B981),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text(
                  badgeText,
                  style: const TextStyle(
                    fontFamily: 'Cairo',
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                ),
              )
            else
              const SizedBox(width: 14),

            const Spacer(),

            // Title
            Text(
              title,
              style: const TextStyle(
                fontFamily: 'Cairo',
                fontWeight: FontWeight.w600,
                fontSize: 15,
                color: Color(0xFF1E293B),
              ),
            ),
            const SizedBox(width: 12),

            // Icon in rounded box
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: iconBg,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Icon(icon, color: iconColor, size: 20),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildChatHighlightedItem({
    required bool isActive,
    VoidCallback? onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF0072FF), Color(0xFF00C6FF)],
            begin: Alignment.centerLeft,
            end: Alignment.centerRight,
          ),
          borderRadius: BorderRadius.circular(16),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF0072FF).withValues(alpha: 0.35),
              blurRadius: 14,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          children: [
            // White "نشط" badge
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Text(
                'نشط',
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: Color(0xFF0072FF),
                ),
              ),
            ),
            const Spacer(),

            // Title
            const Text(
              'الدردشة',
              style: TextStyle(
                fontFamily: 'Cairo',
                fontWeight: FontWeight.bold,
                fontSize: 15,
                color: Colors.white,
              ),
            ),
            const SizedBox(width: 12),

            // Chat bubble icon
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: Colors.white.withValues(alpha: 0.2),
                borderRadius: BorderRadius.circular(12),
              ),
              child: const Icon(
                Icons.chat_bubble_outline_rounded,
                color: Colors.white,
                size: 20,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
