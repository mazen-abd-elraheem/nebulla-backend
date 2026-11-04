import 'package:flutter/material.dart';
import '../services/avatar_audio_service.dart';
import '../widgets/interactive_animated_avatar.dart';
import '../widgets/nebula_side_menu.dart';

/// Full interactive animated avatar home screen matching the provided UI mockup.
class DashboardScreen extends StatefulWidget {
  final ValueChanged<int>? onNavigate;

  const DashboardScreen({super.key, this.onNavigate});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final _audioService = AvatarAudioService.instance;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      body: Stack(
        fit: StackFit.expand,
        children: [
          // 1. Full-Screen Interactive Animated Avatar (Background & Foreground Character)
          Positioned.fill(
            child: InteractiveAnimatedAvatar(
              fullScreen: true,
              onAvatarTapped: () {
                // Friendly voice greeting triggers on tap
              },
              onAvatarDoubleTapped: () {
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

          // 2. Top Header Bar (09:41, Hamburger Menu, Green Status Dot, Bell)
          SafeArea(
            child: Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    // Hamburger Menu Button (Left) -> Opens Side Menu
                    Builder(
                      builder: (btnCtx) => InkWell(
                        onTap: () {
                          try {
                            Scaffold.of(btnCtx).openDrawer();
                          } catch (_) {
                            NebulaSideMenu.show(
                              btnCtx,
                              activeIndex: 0,
                              onNavigate: (idx) {
                                if (widget.onNavigate != null && idx >= 0) {
                                  widget.onNavigate!(idx);
                                }
                              },
                            );
                          }
                        },
                        borderRadius: BorderRadius.circular(16),
                        child: Container(
                          width: 44,
                          height: 44,
                          decoration: BoxDecoration(
                            color: Colors.white.withValues(alpha: 0.85),
                            shape: BoxShape.circle,
                            border: Border.all(
                              color: const Color(0xFFE2E8F0),
                              width: 1.2,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.05),
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
                    ),

                    // Center: Live Status Green Dot with Pulse
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Container(
                          width: 10,
                          height: 10,
                          decoration: BoxDecoration(
                            color: const Color(0xFF10B981),
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: const Color(0xFF10B981).withValues(alpha: 0.6),
                                blurRadius: 8,
                                spreadRadius: 2,
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(width: 6),
                        const Text(
                          'متصل الآن',
                          style: TextStyle(
                            fontFamily: 'Cairo',
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            color: Color(0xFF0F172A),
                          ),
                        ),
                      ],
                    ),

                    // Notification Bell (Right)
                    InkWell(
                      onTap: () {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text(
                              'لا توجد تنبيهات جديدة • النظام يعمل بكفاءة 100%',
                              style: TextStyle(fontFamily: 'Cairo'),
                            ),
                            behavior: SnackBarBehavior.floating,
                            duration: Duration(seconds: 2),
                          ),
                        );
                      },
                      borderRadius: BorderRadius.circular(16),
                      child: Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.85),
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: const Color(0xFFE2E8F0),
                            width: 1.2,
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: Colors.black.withValues(alpha: 0.05),
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

          // 3. Floating Quick Switcher & Character Name Badge (Top Center below header)
          SafeArea(
            child: Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: const EdgeInsets.only(top: 68),
                child: ValueListenableBuilder<String>(
                  valueListenable: _audioService.activeAvatarType,
                  builder: (context, avatarType, _) {
                    final isFemale = avatarType == 'female';

                    return InkWell(
                      onTap: () {
                        final next = isFemale ? 'male' : 'female';
                        _audioService.switchAvatar(next);
                      },
                      borderRadius: BorderRadius.circular(24),
                      child: Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 16, vertical: 8),
                        decoration: BoxDecoration(
                          color: Colors.white.withValues(alpha: 0.9),
                          borderRadius: BorderRadius.circular(24),
                          border: Border.all(
                            color: const Color(0xFF00E5FF).withValues(alpha: 0.6),
                            width: 1.2,
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: const Color(0xFF00E5FF).withValues(alpha: 0.15),
                              blurRadius: 12,
                              offset: const Offset(0, 4),
                            ),
                          ],
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(
                              Icons.sync_rounded,
                              size: 16,
                              color: isFemale
                                  ? const Color(0xFFEC4899)
                                  : const Color(0xFF0072FF),
                            ),
                            const SizedBox(width: 8),
                            ValueListenableBuilder<String>(
                              valueListenable: _audioService.activePersonaName,
                              builder: (context, personaName, _) => Text(
                                '$personaName • ${isFemale ? "نمط 2" : "نمط 1"}',
                                style: const TextStyle(
                                  fontFamily: 'Cairo',
                                  fontWeight: FontWeight.bold,
                                  fontSize: 13,
                                  color: Color(0xFF1E293B),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
            ),
          ),

          // 4. Floating Action Prompt at Bottom above the Nav Bar
          Positioned(
            left: 20,
            right: 20,
            bottom: 90,
            child: ValueListenableBuilder<bool>(
              valueListenable: _audioService.isSpeaking,
              builder: (context, isSpeaking, _) {
                return InkWell(
                  onTap: () {
                    if (isSpeaking) {
                      _audioService.stop();
                    } else {
                      final personaName = _audioService.activePersonaName.value;
                      final text = 'مرحباً بك! أنا $personaName. كيف يمكنني مساعدتك اليوم؟';
                      _audioService.speak(text, emotion: 'happy');
                    }
                  },
                  borderRadius: BorderRadius.circular(20),
                  child: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 20, vertical: 14),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.92),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: isSpeaking
                            ? const Color(0xFF00E5FF)
                            : const Color(0xFFE2E8F0),
                        width: 1.5,
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: (isSpeaking
                                  ? const Color(0xFF00E5FF)
                                  : Colors.black)
                              .withValues(alpha: 0.1),
                          blurRadius: 18,
                          offset: const Offset(0, 6),
                        ),
                      ],
                    ),
                    child: Row(
                      children: [
                        Container(
                          width: 40,
                          height: 40,
                          decoration: BoxDecoration(
                            gradient: const LinearGradient(
                              colors: [Color(0xFF0072FF), Color(0xFF00C6FF)],
                            ),
                            shape: BoxShape.circle,
                            boxShadow: [
                              BoxShadow(
                                color: const Color(0xFF0072FF)
                                    .withValues(alpha: 0.3),
                                blurRadius: 10,
                                offset: const Offset(0, 2),
                              ),
                            ],
                          ),
                          child: Icon(
                            isSpeaking
                                ? Icons.stop_rounded
                                : Icons.volume_up_rounded,
                            color: Colors.white,
                            size: 22,
                          ),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Text(
                                isSpeaking
                                    ? 'المساعد يتحدث الآن...'
                                    : 'اضغط للتحدث أو الاستماع',
                                style: const TextStyle(
                                  fontFamily: 'Cairo',
                                  fontWeight: FontWeight.bold,
                                  fontSize: 14,
                                  color: Color(0xFF1E293B),
                                ),
                              ),
                              Text(
                                isSpeaking
                                    ? 'مزامنة صوتية حية مع تعابير الوجه والشفتين'
                                    : 'توليد صوت ذكي متزامن مع حركة الشخصية',
                                style: const TextStyle(
                                  fontFamily: 'Cairo',
                                  fontSize: 11,
                                  color: Color(0xFF64748B),
                                ),
                              ),
                            ],
                          ),
                        ),
                        InkWell(
                          onTap: () {
                            widget.onNavigate?.call(1); // Navigate to Chat
                          },
                          child: Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: const Color(0xFFF1F5F9),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Text(
                              'دردشة 💬',
                              style: TextStyle(
                                fontFamily: 'Cairo',
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                                color: Color(0xFF0284C7),
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
