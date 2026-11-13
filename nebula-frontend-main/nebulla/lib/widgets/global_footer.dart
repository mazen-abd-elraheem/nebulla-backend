import 'package:flutter/material.dart';
import '../services/locale_service.dart';

/// Reusable Global Footer Component matching the user reference image 100%
/// - 4 circular frosted glass buttons: Home, Chat, Personas, Profile
/// - Real-time language translation for Arabic and English
/// - Elegant cybernetic glass gradient background
class GlobalNebulaFooter extends StatelessWidget {
  final int activeIndex;
  final ValueChanged<int> onNavigate;

  const GlobalNebulaFooter({
    super.key,
    required this.activeIndex,
    required this.onNavigate,
  });

  @override
  Widget build(BuildContext context) {
    final t = LocaleService.instance.translate;

    final items = [
      _FooterItem(
        index: 0,
        icon: Icons.home_outlined,
        activeIcon: Icons.home_rounded,
        label: t('nav_home'),
      ),
      _FooterItem(
        index: 1,
        icon: Icons.chat_bubble_outline_rounded,
        activeIcon: Icons.chat_bubble_rounded,
        label: t('nav_chat'),
      ),
      _FooterItem(
        index: 2,
        icon: Icons.groups_outlined,
        activeIcon: Icons.groups_rounded,
        label: t('nav_personas'),
      ),
      _FooterItem(
        index: 3,
        icon: Icons.person_outline_rounded,
        activeIcon: Icons.person_rounded,
        label: t('nav_profile'),
      ),
    ];

    // Directionality matches the screenshot layout (Home -> Chat -> Personas -> Profile)
    return Directionality(
      textDirection: TextDirection.ltr,
      child: Container(
        width: double.infinity,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Colors.transparent,
              Colors.black.withValues(alpha: 0.25),
              Colors.black.withValues(alpha: 0.60),
            ],
            stops: const [0.0, 0.35, 1.0],
          ),
        ),
        padding: const EdgeInsets.only(top: 14, bottom: 10),
        child: SafeArea(
          top: false,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: items.map((item) {
              final isSelected = activeIndex == item.index;

              return InkWell(
                onTap: () => onNavigate(item.index),
                borderRadius: BorderRadius.circular(30),
                child: Padding(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Circular Frosted Glass Button matching Screenshot exactly
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        width: 48,
                        height: 48,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          gradient: isSelected
                              ? LinearGradient(
                                  begin: Alignment.topCenter,
                                  end: Alignment.bottomCenter,
                                  colors: [
                                    const Color(0xFF00E5FF).withValues(alpha: 0.38),
                                    const Color(0xFF0072FF).withValues(alpha: 0.25),
                                  ],
                                )
                              : LinearGradient(
                                  begin: Alignment.topLeft,
                                  end: Alignment.bottomRight,
                                  colors: [
                                    Colors.white.withValues(alpha: 0.85),
                                    Colors.white.withValues(alpha: 0.55),
                                  ],
                                ),
                          border: Border.all(
                            color: isSelected
                                ? const Color(0xFF00E5FF)
                                : Colors.white.withValues(alpha: 0.95),
                            width: isSelected ? 2.2 : 1.5,
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: isSelected
                                  ? const Color(0xFF00E5FF).withValues(alpha: 0.55)
                                  : Colors.black.withValues(alpha: 0.22),
                              blurRadius: isSelected ? 14 : 7,
                              offset: const Offset(0, 3),
                            ),
                          ],
                        ),
                        child: Center(
                          child: Icon(
                            isSelected ? item.activeIcon : item.icon,
                            color: isSelected
                                ? const Color(0xFF0096C7)
                                : const Color(0xFF0F172A),
                            size: 24,
                          ),
                        ),
                      ),
                      const SizedBox(height: 5),

                      // Section Label with Drop Shadow
                      Text(
                        item.label,
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 11,
                          fontWeight:
                              isSelected ? FontWeight.w900 : FontWeight.w700,
                          color: isSelected
                              ? const Color(0xFF00E5FF)
                              : Colors.white,
                          shadows: [
                            Shadow(
                              color: Colors.black.withValues(alpha: 0.85),
                              blurRadius: 5,
                              offset: const Offset(0, 1.5),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }).toList(),
          ),
        ),
      ),
    );
  }
}

class _FooterItem {
  final int index;
  final IconData icon;
  final IconData activeIcon;
  final String label;

  const _FooterItem({
    required this.index,
    required this.icon,
    required this.activeIcon,
    required this.label,
  });
}

