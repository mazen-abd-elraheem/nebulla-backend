import 'dart:ui';
import 'package:flutter/material.dart';
import 'dashboard_screen.dart';
import 'chat_screen.dart';
import 'memory_personas_screen.dart';
import 'diagnostics_screen.dart';
import 'settings_screen.dart';
import '../widgets/nebula_side_menu.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key, this.initialIndex = 0});
  final int initialIndex;

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  late int _currentIndex;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
  }

  void _onNavigate(int index) {
    if (index >= 0 && index < 4) {
      setState(() => _currentIndex = index);
    }
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      DashboardScreen(onNavigate: _onNavigate),
      const ChatScreen(),
      const MemoryPersonasScreen(),
      const DiagnosticsScreen(),
      const SettingsScreen(),
    ];

    return Scaffold(
      backgroundColor: Colors.white,
      drawer: Drawer(
        backgroundColor: Colors.transparent,
        elevation: 0,
        child: NebulaSideMenu(
          activeIndex: _currentIndex,
          onNavigate: (idx) {
            Navigator.of(context).maybePop();
            _onNavigate(idx);
          },
          onClose: () => Navigator.of(context).maybePop(),
        ),
      ),
      body: Stack(
        children: [
          // Current active screen
          IndexedStack(
            index: _currentIndex,
            children: screens,
          ),

          // Floating Translucent Frosted Glass Bottom Navigation Bar matching Image 2
          Align(
            alignment: Alignment.bottomCenter,
            child: _buildFloatingGlassNavBar(),
          ),
        ],
      ),
    );
  }

  Widget _buildFloatingGlassNavBar() {
    final items = [
      const _BottomNavItem(
        icon: Icons.home_outlined,
        activeIcon: Icons.home_rounded,
        label: 'الصفحة الرئيسية',
      ),
      const _BottomNavItem(
        icon: Icons.chat_bubble_outline_rounded,
        activeIcon: Icons.chat_bubble_rounded,
        label: 'الدردشة',
      ),
      const _BottomNavItem(
        icon: Icons.groups_outlined,
        activeIcon: Icons.groups_rounded,
        label: 'الشخصيات',
      ),
      const _BottomNavItem(
        icon: Icons.person_outline_rounded,
        activeIcon: Icons.person_rounded,
        label: 'الملف الشخصي',
      ),
    ];

    return SafeArea(
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        height: 66,
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.88),
          borderRadius: BorderRadius.circular(32),
          border: Border.all(
            color: Colors.white.withValues(alpha: 0.9),
            width: 1.5,
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.08),
              blurRadius: 24,
              offset: const Offset(0, 6),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(32),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 16, sigmaY: 16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceAround,
              children: List.generate(items.length, (i) {
                final selected = _currentIndex == i;
                final item = items[i];

                return InkWell(
                  onTap: () => setState(() => _currentIndex = i),
                  borderRadius: BorderRadius.circular(24),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 14, vertical: 6),
                    decoration: selected
                        ? BoxDecoration(
                            color: const Color(0xFF0072FF).withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(20),
                          )
                        : null,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          selected ? item.activeIcon : item.icon,
                          color: selected
                              ? const Color(0xFF0072FF)
                              : const Color(0xFF64748B),
                          size: 22,
                        ),
                        const SizedBox(height: 3),
                        Text(
                          item.label,
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 10,
                            fontWeight:
                                selected ? FontWeight.bold : FontWeight.w500,
                            color: selected
                                ? const Color(0xFF0072FF)
                                : const Color(0xFF64748B),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              }),
            ),
          ),
        ),
      ),
    );
  }
}

class _BottomNavItem {
  final IconData icon;
  final IconData activeIcon;
  final String label;

  const _BottomNavItem({
    required this.icon,
    required this.activeIcon,
    required this.label,
  });
}
