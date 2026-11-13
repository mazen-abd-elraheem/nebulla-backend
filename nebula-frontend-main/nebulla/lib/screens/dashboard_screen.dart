import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
import '../services/locale_service.dart';
import '../services/storage_service.dart';
import '../screens/login_screen.dart';
import '../widgets/interactive_animated_avatar.dart';
import '../widgets/nebula_side_menu.dart';

/// Full interactive animated avatar home screen matching Image 2 mockup.
class DashboardScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;

  const DashboardScreen({super.key, this.onNavigate});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _audioService = AvatarAudioService.instance;
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();

  void _openMenu() {
    NebulaSideMenu.show(
      context,
      activeIndex: 0,
      onNavigate: (idx) {
        if (widget.onNavigate != null && idx >= 0) {
          widget.onNavigate!(idx);
        }
      },
    );
  }

  Future<void> _handleLogout() async {
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
                backgroundColor: const Color(0xFF0F172A),
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
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

    if (confirmed == true && mounted) {
      await StorageService.instance.clearToken();
      if (mounted) {
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const LoginScreen()),
          (route) => false,
        );
      }
    }
  }

  void _triggerAvatarGreeting() {
    final isFemale = _audioService.activeAvatarType.value == 'female';
    final name = _audioService.activePersonaName.value;
    final greeting = isFemale
        ? 'مرحباً بك! أنا $name، جاهزة لمساعدتك في أي استفسار.'
        : 'أهلاً بك! أنا $name، مستعد لمساعدتك وإنجاز مهامك فوراً.';
    _audioService.speak(greeting, emotion: 'happy');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: Colors.white,
      drawer: Drawer(
        backgroundColor: Colors.transparent,
        elevation: 0,
        child: NebulaSideMenu(
          activeIndex: 0,
          onNavigate: (idx) {
            _scaffoldKey.currentState?.closeDrawer();
            if (widget.onNavigate != null && idx >= 0) {
              widget.onNavigate!(idx);
            }
          },
          onClose: () => _scaffoldKey.currentState?.closeDrawer(),
        ),
      ),
      body: Stack(
        fit: StackFit.expand,
        children: [
          // 1. Full-Screen Interactive 3D Avatar (Filter Parallax, 3D Orbit, Living Respiration, Eye Blinking, Lip-Sync)
          Positioned.fill(
            child: InteractiveAnimatedAvatar(
              fullScreen: true,
              onAvatarTapped: _triggerAvatarGreeting,
              onAvatarDoubleTapped: () {
                final current = _audioService.activeAvatarType.value;
                final next = current == 'female' ? 'male' : 'female';
                _audioService.switchAvatar(next);
                _triggerAvatarGreeting();
              },
            ),
          ),

          // 2. Top Header Bar:
          // - LEFT: Black Circular Hamburger Menu Button (strictly on the left)
          // - CENTER: Glowing Green Online Status Dot
          // - RIGHT: Language Switcher + Black Logout Button (strictly on the right)
          SafeArea(
            child: Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                child: Directionality(
                  textDirection: TextDirection.ltr, // Enforces Left=Menu, Right=Logout
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      // LEFT: Black Circular Hamburger Menu Button
                      GestureDetector(
                        onTap: _openMenu,
                        behavior: HitTestBehavior.opaque,
                        child: Container(
                          width: 42,
                          height: 42,
                          decoration: BoxDecoration(
                            color: const Color(0xFF0F172A), // Black background
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.18),
                                blurRadius: 8,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: const Icon(
                            Icons.menu_rounded,
                            color: Colors.white,
                            size: 22,
                          ),
                        ),
                      ),

                      // CENTER: Glowing Green Online Status Dot
                      Container(
                        width: 10,
                        height: 10,
                        decoration: BoxDecoration(
                          color: const Color(0xFF10B981),
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF10B981).withValues(alpha: 0.8),
                              blurRadius: 10,
                              spreadRadius: 3,
                            ),
                          ],
                        ),
                      ),

                      // RIGHT: Language Toggle + Black Logout Button
                      Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // Lang Switch Pill
                          InkWell(
                            onTap: () => LocaleService.instance.toggleLanguage(),
                            borderRadius: BorderRadius.circular(10),
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
                              decoration: BoxDecoration(
                                color: Colors.white.withValues(alpha: 0.95),
                                borderRadius: BorderRadius.circular(10),
                                border: Border.all(color: const Color(0xFFE2E8F0)),
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(Icons.language_rounded, size: 14, color: Color(0xFF0284C7)),
                                  const SizedBox(width: 4),
                                  Text(
                                    LocaleService.instance.isArabic ? 'EN' : 'عربي',
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

                          // Black Logout Button
                          GestureDetector(
                            onTap: _handleLogout,
                            behavior: HitTestBehavior.opaque,
                            child: Container(
                              height: 38,
                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                              decoration: BoxDecoration(
                                color: const Color(0xFF0F172A), // Black background
                                borderRadius: BorderRadius.circular(10),
                                boxShadow: [
                                  BoxShadow(
                                    color: Colors.black.withValues(alpha: 0.15),
                                    blurRadius: 6,
                                    offset: const Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  const Icon(Icons.logout_rounded, color: Color(0xFFF87171), size: 16),
                                  const SizedBox(width: 5),
                                  Text(
                                    LocaleService.instance.translate('logout'),
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
            ),
          ),

        ],
      ),
    );
  }
}
