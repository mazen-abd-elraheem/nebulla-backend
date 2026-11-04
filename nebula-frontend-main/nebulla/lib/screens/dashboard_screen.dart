import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
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
          // 1. Full-Screen Interactive Animated Character matching Image 2
          Positioned.fill(
            child: InteractiveAnimatedAvatar(
              fullScreen: true,
              onAvatarTapped: () {
                // Tapping anywhere on the character triggers friendly voice greeting
              },
              onAvatarDoubleTapped: () {
                // Double tap toggles between Male & Female visual styles
                final isFemale = _audioService.activeAvatarType.value == 'female';
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(
                      isFemale
                          ? 'تم تبديل المظهر: النمط الثاني'
                          : 'تم تبديل المظهر: النمط الأول',
                      style: const TextStyle(fontFamily: 'Cairo'),
                    ),
                    duration: const Duration(seconds: 2),
                    behavior: SnackBarBehavior.floating,
                  ),
                );
              },
            ),
          ),

          // 2. Top Header Bar matching Image 2 100%:
          // - LEFT: Hamburger Menu Button (opens side menu)
          // - CENTER: Live Green Status Dot
          // - RIGHT: Notification Bell Button
          SafeArea(
            child: Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 10),
                child: Directionality(
                  textDirection: TextDirection.ltr, // Enforces Left=Menu, Right=Bell
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      // LEFT: Circular Hamburger Menu Button -> Opens Side Menu
                      InkWell(
                        onTap: () {
                          _scaffoldKey.currentState?.openDrawer();
                        },
                        borderRadius: BorderRadius.circular(22),
                        child: Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.9),
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: const Color(0xFFE2E8F0),
                              width: 1.2,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.06),
                                blurRadius: 10,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: const Icon(
                            Icons.menu_rounded,
                            color: Color(0xFF1E293B),
                            size: 24,
                          ),
                        ),
                      ),

                      // CENTER: Green Online Status Dot with subtle pulse matching Image 2
                      Container(
                        width: 9,
                        height: 9,
                        decoration: BoxDecoration(
                          color: const Color(0xFF10B981),
                          shape: BoxShape.circle,
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF10B981).withValues(alpha: 0.7),
                              blurRadius: 8,
                              spreadRadius: 2,
                            ),
                          ],
                        ),
                      ),

                      // RIGHT: Circular Notification Bell Button matching Image 2
                      InkWell(
                        onTap: () {
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(
                              content: Text(
                                'لا توجد إشعارات جديدة • النظام يعمل بكفاءة 100%',
                                style: TextStyle(fontFamily: 'Cairo'),
                              ),
                              behavior: SnackBarBehavior.floating,
                              duration: Duration(seconds: 2),
                            ),
                          );
                        },
                        borderRadius: BorderRadius.circular(22),
                        child: Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.9),
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: const Color(0xFFE2E8F0),
                              width: 1.2,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.06),
                                blurRadius: 10,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: const Icon(
                            Icons.notifications_none_rounded,
                            color: Color(0xFF1E293B),
                            size: 24,
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
    );
  }
}
