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
    this.activeIndex = 1, // 1 = Chat by default
    this.onNavigate,
    this.onClose,
  });

  /// Displays the side menu reliably using Flutter's native dialog overlay
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
        return Directionality(
          textDirection: TextDirection.rtl,
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

  @override
  Widget build(BuildContext context) {
    final audioService = AvatarAudioService.instance;

    return Directionality(
      textDirection: TextDirection.rtl,
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

            // Left-aligned Side Menu Card (matching mockup Image 3)
            Align(
              alignment: Alignment.centerLeft,
              child: Container(
                width: 310,
                height: double.infinity,
                margin: const EdgeInsets.symmetric(vertical: 20, horizontal: 16),
                decoration: BoxDecoration(
                  color: Colors.white,
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
                        // 1. Top Close Button (X)
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
                                child: const Icon(
                                  Icons.close_rounded,
                                  size: 20,
                                  color: Color(0xFF475569),
                                ),
                              ),
                            ),
                            const Spacer(),
                          ],
                        ),
                        const SizedBox(height: 12),

                        // 2. Active AI Profile Header Card with Quick Persona Switch
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
                              child: Column(
                                children: [
                                  Row(
                                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                    children: [
                                      // Dynamic User-Chosen Persona Name
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            ValueListenableBuilder<String>(
                                              valueListenable: audioService.activePersonaName,
                                              builder: (context, name, _) => Text(
                                                name,
                                                maxLines: 1,
                                                overflow: TextOverflow.ellipsis,
                                                style: const TextStyle(
                                                  fontFamily: 'Cairo',
                                                  fontWeight: FontWeight.bold,
                                                  fontSize: 15,
                                                  color: Color(0xFF1E293B),
                                                ),
                                              ),
                                            ),
                                            const SizedBox(height: 2),
                                            const Text(
                                              'متصل • استجابة فورية',
                                              style: TextStyle(
                                                fontFamily: 'Cairo',
                                                fontSize: 12,
                                                color: Color(0xFF0284C7),
                                                fontWeight: FontWeight.w600,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),

                                      // Avatar Image with AI-01 / AI-02 badge
                                      Stack(
                                        clipBehavior: Clip.none,
                                        children: [
                                          Container(
                                            width: 56,
                                            height: 56,
                                            decoration: BoxDecoration(
                                              borderRadius: BorderRadius.circular(16),
                                              border: Border.all(
                                                color: const Color(0xFF0284C7),
                                                width: 1.5,
                                              ),
                                            ),
                                            child: ClipRRect(
                                              borderRadius: BorderRadius.circular(14),
                                              child: Image.asset(
                                                avatarImg,
                                                fit: BoxFit.cover,
                                                alignment: Alignment.topCenter,
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
                                                color: const Color(0xFF0284C7),
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
                                  const SizedBox(height: 10),
                                  // Quick Switch Persona Button
                                  InkWell(
                                    onTap: () {
                                      final nextType = isFemale ? 'male' : 'female';
                                      audioService.switchAvatar(nextType);
                                    },
                                    borderRadius: BorderRadius.circular(12),
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 10, vertical: 6),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFF0284C7).withValues(alpha: 0.08),
                                        borderRadius: BorderRadius.circular(12),
                                        border: Border.all(
                                          color: const Color(0xFF0284C7).withValues(alpha: 0.25),
                                        ),
                                      ),
                                      child: Row(
                                        mainAxisAlignment: MainAxisAlignment.center,
                                        children: [
                                          const Icon(
                                            Icons.swap_horiz_rounded,
                                            size: 16,
                                            color: Color(0xFF0284C7),
                                          ),
                                          const SizedBox(width: 6),
                                          Text(
                                            isFemale
                                                ? 'تبديل إلى الشخصية الأولى (AI - 01)'
                                                : 'تبديل إلى الشخصية الثانية (AI - 02)',
                                            style: const TextStyle(
                                              fontFamily: 'Cairo',
                                              fontSize: 11.5,
                                              fontWeight: FontWeight.bold,
                                              color: Color(0xFF0284C7),
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            );
                          },
                        ),
                        const SizedBox(height: 16),

                        // 3. Navigation Menu Items List - All with uniform color, dynamic touch transition
                        Expanded(
                          child: ListView(
                            padding: EdgeInsets.zero,
                            children: [
                              // تسجيل الدخول
                              _InteractiveMenuButton(
                                icon: Icons.login_rounded,
                                title: 'تسجيل الدخول',
                                hasArrow: true,
                                onTap: () => onNavigate?.call(-1),
                              ),
                              const SizedBox(height: 9),

                              // إنشاء حساب (جديد)
                              _InteractiveMenuButton(
                                icon: Icons.person_add_alt_1_rounded,
                                title: 'إنشاء حساب',
                                badgeText: 'جديد',
                                onTap: () => onNavigate?.call(-2),
                              ),
                              const SizedBox(height: 9),

                              // إضافة شخصية
                              _InteractiveMenuButton(
                                icon: Icons.add_rounded,
                                title: 'إضافة شخصية',
                                hasArrow: true,
                                onTap: () => onNavigate?.call(2), // Personas screen
                              ),
                              const SizedBox(height: 9),

                              // الدردشة
                              _InteractiveMenuButton(
                                icon: Icons.chat_bubble_outline_rounded,
                                title: 'الدردشة',
                                isActive: activeIndex == 1,
                                badgeText: activeIndex == 1 ? 'نشط' : null,
                                onTap: () => onNavigate?.call(1), // Chat screen
                              ),
                              const SizedBox(height: 9),

                              // الأجهزة
                              _InteractiveMenuButton(
                                icon: Icons.desktop_windows_outlined,
                                title: 'الأجهزة',
                                isActive: activeIndex == 3,
                                onTap: () => onNavigate?.call(3), // Diagnostics
                              ),
                              const SizedBox(height: 9),

                              // الشخصيات
                              _InteractiveMenuButton(
                                icon: Icons.groups_outlined,
                                title: 'الشخصيات',
                                hasArrow: true,
                                isActive: activeIndex == 2,
                                onTap: () => onNavigate?.call(2), // Personas
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
                                color: Color(0xFF0284C7),
                                shape: BoxShape.circle,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),

                        // 5. Logout Button (Dark Navy)
                        InkWell(
                          onTap: () async {
                            await StorageService.instance.clearToken();
                            if (context.mounted) {
                              Navigator.of(context).maybePop();
                            }
                          },
                          borderRadius: BorderRadius.circular(16),
                          child: Container(
                            height: 50,
                            decoration: BoxDecoration(
                              color: const Color(0xFF0F172A),
                              borderRadius: BorderRadius.circular(16),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.black.withValues(alpha: 0.12),
                                  blurRadius: 10,
                                  offset: const Offset(0, 3),
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
                                    fontSize: 15,
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

/// Interactive button in the side menu:
/// - Has a single uniform clean base color for all buttons
/// - Dynamically transitions color to vibrant blue on touch / hover / active
class _InteractiveMenuButton extends StatefulWidget {
  final IconData icon;
  final String title;
  final bool hasArrow;
  final String? badgeText;
  final bool isActive;
  final VoidCallback? onTap;

  const _InteractiveMenuButton({
    required this.icon,
    required this.title,
    this.hasArrow = false,
    this.badgeText,
    this.isActive = false,
    this.onTap,
  });

  @override
  State<_InteractiveMenuButton> createState() => _InteractiveMenuButtonState();
}

class _InteractiveMenuButtonState extends State<_InteractiveMenuButton> {
  bool _isHovered = false;
  bool _isPressed = false;

  @override
  Widget build(BuildContext context) {
    final isHighlighted = widget.isActive || _isHovered || _isPressed;

    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      cursor: SystemMouseCursors.click,
      child: GestureDetector(
        onTapDown: (_) => setState(() => _isPressed = true),
        onTapUp: (_) => setState(() => _isPressed = false),
        onTapCancel: () => setState(() => _isPressed = false),
        onTap: widget.onTap,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeInOut,
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
          decoration: BoxDecoration(
            color: isHighlighted
                ? const Color(0xFF0284C7) // Vibrant Blue on touch / hover / active
                : const Color(0xFFF8FAFC), // Uniform base color for ALL buttons
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isHighlighted
                  ? const Color(0xFF0284C7)
                  : const Color(0xFFE2E8F0), // Uniform subtle border
              width: 1.2,
            ),
            boxShadow: isHighlighted
                ? [
                    BoxShadow(
                      color: const Color(0xFF0284C7).withValues(alpha: 0.35),
                      blurRadius: 12,
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
              // Left indicator or arrow or badge
              if (widget.hasArrow)
                Icon(
                  Icons.arrow_back_ios_rounded,
                  size: 14,
                  color: isHighlighted
                      ? Colors.white.withValues(alpha: 0.9)
                      : const Color(0xFF94A3B8),
                )
              else if (widget.badgeText != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: isHighlighted
                        ? Colors.white.withValues(alpha: 0.25)
                        : const Color(0xFFE2E8F0),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    widget.badgeText!,
                    style: TextStyle(
                      fontFamily: 'Cairo',
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      color: isHighlighted ? Colors.white : const Color(0xFF475569),
                    ),
                  ),
                )
              else
                const SizedBox(width: 14),

              const Spacer(),

              // Title
              Text(
                widget.title,
                style: TextStyle(
                  fontFamily: 'Cairo',
                  fontWeight: FontWeight.w600,
                  fontSize: 14.5,
                  color: isHighlighted ? Colors.white : const Color(0xFF1E293B),
                ),
              ),
              const SizedBox(width: 12),

              // Icon container with smooth color transition
              AnimatedContainer(
                duration: const Duration(milliseconds: 180),
                width: 36,
                height: 36,
                decoration: BoxDecoration(
                  color: isHighlighted
                      ? Colors.white.withValues(alpha: 0.2)
                      : const Color(0xFFF1F5F9), // Uniform icon container
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(
                  widget.icon,
                  color: isHighlighted ? Colors.white : const Color(0xFF334155),
                  size: 19,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
