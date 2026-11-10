import 'package:flutter/material.dart';
import 'dashboard_screen.dart';
import 'chat_screen.dart';
import 'memory_personas_screen.dart';
import 'profile_screen.dart';
import 'diagnostics_screen.dart';
import 'settings_screen.dart';
import '../widgets/nebula_side_menu.dart';

class MainShell extends StatefulWidget {
  const MainShell({super.key, this.initialIndex = 0});
  final int initialIndex;

  static void navigateTo(BuildContext context, int index) {
    final state = context.findAncestorStateOfType<_MainShellState>();
    if (state != null) {
      state._onNavigate(index);
    } else {
      Navigator.of(context).pushAndRemoveUntil(
        MaterialPageRoute(builder: (_) => MainShell(initialIndex: index)),
        (route) => false,
      );
    }
  }

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
    if (index >= 0 && index < 6) {
      setState(() => _currentIndex = index);
    }
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      DashboardScreen(onNavigate: _onNavigate),
      ChatScreen(onNavigate: _onNavigate),
      MemoryPersonasScreen(onNavigate: _onNavigate),
      const ProfileScreen(),
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
          // Automatically hide when keyboard is open so it never obstructs typing
          if (MediaQuery.of(context).viewInsets.bottom == 0)
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
        label: 'الصفحه الرئيسيه',
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

    return Directionality(
      textDirection: TextDirection.ltr, // Matches Mockup layout: Left=Home -> Right=Profile
      child: Container(
        width: double.infinity,
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Colors.transparent,
              Colors.black.withValues(alpha: 0.20),
              Colors.black.withValues(alpha: 0.55),
            ],
            stops: const [0.0, 0.40, 1.0],
          ),
        ),
        padding: const EdgeInsets.only(top: 14, bottom: 12),
        child: SafeArea(
          top: false,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceAround,
            children: List.generate(items.length, (i) {
              final selected = _currentIndex == i;
              final item = items[i];

              return InkWell(
                onTap: () => setState(() => _currentIndex = i),
                borderRadius: BorderRadius.circular(30),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      // Circular Glass Icon Container matching Mockup 100%
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: selected
                              ? const Color(0xFF00E5FF).withValues(alpha: 0.22)
                              : Colors.white.withValues(alpha: 0.16),
                          border: Border.all(
                            color: selected
                                ? const Color(0xFF00E5FF)
                                : Colors.white.withValues(alpha: 0.85),
                            width: selected ? 1.8 : 1.3,
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: selected
                                  ? const Color(0xFF00E5FF).withValues(alpha: 0.45)
                                  : Colors.black.withValues(alpha: 0.18),
                              blurRadius: selected ? 12 : 6,
                              offset: const Offset(0, 2),
                            ),
                          ],
                        ),
                        child: Icon(
                          selected ? item.activeIcon : item.icon,
                          color: selected
                              ? const Color(0xFF00E5FF)
                              : Colors.white,
                          size: 22,
                        ),
                      ),
                      const SizedBox(height: 5),
                      Text(
                        item.label,
                        style: TextStyle(
                          fontFamily: 'Cairo',
                          fontSize: 10.5,
                          fontWeight: selected ? FontWeight.bold : FontWeight.w600,
                          color: selected
                              ? const Color(0xFF00E5FF)
                              : Colors.white,
                          shadows: [
                            Shadow(
                              color: Colors.black.withValues(alpha: 0.7),
                              blurRadius: 4,
                              offset: const Offset(0, 1),
                            ),
                          ],
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
