import 'package:flutter/material.dart';
import 'dashboard_screen.dart';
import 'chat_screen.dart';
import 'memory_personas_screen.dart';
import 'persona_memory_specs_screen.dart';
import 'profile_screen.dart';
import 'diagnostics_screen.dart';
import 'settings_screen.dart';
import '../widgets/nebula_side_menu.dart';
import '../widgets/global_footer.dart';

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

  static void openSideMenu(BuildContext context) {
    final state = context.findAncestorStateOfType<_MainShellState>();
    state?._openDrawer();
  }

  @override
  State<MainShell> createState() => _MainShellState();
}

class _MainShellState extends State<MainShell> {
  final GlobalKey<ScaffoldState> _shellScaffoldKey = GlobalKey<ScaffoldState>();
  late int _currentIndex;

  @override
  void initState() {
    super.initState();
    _currentIndex = widget.initialIndex;
  }

  void _onNavigate(int index) {
    if (index >= 0 && index < 7) {
      setState(() => _currentIndex = index);
    }
  }

  void _openDrawer() {
    _shellScaffoldKey.currentState?.openEndDrawer();
  }

  void _closeDrawer() {
    _shellScaffoldKey.currentState?.closeEndDrawer();
  }

  @override
  Widget build(BuildContext context) {
    final screens = [
      DashboardScreen(onNavigate: _onNavigate),
      ChatScreen(onNavigate: _onNavigate),
      MemoryPersonasScreen(onNavigate: _onNavigate),
      PersonaMemorySpecsScreen(onNavigate: _onNavigate),
      const ProfileScreen(),
      const DiagnosticsScreen(),
      const SettingsScreen(),
    ];

    // Sidebar: In RTL (Arabic) endDrawer opens from LEFT.
    // In LTR (English) endDrawer opens from RIGHT.
    final sidebarDrawer = Drawer(
      backgroundColor: Colors.transparent,
      elevation: 0,
      child: NebulaSideMenu(
        activeIndex: _currentIndex,
        onNavigate: (idx) {
          _closeDrawer();
          _onNavigate(idx);
        },
        onClose: _closeDrawer,
      ),
    );

    return Scaffold(
      key: _shellScaffoldKey,
      backgroundColor: Colors.white,
      endDrawer: sidebarDrawer,
      body: Stack(
        children: [
          // Current active screen
          IndexedStack(
            index: _currentIndex,
            children: screens,
          ),

          // Global Unified Glass Footer matching user reference image
          if (MediaQuery.of(context).viewInsets.bottom == 0)
            Align(
              alignment: Alignment.bottomCenter,
              child: GlobalNebulaFooter(
                activeIndex: _currentIndex,
                onNavigate: _onNavigate,
              ),
            ),
        ],
      ),
    );
  }
}
